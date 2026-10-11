// Detects main-loop gaps long enough to age the guest's UI feedback past the
// freshness window (D-056). Pure arithmetic: the shell supplies monotonic times.
#pragma once
#include "input/info.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <optional>
#include <string>
#include <string_view>

namespace sc64::shell {

class LoopWatch {
public:
    enum Stage { tick, scripts, draw, present, stage_count };
    // D-016: nominal 60 Hz field. Feedback older than input::max_feedback_age
    // fields is stale, so a menu click after a longer gap is dropped as
    // "Waiting for interface frame".
    static constexpr double field_ms = 1000.0 / 60;
    static constexpr double default_threshold_ms = input::max_feedback_age * field_ms;
    // A blocked present (occluded window) repeats the gap every iteration.
    static constexpr double default_report_interval_ms = 1000;

    explicit LoopWatch(double threshold_ms = default_threshold_ms,
                       double report_interval_ms = default_report_interval_ms)
        : threshold_ms_(threshold_ms), report_interval_ms_(report_interval_ms) {}

    // Start of an iteration. Returns a report when the gap since the previous
    // start exceeded the threshold, attributing it to the previous iteration's
    // stages; `state` describes the window (for example "occluded").
    std::optional<std::string> begin(std::uint64_t now_ns, std::string_view state = {}) {
        const auto last = last_;
        last_ = mark_ = now_ns;
        if (!last || now_ns < *last) return std::nullopt;
        const double gap = ms(now_ns - *last);
        if (gap <= threshold_ms_) return std::nullopt;
        if (reported_ && ms(now_ns - *reported_) < report_interval_ms_) {
            ++suppressed_;
            return std::nullopt;
        }
        std::uint64_t used = 0;
        for (const auto ns : stages_) used += ns;
        const double outside = gap - ms(used); // events and SDL between iterations
        char text[256];
        int length = std::snprintf(text, sizeof text,
            "SC64 loop gap %.0f ms (tick %.0f, scripts %.0f, draw %.0f, present %.0f, outside %.0f)", gap,
            ms(stages_[tick]), ms(stages_[scripts]), ms(stages_[draw]), ms(stages_[present]),
            outside < 0 ? 0 : outside);
        std::string report(text, std::size_t(length < 0 ? 0 : length < int(sizeof text) ? length : int(sizeof text) - 1));
        if (!state.empty()) report += " [" + std::string(state) + "]";
        if (suppressed_) report += " +" + std::to_string(suppressed_) + " similar suppressed";
        suppressed_ = 0;
        reported_ = now_ns;
        return report;
    }
    // Close `stage` at `now_ns`: its duration runs from the previous lap or begin().
    void lap(Stage stage, std::uint64_t now_ns) {
        stages_[stage] = now_ns >= mark_ ? now_ns - mark_ : 0;
        mark_ = now_ns;
    }
    // Lifecycle transitions (minimize, Android background) stop the loop by design.
    void reset() { last_.reset(); reported_.reset(); suppressed_ = 0; }

private:
    static double ms(std::uint64_t ns) { return double(ns) / 1e6; }

    double threshold_ms_, report_interval_ms_;
    std::array<std::uint64_t, stage_count> stages_{}; // nanoseconds, previous iteration
    std::uint64_t mark_ = 0;
    std::optional<std::uint64_t> last_, reported_;
    unsigned suppressed_ = 0;
};

} // namespace sc64::shell
