#pragma once
#include <algorithm>
#include <cstdint>
#include <span>
#include <vector>

namespace sc64::desktop {
// Optional private diagnostic. Allocate before starting either producer, then
// give each lane exactly one writer; export only after both threads stop.
class PcmTraceLane {
public:
    struct Block {
        std::uint64_t field = 0, stream = 0;
        double seconds = 0, correction = 0;
        std::size_t offset = 0, frames = 0;
        unsigned rate = 0, played = 0;
        bool starved = false;
    };
    void initialize(std::size_t frames) {
        samples_.resize(frames * 2);
        blocks_.resize(4096);
        samples_used_ = blocks_used_ = 0; truncated_ = false;
    }
    template<class Sample> void append(Block block, std::size_t frames, Sample sample) {
        if (blocks_used_ == blocks_.size()) { truncated_ = true; return; }
        const auto n = std::min(frames, (samples_.size() - samples_used_) / 2);
        if (n != frames) truncated_ = true;
        if (!n) return;
        block.offset = samples_used_ / 2; block.frames = n;
        blocks_[blocks_used_++] = block;
        for (std::size_t i = 0; i < n * 2; ++i) samples_[samples_used_++] = sample(i);
    }
    std::span<const float> samples() const { return {samples_.data(), samples_used_}; }
    std::span<const Block> blocks() const { return {blocks_.data(), blocks_used_}; }
    bool truncated() const { return truncated_; }
private:
    std::vector<float> samples_;
    std::vector<Block> blocks_;
    std::size_t samples_used_ = 0, blocks_used_ = 0;
    bool truncated_ = false;
};
}
