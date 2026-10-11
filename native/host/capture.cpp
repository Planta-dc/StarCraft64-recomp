#include "capture.hpp"

#include <array>
#include <openssl/evp.h>
#include <stdexcept>
#include <iomanip>
#include <sstream>

namespace sc64::host {
namespace {
std::string digest(std::span<const uint8_t> bytes, const EVP_MD* algorithm) {
    unsigned char output[EVP_MAX_MD_SIZE];
    unsigned int size = 0;
    if (!EVP_Digest(bytes.data(), bytes.size(), output, &size, algorithm, nullptr)) {
        throw std::runtime_error("OpenSSL digest failed");
    }
    std::ostringstream text;
    for (unsigned int i = 0; i < size; ++i) {
        text << std::hex << std::setw(2) << std::setfill('0') << unsigned(output[i]);
    }
    return text.str();
}
}
std::string sha256(std::span<const uint8_t> bytes) { return digest(bytes, EVP_sha256()); }
std::string sha1(std::span<const uint8_t> bytes) { return digest(bytes, EVP_sha1()); }

void write_bytes(const std::filesystem::path& path, std::span<const uint8_t> bytes) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    output.exceptions(std::ios::badbit | std::ios::failbit);
    output.write(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    output.close();
}

Capture::Capture(const std::filesystem::path& directory)
    : directory_(directory), canonical_(0x800000) {
    // Refuse replacement of an earlier run: diagnostics are evidence too.
    if (std::filesystem::exists(directory_)) {
        throw std::runtime_error("Capture directory already exists");
    }
    std::filesystem::create_directories(directory_ / "pages");
    events_.open(directory_ / "events.jsonl");
    events_.exceptions(std::ios::failbit | std::ios::badbit);
}

void Capture::event(nlohmann::json value) {
    std::lock_guard lock(mutex_);
    events_ << value.dump() << '\n';
    events_.flush();
}

void Capture::task(uint8_t* rdram, const OSTask& task, uint64_t field) {
    const auto& t = task.t;
    if (t.type != M_GFXTASK || t.ucode_size != 4096) {
        throw std::runtime_error("Unexpected graphics microcode descriptor");
    }
    for (size_t i = 0; i < canonical_.size(); ++i) canonical_[i] = rdram[i ^ 3];
    auto range = [&](uint32_t address, uint32_t size) -> std::span<const uint8_t> {
        address &= 0x1FFFFFFF;
        if (address > canonical_.size() || size > canonical_.size() - address) {
            throw std::runtime_error("Task dependency outside 8 MiB RDRAM");
        }
        return {canonical_.data() + address, size};
    };
    const auto microcode_hash = sha1(range(t.ucode, t.ucode_size));
    if (microcode_hash != "7d0f686719afde0703d377ccc7a492318c01eec0") {
        throw std::runtime_error("Unresearched graphics microcode: " + microcode_hash);
    }
    // Each packet references a complete immutable snapshot. Content-addressed
    // pages avoid 8 MiB per task without weakening the dependency capture.
    nlohmann::json pages = nlohmann::json::array();
    for (size_t i = 0; i < canonical_.size(); i += 4096) {
        const auto page = std::span<const uint8_t>(canonical_.data() + i, 4096);
        const auto key = sha256(page);
        const auto path = directory_ / "pages" / (key + ".bin");
        if (stored_pages_.insert(key).second) write_bytes(path, page);
        pages.push_back(key);
    }
    nlohmann::json descriptor = nlohmann::json::array();
    const auto* words = reinterpret_cast<const uint32_t*>(&task);
    for (size_t i = 0; i < sizeof(task) / 4; ++i) descriptor.push_back(words[i]);
    const auto data = range(t.data_ptr, t.data_size);
    const auto id = ++tasks_;
    write_bytes(directory_ / ("task-" + std::to_string(id) + ".dl.bin"), data);
    event({{"kind", "sp_task"}, {"task", id}, {"field", field},
           {"descriptor", descriptor}, {"ucode_sha1", microcode_hash},
           {"dl_sha256", sha256(data)}, {"rdram_sha256", sha256(canonical_)},
           {"pages", pages}, {"page_size", 4096}, {"rdram_size", canonical_.size()},
           {"snapshot", "guest-submit-before-task-enqueue"}});
}

void Capture::vi(const ultramodern::renderer::ViRegs& r, uint64_t field) {
    const auto* words = reinterpret_cast<const uint32_t*>(&r);
    nlohmann::json registers = nlohmann::json::array();
    for (size_t i = 0; i < sizeof(r) / 4; ++i) registers.push_back(words[i]);
    event({{"kind", "vi"}, {"field", field}, {"registers", registers}});
}

void Capture::finish(nlohmann::json report) {
    report["schema"] = "sc64-native-capture-v1";
    report["tasks"] = tasks_.load();
    std::ofstream output(directory_ / "report.json");
    output.exceptions(std::ios::failbit | std::ios::badbit);
    output << report.dump(2) << '\n';
}
}
