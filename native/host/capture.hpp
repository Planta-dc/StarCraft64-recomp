#pragma once

#include <filesystem>
#include <fstream>
#include <atomic>
#include <mutex>
#include <span>
#include <string>
#include <vector>
#include <unordered_set>
#include <ultramodern/renderer_context.hpp>
#include "json/json.hpp"

namespace sc64::host {
std::string sha256(std::span<const uint8_t> bytes);
std::string sha1(std::span<const uint8_t> bytes);
void write_bytes(const std::filesystem::path& path, std::span<const uint8_t> bytes);

class Capture {
public:
    explicit Capture(const std::filesystem::path& directory);
    void event(nlohmann::json value);
    void task(uint8_t* rdram, const OSTask& task, uint64_t field);
    void vi(const ultramodern::renderer::ViRegs& registers, uint64_t field);
    void finish(nlohmann::json report);
    uint64_t task_count() const { return tasks_.load(); }
private:
    std::filesystem::path directory_;
    std::ofstream events_;
    std::mutex mutex_;
    std::atomic<uint64_t> tasks_ = 0;
    std::vector<uint8_t> canonical_;
    std::unordered_set<std::string> stored_pages_;
};
}
