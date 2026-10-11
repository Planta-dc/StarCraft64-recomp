#include "audio.hpp"
#include <algorithm>
#include <array>
#include <stdexcept>
#include <vector>

namespace sc64::host {
namespace {
void put32(uint8_t* p, uint32_t v) {
    for (int i = 0; i < 4; ++i) p[i] = uint8_t(v >> (i * 8));
}
}
Audio::Audio(const std::filesystem::path& path, bool silent) : path_(path), silent_(silent) {
    if (!silent_ && SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) {
        throw std::runtime_error(std::string("SDL audio initialization: ") + SDL_GetError());
    }
    wav_.open(path, std::ios::binary);
    wav_.exceptions(std::ios::failbit | std::ios::badbit);
    std::array<char, 44> header{};
    wav_.write(header.data(), header.size());
}
Audio::~Audio() {
    if (device_) SDL_CloseAudioDevice(device_);
    if (!silent_) SDL_QuitSubSystem(SDL_INIT_AUDIO);
}
void Audio::frequency(uint32_t hz) {
    std::lock_guard lock(mutex_);
    if (hz == frequency_) return;
    if (segment_samples_) {
        close_segment();
        ++segment_;
        const auto name = path_.parent_path() / (path_.stem().string() + "-" + std::to_string(segment_) + ".wav");
        wav_.open(name, std::ios::binary);
        std::array<char, 44> header{};
        wav_.write(header.data(), header.size());
        segment_samples_ = 0;
    }
    if (hz < 1000 || hz > 96000) throw std::runtime_error("Unsupported AI frequency");
    if (device_) SDL_CloseAudioDevice(device_);
    device_ = 0;
    if (!silent_) {
        SDL_AudioSpec wanted{};
        wanted.freq = int(hz);
        wanted.format = AUDIO_S16LSB;
        wanted.channels = 2;
        wanted.samples = 512;
        SDL_AudioSpec obtained{};
        device_ = SDL_OpenAudioDevice(nullptr, 0, &wanted, &obtained, 0);
        if (!device_) throw std::runtime_error(std::string("SDL audio device: ") + SDL_GetError());
        SDL_PauseAudioDevice(device_, 0);
    }
    frequency_ = hz;
    dma_ends_.clear();
}
void Audio::queue(const int16_t* input, size_t count) {
    std::lock_guard lock(mutex_);
    if (count % 2 || !frequency_) throw std::runtime_error("Invalid stereo AI buffer");
    retire_dma();
    if (dma_ends_.size() >= 2) throw std::runtime_error("AI DMA submitted to full two-buffer FIFO");
    const auto begin = dma_ends_.empty() ? std::chrono::steady_clock::now() : dma_ends_.back();
    dma_ends_.push_back(begin + std::chrono::nanoseconds((count / 2) * 1'000'000'000ull / frequency_));
    std::vector<uint8_t> pcm(count * 2);
    // MEM_H native words contain the two guest halfwords in reverse order.
    for (size_t i = 0; i < count; ++i) {
        const uint16_t sample = uint16_t(input[i ^ 1]);
        pcm[2 * i] = uint8_t(sample);
        pcm[2 * i + 1] = uint8_t(sample >> 8);
    }
    wav_.write(reinterpret_cast<const char*>(pcm.data()), pcm.size());
    sample_count_ += count;
    segment_samples_ += count;
    if (device_) {
        const uint64_t queued = SDL_GetQueuedAudioSize(device_);
        peak_queue_bytes_ = std::max(peak_queue_bytes_, queued + pcm.size());
        if (queued + pcm.size() > frequency_ * 4) {
            throw std::runtime_error("AI output queue exceeded one second");
        }
        if (SDL_QueueAudio(device_, pcm.data(), uint32_t(pcm.size())) != 0) {
            throw std::runtime_error(std::string("SDL audio queue: ") + SDL_GetError());
        }
    }
}
size_t Audio::remaining() {
    std::lock_guard lock(mutex_);
    retire_dma();
    if (dma_ends_.empty()) return 0;
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(dma_ends_.back() - std::chrono::steady_clock::now()).count();
    return ns > 0 ? (uint64_t(ns) * frequency_ + 999'999'999) / 1'000'000'000 : 0;
}
void Audio::retire_dma() {
    const auto now = std::chrono::steady_clock::now();
    while (!dma_ends_.empty() && dma_ends_.front() <= now) dma_ends_.pop_front();
}
uint32_t Audio::status() {
    std::lock_guard lock(mutex_);
    retire_dma();
    return (dma_ends_.empty() ? 0u : 0x40000000u) | (dma_ends_.size() == 2 ? 0x80000000u : 0u);
}
void Audio::close_segment() {
    if (segment_samples_ * 2 > UINT32_MAX - 36) throw std::runtime_error("WAV exceeds RIFF size");
    std::array<uint8_t, 44> header{};
    std::copy_n("RIFF", 4, header.data());
    put32(header.data() + 4, uint32_t(segment_samples_ * 2 + 36));
    std::copy_n("WAVEfmt ", 8, header.data() + 8);
    put32(header.data() + 16, 16);
    header[20] = 1; header[22] = 2;
    put32(header.data() + 24, frequency_);
    put32(header.data() + 28, frequency_ * 4);
    header[32] = 4; header[34] = 16;
    std::copy_n("data", 4, header.data() + 36);
    put32(header.data() + 40, uint32_t(segment_samples_ * 2));
    wav_.seekp(0);
    wav_.write(reinterpret_cast<const char*>(header.data()), header.size());
    wav_.close();
}
void Audio::finish() {
    std::lock_guard lock(mutex_);
    if (finished_) return;
    close_segment();
    finished_ = true;
}
}
