#pragma once
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <chrono>
#include <deque>
#include <mutex>
#include <SDL.h>

namespace sc64::host {
class Audio {
public:
    Audio(const std::filesystem::path& path, bool silent);
    ~Audio();
    void frequency(uint32_t hz);
    void queue(const int16_t* swapped_samples, size_t count);
    size_t remaining();
    uint32_t status();
    void finish();
    uint64_t samples() const { std::lock_guard lock(mutex_); return sample_count_; }
    uint32_t rate() const { std::lock_guard lock(mutex_); return frequency_; }
    uint64_t peak_queue_bytes() const { std::lock_guard lock(mutex_); return peak_queue_bytes_; }
private:
    mutable std::mutex mutex_;
    std::ofstream wav_;
    SDL_AudioDeviceID device_ = 0;
    uint32_t frequency_ = 0;
    uint64_t sample_count_ = 0;
    uint64_t peak_queue_bytes_ = 0;
    uint64_t segment_samples_ = 0;
    uint32_t segment_ = 0;
    std::filesystem::path path_;
    bool silent_;
    bool finished_ = false;
    void close_segment();
    std::deque<std::chrono::steady_clock::time_point> dma_ends_;
    void retire_dma();
};
}
