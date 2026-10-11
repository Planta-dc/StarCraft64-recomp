#pragma once
#include <chrono>

namespace sc64::desktop {
// Maps the guest Rumble Pak motor onto one-shot device vibrations. A running
// motor is re-armed before its burst expires; it stops when the guest stops it
// or when haptics are disabled, the game pauses or the app is inactive.
class RumbleMotor {
public:
    using Clock = std::chrono::steady_clock;
    static constexpr int burst_ms = 5000;
    static constexpr auto rearm = std::chrono::milliseconds(4000);
    static constexpr int amplitude = 200;
    static constexpr int none = -1;
    // Returns the vibration length to request: > 0 starts/re-arms, 0 stops,
    // none leaves the device unchanged.
    int update(bool wanted, Clock::time_point now) {
        if (!wanted) {
            if (!on_) return none;
            on_ = false;
            return 0;
        }
        if (on_ && now - armed_ < rearm) return none;
        on_ = true;
        armed_ = now;
        return burst_ms;
    }
    bool on() const { return on_; }
private:
    bool on_ = false;
    Clock::time_point armed_{};
};
}
