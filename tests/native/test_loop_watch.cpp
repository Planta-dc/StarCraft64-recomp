// Loop-gap watch regression for D-056: long gaps are reported with the stage that
// consumed them, tagged with the window state and rate-limited; normal frames,
// resets and clock steps are silent, and the threshold tracks the UI freshness.
#include "loop_watch.hpp"
#include <cassert>
#include <string>

namespace {
constexpr std::uint64_t ms = 1'000'000;
using sc64::shell::LoopWatch;

// One iteration as app.cpp drives it: begin, then a lap per stage.
std::optional<std::string> iterate(LoopWatch& watch, std::uint64_t start, std::uint64_t tick_ms,
                                   std::uint64_t scripts_ms, std::uint64_t draw_ms, std::uint64_t present_ms,
                                   std::string_view state = {}) {
    auto report = watch.begin(start, state);
    std::uint64_t at = start;
    watch.lap(LoopWatch::tick, at += tick_ms * ms);
    watch.lap(LoopWatch::scripts, at += scripts_ms * ms);
    watch.lap(LoopWatch::draw, at += draw_ms * ms);
    watch.lap(LoopWatch::present, at += present_ms * ms);
    return report;
}
}

int main() {
    // The threshold follows the freshness window: 12 fields at the nominal 60 Hz.
    assert(LoopWatch::default_threshold_ms > 199.9 && LoopWatch::default_threshold_ms < 200.1);

    LoopWatch watch;
    assert(!iterate(watch, 1000 * ms, 1, 1, 1, 10));      // first iteration has no gap
    assert(!iterate(watch, 1017 * ms, 1, 1, 1, 10));      // 17 ms frame
    assert(!iterate(watch, 1217 * ms, 1, 1, 1, 10));      // exactly at the threshold
    // 201 ms is already enough to age the feedback; a 250 ms threshold missed it.
    assert(iterate(watch, 1418 * ms, 1, 1, 1, 10));

    // A long gap spent in present is attributed to the stage that measured it, and
    // the previous iteration's laps are what the next begin() reports.
    LoopWatch stalled;
    iterate(stalled, 10'000 * ms, 3, 0, 2, 930);
    const auto report = stalled.begin(10'000 * ms + 940 * ms, "occluded,unfocused");
    assert(report);
    assert(report->find("gap 940 ms") != std::string::npos);
    assert(report->find("tick 3,") != std::string::npos);
    assert(report->find("draw 2,") != std::string::npos);
    assert(report->find("present 930,") != std::string::npos);
    assert(report->find("outside 5)") != std::string::npos);
    assert(report->find("[occluded,unfocused]") != std::string::npos);

    // A blocked present repeats the gap each iteration: one report per interval,
    // and the next report counts what was suppressed.
    LoopWatch repeating;
    iterate(repeating, 0, 0, 0, 0, 300);
    assert(iterate(repeating, 300 * ms, 0, 0, 0, 300));    // first long gap is reported
    assert(!iterate(repeating, 600 * ms, 0, 0, 0, 300));   // 300 ms later: suppressed
    assert(!iterate(repeating, 900 * ms, 0, 0, 0, 300));
    const auto again = iterate(repeating, 1300 * ms, 0, 0, 0, 300);
    assert(again && again->find("+2 similar suppressed") != std::string::npos);

    // After a reset (minimize, Android background) the first gap is not reported.
    watch.reset();
    assert(!iterate(watch, 60'000 * ms, 1, 1, 1, 1));
    assert(iterate(watch, 61'000 * ms, 1, 1, 1, 1));       // but later gaps are
    // A non-monotonic clock never reports.
    assert(!iterate(watch, 59'000 * ms, 1, 1, 1, 1));
}
