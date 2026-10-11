#include "rom_import.hpp"
#include "../runtime/rom_image.hpp"
#include <stdexcept>
#include <vector>
#include <cassert>
#include <fstream>

namespace fs = std::filesystem;
void write(const fs::path& path) { std::ofstream(path) << "synthetic import"; }
// Shared host/shell ROM normalization; SHA providers differ per link profile.
void rom_image_regression() {
    namespace rt = sc64::runtime;
    std::vector<std::uint8_t> z64(rt::rom_size);
    for (std::size_t i = 0; i < z64.size(); ++i) z64[i] = std::uint8_t(i * 7 + (i >> 9));
    z64[0] = 0x80; z64[1] = 0x37; z64[2] = 0x12; z64[3] = 0x40;
    auto with = [&](int lane_xor) {
        std::vector<std::uint8_t> out(z64.size());
        for (std::size_t i = 0; i < z64.size(); ++i) out[i ^ lane_xor] = z64[i];
        return out;
    };
    for (int lane_xor : {0, 1, 3}) {
        auto dump = with(lane_xor);
        rt::normalize_rom_byte_order(dump);
        assert(dump == z64);
    }
    auto rejects = [](auto&& f) { try { f(); } catch (const std::runtime_error&) { return true; } return false; };
    auto bad = z64; bad[0] = 0x12;
    assert(rejects([&] { rt::normalize_rom_byte_order(bad); }));
    std::vector<std::uint8_t> short_dump(16);
    assert(rejects([&] { rt::normalize_rom_byte_order(short_dump); }));
    auto v64 = with(1);
    rt::validate_rom(v64, [](std::span<const std::uint8_t>) { return std::string(rt::rom_sha1); });
    assert(v64 == z64);
    auto other = with(3);
    assert(rejects([&] { rt::validate_rom(other, [](std::span<const std::uint8_t>) { return std::string(40, '0'); }); }));
}
int main(int argc, char** argv) {
    assert(argc == 2);
    rom_image_regression();
    const fs::path directory = fs::absolute(argv[1]);
    assert(!fs::exists(directory));
    fs::create_directories(directory / "files");
    const auto files = directory / "files";
    const auto pending = files / "sc64-import-123.tmp";
    const auto late = files / "sc64-import-456.tmp";
    const auto taken = files / "sc64-import-789.tmp";
    const auto orphan = files / "sc64-import-crashed.tmp";
    const auto normalized_tmp = files / ".sc64-rom.tmp";
    const auto outside = directory / "sc64-import-user.tmp";
    const auto saved = files / "sc64.fla";
    const auto rom = files / "sc64-ntsc-u.z64";
    write(orphan); write(normalized_tmp); write(outside); write(saved); write(rom);
    write(files / "sc64-import-.tmp");
    fs::create_directory(files / "sc64-import-folder.tmp");
    fs::create_symlink(outside, files / "sc64-import-link.tmp");
    fs::create_directory_symlink(files, directory / "alias");
    sc64::desktop::RomImportState state;
    assert(!state.initialize(directory / "alias"));
    assert(!fs::exists(orphan) && !fs::exists(normalized_tmp));
    assert(fs::exists(outside) && fs::exists(saved) && fs::exists(rom));
    assert(fs::exists(files / "sc64-import-.tmp"));
    assert(fs::is_directory(files / "sc64-import-folder.tmp"));
    assert(fs::is_symlink(files / "sc64-import-link.tmp"));

    assert(state.begin());
    assert(state.take().path.empty() && !state.begin()); // copying stays busy
    write(pending);
    assert(!state.complete({pending.string(), {}}));
    assert(!state.begin()); // pending result cannot be replaced by another picker
    assert(!state.finalize());
    assert(!state.alive() && !fs::exists(pending) && !state.begin());
    write(late);
    assert(!state.complete({late.string(), {}}));
    assert(!fs::exists(late) && state.take().path.empty());

    assert(!state.initialize(files) && state.begin());
    write(taken);
    assert(!state.complete({taken.string(), {}}));
    assert(state.take().path == taken.string());
    assert(!state.finalize() && fs::exists(taken)); // ownership transferred
    fs::remove(taken);

    assert(!state.initialize(files) && state.begin());
    assert(!state.complete({{}, "provider failed"}));
    assert(!state.begin() && state.take().error == "provider failed" && state.begin());
    state.cancel(); assert(state.begin());
    assert(!state.finalize());
    assert(fs::exists(saved) && fs::exists(rom) && fs::exists(outside));
    fs::remove_all(directory);
}
