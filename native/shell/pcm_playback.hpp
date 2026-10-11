#pragma once
#include "pcm_ring.hpp"
#include <algorithm>
#include <cmath>
#include <span>

namespace sc64::desktop {
// Host-only jitter buffer. Guest AI deadlines must remain independent of this
// pre-roll; otherwise buffering would change libultra's two-DMA FIFO semantics.
template<std::size_t Capacity> class PcmPlayback {
public:
    struct Result { unsigned played = 0, nonzero = 0; bool starved = false, waiting = false; };
    std::size_t size() const { return pcm_.size(); }
    bool buffering() const { return buffering_; }
    double correction() const { return correction_; }
    void rebuffer() { buffering_ = true; fade_ = 0; }
    void clear() { pcm_.clear(); phase_ = 0; buffering_ = true; fade_ = 0; correction_ = 0; }
    void push(typename PcmRing<Capacity>::Frame frame) { pcm_.push(frame); }
    void pop() { pcm_.pop(); }
    Result render(std::span<float> output, unsigned rate, unsigned pre_roll_frames = 0) {
        std::fill(output.begin(), output.end(), 0.f);
        Result result;
        // Startup and recovery wait for 60 ms, rather than repeatedly playing
        // one short DMA and starving again. The caller bounds queued storage.
        const unsigned target = pre_roll_frames ? pre_roll_frames : (rate * 60u) / 1000u;
        if (buffering_) {
            if (pcm_.size() < target + 2) { result.waiting = true; return result; }
            buffering_ = false; phase_ = 0; fade_ = 0;
        }
        const double occupancy = double(pcm_.size()) / rate;
        const double desired = std::clamp((occupancy - double(target) / rate) * .1, -.005, .005);
        // Smooth over two seconds: DMA-sized occupancy steps must not create
        // callback-sized pitch jumps, especially in sustained menu music.
        const double alpha = 1.0 - std::exp(-double(output.size() / 2) / (48000.0 * 2));
        correction_ += (desired - correction_) * alpha;
        const double step = double(rate) / 48000.0 * (1.0 + correction_);
        for (std::size_t i = 0; i < output.size() / 2; ++i) {
            if (pcm_.size() < 2) { buffering_ = true; phase_ = 0; result.starved = true; break; }
            // A short ramp avoids a hard edge when starting/recovering playback.
            fade_ = std::min(fade_ + 1, 240u);
            const float gain = float(fade_) / 240.f;
            for (unsigned c = 0; c < 2; ++c)
                output[i * 2 + c] = float(pcm_[0][c] * (1 - phase_) + pcm_[1][c] * phase_) * gain;
            ++result.played;
            if (output[i * 2] != 0 || output[i * 2 + 1] != 0) ++result.nonzero;
            phase_ += step;
            while (phase_ >= 1 && !pcm_.empty()) { pcm_.pop(); phase_ -= 1; }
        }
        return result;
    }
private:
    PcmRing<Capacity> pcm_;
    double phase_ = 0, correction_ = 0;
    bool buffering_ = true;
    unsigned fade_ = 0;
};
}
