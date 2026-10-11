#pragma once
#include <atomic>
#include <cstdint>

namespace sc64::desktop {
// A single lane writer and the log reader share only the peak. Collecting a
// window never locks or allocates on the device callback thread.
class AudioPeak {
public:
    void record(std::uint64_t ns) {
        auto peak = peak_.load(std::memory_order_relaxed);
        while (peak < ns && !peak_.compare_exchange_weak(peak, ns, std::memory_order_relaxed)) {}
    }
    double take_ms() { return double(peak_.exchange(0, std::memory_order_relaxed)) / 1'000'000; }
private:
    static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
    std::atomic<std::uint64_t> peak_{0};
};

class AudioIntervalPeak {
public:
    void observe(std::uint64_t ns, std::uint64_t epoch) {
        if (valid_ && epoch == epoch_ && ns >= previous_) peak_.record(ns - previous_);
        previous_ = ns; epoch_ = epoch; valid_ = true;
    }
    double take_ms() { return peak_.take_ms(); }
private:
    // Only this lane's producer accesses its baseline. Changing epoch excludes
    // intentional pause/rate-change intervals even if callbacks stop entirely.
    std::uint64_t previous_ = 0, epoch_ = 0;
    bool valid_ = false;
    AudioPeak peak_;
};
}
