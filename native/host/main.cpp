#include "capture.hpp"
#include "audio.hpp"
#include "flash_device.hpp"
#include "guest_poll.hpp"
#include "rom_image.hpp"
#include <librecomp/game.hpp>
#include <librecomp/overlays.hpp>
#include <librecomp/rsp.hpp>
#include <xxHash/xxh3.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <memory>
#include <stdexcept>
#if defined(__APPLE__) || defined(__linux__)
#include <sys/resource.h>
#endif

extern "C" {
#include "funcs.h"
#include "recomp_overlays.inl"
}

namespace {
using Clock = std::chrono::steady_clock;
std::unique_ptr<sc64::host::Capture> capture;
std::unique_ptr<sc64::host::Audio> audio;
std::atomic<uint64_t> fields = 0;
std::atomic<uint64_t> rendered_tasks = 0;
volatile std::sig_atomic_t interrupted = 0;
Clock::time_point started;
double duration = 30;
std::vector<std::array<uint64_t, 3>> inputs;
std::atomic<uint16_t> pad_buttons = 0;
bool requested_stop = false;
bool silent = false;
double next_telemetry = 0;

class Renderer final : public ultramodern::renderer::RendererContext {
public:
    Renderer() {
        setup_result = ultramodern::renderer::SetupResult::Success;
        chosen_api = ultramodern::renderer::GraphicsApi::Auto;
    }
    bool valid() override { return true; }
    bool update_config(const ultramodern::renderer::GraphicsConfig&,
                       const ultramodern::renderer::GraphicsConfig&) override { return true; }
    void enable_instant_present() override {}
    void send_dl(const OSTask* task) override {
        if (task->t.type != M_GFXTASK) throw std::runtime_error("Unexpected non-graphics task");
        ++rendered_tasks;
        capture->event({{"kind", "task_completed"}, {"sequence", rendered_tasks.load()},
                        {"field", fields.load()}});
    }
    void send_dummy_workload(uint32_t) override {}
    void update_screen() override {
        capture->vi(*ultramodern::renderer::get_vi_regs(), fields.load());
    }
    void shutdown() override { capture->event({{"kind", "renderer_shutdown"}}); }
    uint32_t get_display_framerate() const override { return 60; }
    float get_resolution_scale() const override { return 1; }
};

std::unique_ptr<ultramodern::renderer::RendererContext> create_renderer(
    uint8_t*, ultramodern::renderer::WindowHandle, bool) {
    return std::make_unique<Renderer>();
}
void on_vi() { ++fields; }
void queue_samples(int16_t* samples, size_t count) { audio->queue(samples, count); }
size_t samples_remaining() { return audio->remaining(); }
void set_frequency(uint32_t rate) {
    audio->frequency(rate);
    capture->event({{"kind", "ai_frequency"}, {"rate", rate}, {"field", fields.load()}});
}
bool get_input(int player, uint16_t* buttons, float* x, float* y) {
    if (player != 0) return false;
    *buttons = pad_buttons.load(); *x = 0; *y = 0;
    return true;
}
ultramodern::input::connected_device_info_t device_info(int player) {
    using namespace ultramodern::input;
    return {player == 0 ? Device::Controller : Device::None,
            player == 0 ? Pak::RumblePak : Pak::None};
}
void on_error(const char* message) {
    std::fprintf(stderr, "Runtime: %s\n", message);
    if (capture) capture->event({{"kind", "runtime_error"}, {"message", message}});
}
void on_update(void*) {
    uint16_t buttons = 0;
    const auto field = fields.load();
    for (const auto& input : inputs) {
        if (field >= input[0] && field < input[0] + input[1]) buttons |= uint16_t(input[2]);
    }
    const auto previous_buttons = pad_buttons.exchange(buttons);
    if (previous_buttons != buttons) capture->event({{"kind", "input"}, {"field", field}, {"buttons", buttons}});
    const double elapsed = std::chrono::duration<double>(Clock::now() - started).count();
    if (elapsed >= next_telemetry) {
        nlohmann::json telemetry{{"kind", "telemetry"}, {"elapsed_seconds", elapsed},
            {"field", field}, {"submitted_tasks", capture->task_count()},
            {"completed_tasks", rendered_tasks.load()}, {"audio_samples", audio->samples()},
            {"audio_peak_queue_bytes", audio->peak_queue_bytes()}};
#if defined(__APPLE__) || defined(__linux__)
        rusage usage{};
        if (getrusage(RUSAGE_SELF, &usage) == 0) {
#if defined(__APPLE__)
            telemetry["max_resident_bytes"] = usage.ru_maxrss;
#else
            telemetry["max_resident_bytes"] = uint64_t(usage.ru_maxrss) * 1024;
#endif
        }
#endif
        capture->event(telemetry);
        next_telemetry = elapsed + 10;
    }
    if (!requested_stop && (elapsed >= duration || interrupted)) {
        requested_stop = true;
        capture->event({{"kind", "stop_requested"}, {"elapsed_seconds", elapsed}, {"field", field}});
        ultramodern::quit();
    }
}
void boot_callback(uint8_t* rdram, recomp_context*) {
    // Match the observed cold reference OS globals (physical CIC is unknown).
    MEM_W(0, int64_t(int32_t(0x80000314))) = 1;
}
void signal_handler(int) { interrupted = 1; }

std::vector<uint8_t> load_rom(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    file.exceptions(std::ios::failbit | std::ios::badbit);
    if (file.tellg() != std::streamoff(sc64::runtime::rom_size)) throw std::runtime_error("Expected 32 MiB ROM");
    std::vector<uint8_t> bytes(sc64::runtime::rom_size);
    file.seekg(0);
    file.read(reinterpret_cast<char*>(bytes.data()), bytes.size());
    sc64::runtime::validate_rom(bytes, sc64::host::sha1);
    return bytes;
}
}

extern "C" void sc64_capture_submit(uint8_t* rdram, const OSTask* task) {
    capture->task(rdram, *task, fields.load());
}

// The host has no pause point: capture runs are unattended and timed.
extern "C" void sc64_idle_poll(uint8_t* rdram) { sc64::runtime::idle_boundary(rdram); }

extern "C" void sc64_guest_poll(uint8_t* rdram) { sc64::runtime::busy_wait_boundary(rdram); }

extern "C" uint32_t sc64_ai_status(uint8_t* rdram) {
    return sc64::runtime::ai_status_boundary(rdram, [] { return audio->status(); });
}

extern "C" void osViGetCurrentLine_recomp(uint8_t* rdram, recomp_context* ctx) {
    // Unlike the shell profile, this boundary has never yielded the host thread.
    sc64::runtime::guest_boundary(rdram, 0);
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - started).count();
    ctx->r2 = sc64::runtime::vi_current_line(elapsed, fields.load());
}

int main(int argc, char** argv) {
    try {
        std::filesystem::path rom_path, output, storage;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            auto next = [&]() -> std::string {
                if (++i >= argc) throw std::runtime_error("Missing argument for " + arg);
                return argv[i];
            };
            if (arg == "--rom") rom_path = next();
            else if (arg == "--output") output = next();
            else if (arg == "--storage") storage = next();
            else if (arg == "--seconds") duration = std::stod(next());
            else if (arg == "--silent") silent = true;
            else if (arg == "--inputs") {
                std::ifstream file(next());
                const auto json = nlohmann::json::parse(file);
                for (const auto& item : json) inputs.push_back({item.at("field").get<uint64_t>(),
                    item.at("duration").get<uint64_t>(), item.at("buttons").get<uint64_t>()});
            }
            else throw std::runtime_error("Unknown argument: " + arg);
        }
        if (rom_path.empty() || output.empty() || storage.empty() || duration <= 0 || duration > 3600) {
            throw std::runtime_error("Usage: sc64_capture --rom ROM --output NEW_DIR --storage PRIVATE_DIR [--seconds 30] [--inputs JSON] [--silent]");
        }
        const auto rom = load_rom(rom_path);
        capture = std::make_unique<sc64::host::Capture>(output);
        audio = std::make_unique<sc64::host::Audio>(output / "audio.wav", silent);
        audio->frequency(48000);
        std::filesystem::create_directories(storage);
        sc64::runtime::flash_device().initialize(storage / "sc64.fla",
            [](const char* kind, uint32_t address, uint32_t value, size_t bytes) {
                capture->event({{"kind", kind}, {"address", address},
                    {"value", value}, {"bytes", bytes}, {"field", fields.load()}});
            });
        recomp::register_config_path(storage);
        recomp::overlays::register_overlays({section_table, ARRLEN(section_table), ARRLEN(section_table)}, {nullptr, 0});
        recomp::GameEntry game{};
        game.rom_hash = XXH3_64bits(rom.data(), rom.size());
        game.internal_name = "STARCRAFT64";
        game.display_name = "StarCraft 64 NTSC-U";
        game.game_id = u8"sc64-ntsc-u";
        game.save_type = recomp::SaveType::Flashram;
        game.is_enabled = true;
        game.entrypoint_address = int64_t(int32_t(0x80000400));
        game.entrypoint = recomp_entrypoint;
        game.on_init_callback = boot_callback;
        recomp::register_game(game);
        // Write only the already-normalized and SHA-1-validated personal image.
        sc64::host::write_bytes(storage / "sc64-ntsc-u.z64", rom);
        recomp::Configuration config{};
        config.project_version = {0, 1, 0};
#if defined(__APPLE__)
        config.window_handle = {reinterpret_cast<void*>(1), nullptr};
#elif defined(_WIN32)
        config.window_handle = {reinterpret_cast<HWND>(1), 0};
#else
        config.window_handle = reinterpret_cast<SDL_Window*>(1);
#endif
        config.renderer_callbacks.create_render_context = create_renderer;
        config.rsp_callbacks.get_rsp_microcode = [](const OSTask*) -> RspUcodeFunc* {
            throw std::runtime_error("Non-graphics RSP task requires new research (D-020)");
        };
        config.audio_callbacks = {queue_samples, samples_remaining, set_frequency};
        config.input_callbacks.get_input = get_input;
        config.input_callbacks.get_connected_device_info = device_info;
        config.events_callbacks.vi_callback = on_vi;
        config.error_handling_callbacks.message_box = on_error;
        config.gfx_callbacks.update_gfx = on_update;
        std::signal(SIGINT, signal_handler);
        started = Clock::now();
        recomp::start_game(game.game_id, "");
        recomp::start(config);
        audio->finish();
        capture->finish({{"rom_sha1", sc64::host::sha1(rom)}, {"fields", fields.load()},
            {"completed_tasks", rendered_tasks.load()}, {"audio_samples", audio->samples()},
            {"audio_rate", audio->rate()}, {"audio_peak_queue_bytes", audio->peak_queue_bytes()},
            {"elapsed_seconds", std::chrono::duration<double>(Clock::now() - started).count()},
            {"clean_shutdown", true}, {"silent", silent}});
        std::printf("Completed: %llu fields, %llu tasks, %llu audio samples\n",
            static_cast<unsigned long long>(fields.load()),
            static_cast<unsigned long long>(rendered_tasks.load()),
            static_cast<unsigned long long>(audio->samples()));
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "sc64_capture: %s\n", error.what());
        return 1;
    }
}
