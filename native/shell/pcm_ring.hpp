#pragma once
#include <array>
#include <cstddef>
#include <stdexcept>

namespace sc64::desktop {
// Storage is allocated before opening the audio device. Callers synchronize
// access; removing a frame never allocates or frees a callback-time block.
template<std::size_t Capacity> class PcmRing {
public:
    using Frame = std::array<float, 2>;
    std::size_t size() const { return size_; }
    bool empty() const { return size_ == 0; }
    void clear() { begin_ = size_ = 0; }
    const Frame& operator[](std::size_t index) const {
        return frames_[(begin_ + index) % Capacity];
    }
    void push(Frame frame) {
        if (size_ == Capacity) throw std::runtime_error("PCM ring overflow");
        frames_[(begin_ + size_) % Capacity] = frame;
        ++size_;
    }
    void pop() {
        if (size_) { begin_ = (begin_ + 1) % Capacity; --size_; }
    }
private:
    static_assert(Capacity > 1);
    std::array<Frame, Capacity> frames_{};
    std::size_t begin_ = 0, size_ = 0;
};
}
