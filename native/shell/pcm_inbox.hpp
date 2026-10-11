#pragma once
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace sc64::desktop {
struct PcmFrame { float left = 0, right = 0; std::uint64_t stream = 0; };
// Producers are serialized by the guest AI mutex. The device is the sole
// consumer; release/acquire publication lets it run while a producer is
// descheduled inside the mutex. Only the consumer advances the read index.
template<std::size_t Capacity> class PcmInbox {
public:
    bool push(PcmFrame frame) {
        const auto write = write_.load(std::memory_order_relaxed);
        if (write - read_.load(std::memory_order_acquire) >= Capacity) return false;
        frames_[write % Capacity] = frame;
        write_.store(write + 1, std::memory_order_release);
        return true;
    }
    bool pop(PcmFrame& frame) {
        const auto read = read_.load(std::memory_order_relaxed);
        if (read == write_.load(std::memory_order_acquire)) return false;
        frame = frames_[read % Capacity];
        read_.store(read + 1, std::memory_order_release);
        return true;
    }
    // Producer-side occupancy; the consumer can only reduce this count.
    std::size_t pending() const {
        const auto write = write_.load(std::memory_order_relaxed);
        return write - read_.load(std::memory_order_acquire);
    }
private:
    static_assert(Capacity > 1);
    static_assert(std::atomic<std::size_t>::is_always_lock_free);
    std::array<PcmFrame,Capacity> frames_{};
    alignas(64) std::atomic<std::size_t> write_{0};
    alignas(64) std::atomic<std::size_t> read_{0};
};
}
