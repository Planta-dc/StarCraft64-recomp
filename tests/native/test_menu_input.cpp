// Port of tests/test_menu_input.lua: campaign carousel, foreground warning,
// build grid, results tabs, ADR-067 pulse timing against a simulated original
// menu, and Encyclopedia article links.
#include "gestures.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace {
[[noreturn]] void fail(const char* file, int line, const char* expr, const std::string& note) {
    std::fprintf(stderr, "%s:%d: CHECK failed: %s%s%s\n", file, line, expr, note.empty() ? "" : " -- ",
                 note.c_str());
    std::abort();
}
}
#define CHECK(expr) do { if (!(expr)) fail(__FILE__, __LINE__, #expr, ""); } while (0)
#define CHECK_MSG(expr, note) do { if (!(expr)) fail(__FILE__, __LINE__, #expr, (note)); } while (0)

using namespace sc64::input;
namespace ui = ui_input;

namespace {
int wrap6(int value) { return ((value % 6) + 6) % 6; }

Info frame(double field) {
    Info f;
    f.fields = field; f.ui_field = field; f.ui_mode = "menu"; f.ui_token = 256;
    f.ui_carousel = Carousel{.selected = 2, .x0 = 60, .y0 = 220, .x1 = 580, .y1 = 460, .ready = true};
    f.ui_items = {
        UiItem{.id = 0, .group = 1, .x0 = 250, .y0 = 40, .x1 = 400, .y1 = 60, .selected = true, .activate = true},
        UiItem{.id = 1, .group = 5, .x0 = 60, .y0 = 220, .x1 = 180, .y1 = 400, .selected = false},
        UiItem{.id = 2, .group = 5, .x0 = 240, .y0 = 240, .x1 = 360, .y1 = 460, .selected = true},
        UiItem{.id = 3, .group = 5, .x0 = 450, .y0 = 220, .x1 = 580, .y1 = 400, .selected = false},
    };
    return f;
}

// Every ordered pair follows the shortest circular route. Readiness and
// acknowledgement still gate each step; arrival selects without pressing A.
Info campaign_frame(double field, int selected, bool ready, int target) {
    Info f = frame(field);
    f.ui_carousel->selected = selected; f.ui_carousel->ready = ready;
    f.ui_items = {f.ui_items[0]};
    for (int id = 0; id <= 5; ++id) {
        const double x0 = id == selected ? 240 : id == target ? 60 : 450;
        f.ui_items.push_back(UiItem{.id = double(id), .group = 5, .x0 = x0, .y0 = 240, .x1 = x0 + 120, .y1 = 460,
                                    .selected = id == selected, .horizontal = true, .activate = id == selected});
    }
    return f;
}

Info warning(double field) {
    Info f = frame(field);
    f.ui_mode = "campaign_warning"; f.ui_token = 900;
    f.ui_bounds = Bounds{.x0 = 160, .y0 = 222, .x1 = 480, .y1 = 388}; f.ui_carousel.reset(); f.ui_items.clear();
    return f;
}

// All build-grid routes retain grey cells as navigation acknowledgements.
// Mirrors the bridge's visible-cell export; this is a controller fixture.
Info build_frame(double field, int selected) {
    Info f = frame(field);
    f.ui_mode = "build"; f.ui_token = 300; f.ui_carousel.reset();
    f.ui_bounds = Bounds{.x0 = 230, .y0 = 143, .x1 = 310, .y1 = 223}; f.ui_items.clear();
    for (int id = 0; id <= 8; ++id) {
        const double x0 = 235 + 24 * (id % 3), y0 = 150 + 24 * (id / 3);
        f.ui_items.push_back(UiItem{.id = double(id), .group = 1, .x0 = x0, .y0 = y0, .x1 = x0 + 19, .y1 = y0 + 19,
                                    .columns = 3, .selected = id == selected, .activate = id != 3});
    }
    return f;
}

Info results_frame(double field, int selected) {
    Info f;
    f.fields = field; f.ui_field = field; f.ui_mode = "results"; f.ui_token = 700;
    static constexpr double edges[4][5] = {{232, 373, 445, 521, 592}, {232, 284, 445, 521, 592},
                                           {232, 284, 361, 521, 592}, {232, 284, 361, 443, 592}};
    const auto& e = edges[selected];
    for (int id = 0; id <= 3; ++id)
        f.ui_items.push_back(UiItem{.id = double(id), .group = 6, .x0 = e[id], .y0 = 44, .x1 = e[id + 1] - 1,
                                    .y1 = 72, .selected = id == selected, .horizontal = true, .activate = false});
    return f;
}

// ADR-067: measured pulse timing, closed-loop steps, bounded retry and
// overshoot correction against a simulated original menu. The model polls
// the pad every `poll` fields, moves on a sampled press after a sampled
// release (edge/level-with-gate equivalent), optionally drops or doubles
// selected presses, and publishes the selection `lag` fields late.
std::vector<UiItem> list_items(const std::string& kind, int n, int selected) {
    std::vector<UiItem> items;
    for (int id = 0; id < n; ++id) {
        UiItem item;
        item.id = id; item.selected = id == selected; item.activate = kind == "list";
        if (kind == "tabs") {
            item.group = 2; item.horizontal = true; item.activate = false;
            item.x0 = 80 + id * 150; item.y0 = 47; item.x1 = item.x0 + 120; item.y1 = 66;
        } else if (kind == "grid") {
            item.group = 4; item.columns = 3; item.activate = true;
            item.x0 = 232 + id % 3 * 29; item.y0 = 143 + (id / 3) * 27; item.x1 = item.x0 + 28; item.y1 = item.y0 + 26;
        } else {
            item.group = 3; item.x0 = 124; item.y0 = 134 + id * 24; item.x1 = 282; item.y1 = item.y0 + 23;
        }
        items.push_back(item);
    }
    return items;
}
std::pair<double, double> centre(const UiItem& item) {
    return {std::floor((item.x0 + item.x1) / 2), std::floor((item.y0 + item.y1) / 2)};
}

struct SimOptions {
    std::string kind;
    int n = 0, from = 0, to = 0;
    double start = 10000, lag = 3, fields = 400, poll = 3;
    std::set<int> drop;    // 1-based press numbers the menu ignores
    bool drop_all = false; // the menu ignores every press
    std::set<int> twice;   // 1-based press numbers the menu applies twice (Lua `double`)
    bool wrap = false;
    double visible = 0, lock = 0;
};
struct TraceRow { double field; unsigned bits; double x, y; };
struct SimResult {
    std::vector<TraceRow> trace;
    int selected = 0;
    std::optional<double> a_field;
    GestureState sim;
    int presses = 0;
};

SimResult simulate(const SimOptions& o) {
    SimResult result;
    GestureState& sim = result.sim;
    const double field = o.start;
    int& selected = result.selected;
    selected = o.from;
    std::vector<std::pair<double, int>> history; // {visible field, value}
    const auto snapshot = [&](double at) {
        for (auto it = history.rbegin(); it != history.rend(); ++it)
            if (it->first <= at) return it->second;
        return o.from;
    };
    const auto frame_at = [&](double at) {
        Info f;
        f.fields = at; f.ui_field = at - o.lag; f.ui_mode = "menu"; f.ui_token = 262;
        f.ui_items = list_items(o.kind, o.n, snapshot(at - o.lag));
        return f;
    };
    Info f = frame_at(field);
    const auto [tx, ty] = centre(f.ui_items[o.to]);
    CHECK(ui_pointer(sim, "1", Phase::down, tx, ty, f, false, true));
    CHECK(ui_pointer(sim, "1", Phase::up, tx, ty, f, false, true));
    bool armed = true;
    double locked_until = -1;
    const bool grid = o.kind == "grid";
    for (double at = field; at <= field + o.fields; ++at) {
        f = frame_at(at);
        const auto [bits, x, y] = read(sim, f, false);
        result.trace.push_back({at, bits, x, y});
        if (bits == 0x8000 && !result.a_field) result.a_field = at;
        int dir = 0;
        if (bits == 0x400 || y < -.5) dir = grid ? 3 : 1;
        else if (bits == 0x800 || y > .5) dir = grid ? -3 : -1;
        else if (bits == 0x100 || x > .5) dir = 1;
        else if (bits == 0x200 || x < -.5) dir = -1;
        if (floored_mod(at - field, o.poll) == 0) {
            if (dir == 0) armed = true;
            else if (armed) {
                armed = false; ++result.presses;
                if (at >= locked_until && !(o.drop_all || o.drop.contains(result.presses))) {
                    const int step = o.twice.contains(result.presses) ? 2 : 1;
                    int value = selected + dir * step;
                    if (o.wrap) value = ((value % o.n) + o.n) % o.n;
                    else value = std::max(0, std::min(o.n - 1, value));
                    selected = value;
                    history.emplace_back(at + o.visible, selected);
                    locked_until = at + o.lock;
                }
            }
        }
        if (!sim.ui) break;
    }
    return result;
}

// Lua tostring() of a number (LuaJIT formats with %.14g).
std::string lua_number(double value) {
    char text[32];
    std::snprintf(text, sizeof text, "%.14g", value);
    return text;
}

// Exact sequence: each press is held 4 fields and followed by >=4 neutral
// fields; the next step waits for fresh feedback showing the move.
struct Run { std::string key; double start; int length; bool active; };
std::vector<Run> runs(const std::vector<TraceRow>& trace) {
    std::vector<Run> out;
    for (const auto& t : trace) {
        const bool active = t.bits != 0 || t.x != 0 || t.y != 0;
        const std::string key = active ? std::to_string(t.bits) + ":" + lua_number(t.x) + ":" + lua_number(t.y) : "0";
        if (out.empty() || out.back().key != key) out.push_back({key, t.field, 0, active});
        ++out.back().length;
    }
    return out;
}
int active_runs(const std::vector<Run>& r) {
    return int(std::count_if(r.begin(), r.end(), [](const Run& run) { return run.active; }));
}

// Lua `u.bits` is nil until the menu state issues its first pulse; pulse()
// always also stamps until_field, which is otherwise never written.
bool pulsed(const UiState& u) { return u.until_field != 0; }

std::optional<unsigned> nth(const std::vector<unsigned>& v, std::size_t i) {
    return i < v.size() ? std::optional<unsigned>(v[i]) : std::nullopt;
}
std::optional<unsigned> last(const std::vector<unsigned>& v) {
    return v.empty() ? std::nullopt : std::optional<unsigned>(v.back());
}
}

int main() {
    using enum Phase;
    GestureState s;
    Info info = frame(100);
    const auto pointer = [&](Phase phase, double x, double y) { CHECK(ui_pointer(s, "1", phase, x, y, info, false, true)); };
    const auto poll = [&] { return read(s, info, false); };
    pointer(down, 400, 330); pointer(move, 300, 330); pointer(up, 300, 330);
    CHECK(poll().buttons == 0x200 && s.queue.empty());
    info = frame(106); CHECK(poll().buttons == 0);
    info = frame(118); CHECK(poll().buttons == 0); // a swipe never activates on release or afterward
    clear(s); info = frame(200);
    pointer(down, 250, 330); pointer(move, 400, 330); pointer(up, 400, 330);
    CHECK(poll().buttons == 0x100);
    clear(s); info = frame(300);
    pointer(down, 300, 330); info = frame(335); CHECK(poll().buttons == 0 && !s.radial);
    pointer(move, 280, 420); pointer(up, 280, 420);
    CHECK(poll().buttons == 0 && !s.radial); // vertical motion consumes without menu activation
    clear(s); info = frame(400);
    pointer(down, 300, 330); pointer(move, 380, 330); pointer(move, 300, 330); pointer(up, 300, 330);
    CHECK(poll().buttons == 0); // a moved contact cannot become a click by returning to its origin
    clear(s); info = frame(500);
    pointer(down, 300, 330); pointer(up, 302, 330);
    CHECK(poll().buttons == 0x8000);
    info = frame(501); info.ui_mode = "campaign_warning"; info.ui_token = 900;
    CHECK(poll().buttons == 0 && !s.ui); // no original A leaks into the new foreground dialog
    clear(s); info = frame(600); info.ui_items[0].selected = false;
    // The Lua fixture gives this entry no rectangle; it is only matched by group/id.
    info.ui_items.push_back(UiItem{.id = 2, .group = 1, .selected = true, .activate = true});
    pointer(down, 300, 330); pointer(up, 300, 330);
    CHECK(poll().buttons == 0x800);
    info = frame(618); CHECK(poll().buttons == 0x8000); // select Single Player before activating
    clear(s); info = frame(700); info.ui_carousel->ready = false;
    pointer(down, 400, 330); pointer(up, 280, 330); CHECK(poll().buttons == 0);
    clear(s); info = frame(800);
    pointer(down, 400, 330); info.ui_carousel->selected = 3;
    pointer(up, 280, 330); CHECK(poll().buttons == 0);
    clear(s); info = frame(900);
    pointer(down, 400, 330); pointer(cancel, 280, 330); CHECK(poll().buttons == 0);
    clear(s); info = frame(1000);
    pointer(down, 100, 330); pointer(up, 100, 330); CHECK(poll().buttons == 0x100);
    info = frame(1002); pointer(down, 100, 330); pointer(up, 100, 330);
    CHECK(poll().buttons == 0x100); // second tap cannot shorten the original pulse
    info = frame(1006); CHECK(poll().buttons == 0);
    info = frame(1018); CHECK(poll().buttons == 0);
    for (int current = 0; current <= 5; ++current) {
        for (int target = 0; target <= 5; ++target) {
            if (current == target) continue;
            clear(s); info = campaign_frame(1600, current, true, target);
            pointer(down, 100, 330); pointer(up, 100, 330);
            const int delta = wrap6(target - current);
            const int steps = std::min(delta, 6 - delta);
            const unsigned bits = delta <= 3 ? 0x200 : 0x100;
            const int increment = bits == 0x200 ? 1 : -1;
            int selected = current;
            CHECK(poll().buttons == bits);
            for (int step = 1; step <= steps; ++step) {
                const double start = 1600 + (step - 1) * 100;
                selected = wrap6(selected + increment);
                info = campaign_frame(start + 6, selected, false, target); CHECK(poll().buttons == 0);
                info = campaign_frame(start + 18, selected, false, target); CHECK(poll().buttons == 0);
                info = campaign_frame(start + 100, selected, true, target);
                CHECK(poll().buttons == (step < steps ? bits : 0u));
            }
            CHECK(selected == target && s.ui && !s.ui->target && s.queue.empty());
        }
    }
    clear(s); info = campaign_frame(2300, 0, true, 4);
    pointer(down, 100, 330); pointer(up, 100, 330); CHECK(poll().buttons == 0x100);
    info = campaign_frame(2400, 5, true, 4); CHECK(poll().buttons == 0x100);
    info = campaign_frame(2420, 5, false, 4); info.ui_mode = "campaign_warning"; info.ui_token = 900;
    CHECK(poll().buttons == 0 && !s.ui); // changed foreground cancels remaining steps
    clear(s); info = campaign_frame(2500, 0, true, 5);
    pointer(down, 100, 330); pointer(up, 100, 330); CHECK(poll().buttons == 0x100);
    info = campaign_frame(2681, 0, false, 5); CHECK(poll().buttons == 0 && !s.ui); // bounded animation wait
    struct WarningCase { double x, y; unsigned bits; };
    for (const auto& c : {WarningCase{320, 300, 0x1000}, WarningCase{159, 300, 0x4000},
                          WarningCase{320, 220, 0x4000}, WarningCase{160, 222, 0x1000}}) {
        clear(s); info = warning(1100);
        pointer(down, c.x, c.y); pointer(up, c.x, c.y); CHECK(poll().buttons == c.bits);
        info = warning(1106); CHECK(poll().buttons == 0);
        CHECK(s.queue.empty() && !s.radial);
    }
    clear(s); info = warning(1200);
    pointer(down, 160, 300); pointer(up, 158, 300); CHECK(poll().buttons == 0);
    clear(s); info = warning(1300);
    pointer(down, 320, 300); info = warning(1335); CHECK(poll().buttons == 0 && !s.radial);
    pointer(up, 320, 300); CHECK(poll().buttons == 0x1000);
    info.ui_token = 901; CHECK(poll().buttons == 0 && !s.ui);
    clear(s); info = warning(1400);
    pointer(down, 320, 300); info.ui_field = 1380;
    pointer(up, 320, 300); CHECK(poll().buttons == 0);
    clear(s); info = warning(1500); info.ui_bounds.reset();
    pointer(down, 320, 300); pointer(up, 320, 300); CHECK(poll().buttons == 0);
    std::puts("Campaign swipe, selected entry and foreground warning regressions passed");

    for (const bool touch : {false, true}) {
        for (int start = 0; start <= 8; ++start) for (int target = 0; target <= 8; ++target) {
            clear(s); int selected = start; double field = 3000;
            info = build_frame(field, selected);
            const double tx = 244 + 24 * (target % 3), ty = 159 + 24 * (target / 3);
            CHECK(ui_pointer(s, "1", down, tx, ty, info, false, touch));
            CHECK(ui_pointer(s, "1", up, tx, ty, info, false, touch));
            int confirms = 0;
            for (int step = 1; step <= 5; ++step) {
                const auto [bits, sx, sy] = poll();
                if (bits == 0x8000) {
                    CHECK(selected == target && target != 3 && sx == 0 && sy == 0);
                    ++confirms; break;
                }
                CHECK(bits == 0);
                CHECK(s.ui); // Lua indexes s.ui.target here; a missing state is an error
                if (!s.ui->target) break;
                CHECK((sx != 0) != (sy != 0)); // one original row/column edge per pulse
                const int before = selected;
                selected += sx != 0 ? (sx > 0 ? 1 : -1) : (sy > 0 ? -3 : 3);
                CHECK(selected >= 0 && selected <= 8);
                // Acknowledgement arrives before neutral ends; no extra step/A.
                info = build_frame(field + 6, selected); CHECK(poll().buttons == 0);
                info = build_frame(field + 18, before); CHECK(poll().buttons == 0);
                field += 20; info = build_frame(field, selected);
            }
            CHECK(selected == target && confirms == (target == 3 ? 0 : 1));
            // A second click still works after landing on a grey intermediate/target.
            info = build_frame(field + 20, selected);
            CHECK(ui_pointer(s, "1", down, 244, 159, info, false, touch));
            CHECK(ui_pointer(s, "1", up, 244, 159, info, false, touch));
            const auto [b, x, y] = poll();
            CHECK((selected == 0 && b == 0x8000) || (selected != 0 && b == 0 && (x != 0 || y != 0)));
        }
    }
    std::puts("Build grid mouse/touch routes through disabled cells passed");

    for (const bool touch : {false, true}) {
        for (int current = 0; current <= 3; ++current) for (int target = 0; target <= 3; ++target) {
            clear(s); info = results_frame(5000, current);
            const UiItem tab = info.ui_items[target];
            const double x = (tab.x0 + tab.x1) / 2;
            ui_pointer(s, "1", down, x, 55, info, false, touch);
            ui_pointer(s, "1", up, x, 55, info, false, touch);
            int selected = current;
            while (selected != target) {
                const int direction = target > selected ? 1 : -1;
                CHECK(poll().buttons == (direction == 1 ? 0x100u : 0x200u));
                info = results_frame(info.fields + 18, selected); CHECK(poll().buttons == 0);
                selected += direction; info = results_frame(info.fields + 2, selected);
            }
            CHECK(poll().buttons == 0 && s.ui && !s.ui->target && s.queue.empty());
        }
        clear(s); info = results_frame(5200, 2);
        ui_pointer(s, "1", down, 100, 200, info, false, touch);
        info = results_frame(5250, 2); CHECK(poll().buttons == 0 && !s.radial);
        ui_pointer(s, "1", up, 100, 200, info, false, touch); CHECK(poll().buttons == 0x8000);
        info = results_frame(5256, 2); CHECK(poll().buttons == 0);
        info.ui_mode = "menu"; info.ui_token = 256; CHECK(poll().buttons == 0 && !s.ui);
    }
    for (const std::string cancel_kind : {"move", "stale", "transition", "missing"}) {
        clear(s); info = results_frame(5300, 0);
        ui_pointer(s, "1", down, 100, 200, info);
        if (cancel_kind == "move") ui_pointer(s, "1", move, 140, 200, info);
        else if (cancel_kind == "stale") info.fields = 5340;
        else if (cancel_kind == "transition") info.ui_token = 701;
        else info.ui_items.clear();
        ui_pointer(s, "1", up, 100, 200, info); CHECK(poll().buttons == 0);
    }
    std::puts("Results tabs, tap-to-continue and cancellation passed");
    clear(s); info = results_frame(5400, 0);
    ui_pointer(s, "1", down, 232, 55, info);
    ui_pointer(s, "1", up, 227, 55, info);
    CHECK(poll().buttons == 0); // leaving a tab edge cannot turn its tap into Continue

    CHECK(ui::pulse_fields == 4 && ui::neutral_fields == 4 && ui::retry_fields == 30 && ui::cancel_fields == 90);
    {
        auto sim = simulate({.kind = "list", .n = 10, .from = 0, .to = 3});
        CHECK(sim.selected == 3 && sim.a_field);
        auto r = runs(sim.trace);
        const std::array<std::string, 8> expected{"1024:0:0", "0", "1024:0:0", "0", "1024:0:0", "0", "32768:0:0", "0"};
        for (std::size_t i = 0; i < expected.size(); ++i)
            CHECK_MSG(i < r.size() && r[i].key == expected[i],
                      std::to_string(i + 1) + ":" + (i < r.size() ? r[i].key : std::string("nil")));
        for (std::size_t i = 0; i <= 6; i += 2) CHECK(r[i].length == ui::pulse_fields);
        for (std::size_t i = 1; i <= 5; i += 2) CHECK(r[i].length >= ui::neutral_fields);
        // Feedback with lag 3 at poll 3 makes a step 9 fields (was >=18).
        CHECK(r[2].start - r[0].start <= 10 && r[4].start - r[2].start <= 10);
        std::printf("List steps: %d and %d fields\n", int(r[2].start - r[0].start), int(r[4].start - r[2].start));
        // Retry path: a dropped press is repeated once fresh feedback 30 fields
        // after the press is unchanged; the route still arrives without A first.
        sim = simulate({.kind = "list", .n = 10, .from = 0, .to = 2, .drop = {1}});
        CHECK(sim.selected == 2 && sim.a_field);
        r = runs(sim.trace);
        CHECK(r.size() >= 3 && r[0].key == "1024:0:0" && r[1].key == "0" && r[2].key == "1024:0:0");
        const double gap = r[2].start - r[0].start;
        CHECK_MSG(gap >= ui::retry_fields && gap <= ui::retry_fields + 6, lua_number(gap));
        // A slow acknowledgement inside the retry window never causes a re-press.
        sim = simulate({.kind = "tabs", .n = 3, .from = 0, .to = 1, .visible = 21});
        r = runs(sim.trace);
        CHECK(sim.selected == 1 && active_runs(r) == 1);
        // Tab lock: presses during ~55 locked fields are retried until accepted.
        sim = simulate({.kind = "tabs", .n = 3, .from = 0, .to = 2, .wrap = true, .visible = 21, .lock = 57});
        CHECK(sim.selected == 2);
        // Overshoot: a retry whose original press is also taken (double move) is
        // corrected by reversing from fresh feedback; A only follows on target.
        sim = simulate({.kind = "list", .n = 10, .from = 0, .to = 2, .twice = {2}});
        CHECK(sim.selected == 2 && sim.a_field);
        bool saw_up = false;
        for (const auto& t : sim.trace) if (t.bits == 0x800) saw_up = true;
        CHECK(saw_up);
        sim = simulate({.kind = "tabs", .n = 3, .from = 0, .to = 2, .twice = {1}, .wrap = true});
        CHECK(sim.selected == 2);
        // Grid routes use stick pulses and also self-correct an overshoot.
        sim = simulate({.kind = "grid", .n = 9, .from = 0, .to = 8});
        CHECK(sim.selected == 8 && sim.a_field);
        sim = simulate({.kind = "grid", .n = 9, .from = 0, .to = 5, .twice = {1}});
        CHECK(sim.selected == 5 && sim.a_field);
        // Cancellation remains a last resort: once 90 fields have passed since the
        // first press, the next unanswered retry window cancels (presses at 0/30/60).
        sim = simulate({.kind = "list", .n = 10, .from = 0, .to = 2, .drop_all = true});
        CHECK(sim.selected == 0 && !sim.a_field && !sim.sim.ui && sim.sim.notice == "Menu did not respond; click cancelled");
        r = runs(sim.trace);
        CHECK_MSG(active_runs(r) == 3, std::to_string(active_runs(r)));
        const double cancelled_at = sim.trace.back().field - sim.trace.front().field;
        CHECK_MSG(cancelled_at >= ui::cancel_fields && cancelled_at <= ui::cancel_fields + ui::retry_fields + 3,
                  lua_number(cancelled_at));
        // Live tab profile (menu-speed-nav-after-04): acknowledgement 20 fields after
        // an accepted press, ~57-field lock. Two steps still arrive without cancel.
        sim = simulate({.kind = "tabs", .n = 3, .from = 0, .to = 2, .poll = 2, .visible = 20, .lock = 57});
        CHECK_MSG(sim.selected == 2 && sim.sim.notice.empty(), sim.sim.notice);
        r = runs(sim.trace);
        std::vector<double> starts;
        std::string joined;
        for (const auto& run : r) {
            if (run.active) {
                starts.push_back(run.start - sim.trace.front().field);
                joined += (joined.empty() ? "" : " ") + lua_number(starts.back());
            }
        }
        CHECK_MSG(starts.size() == 4 && starts[1] <= 24 && starts[3] - starts[1] <= 62, joined);
    }
    // Fast repeated taps cannot shorten a pulse or merge two edges: a tap inside
    // the pulse/neutral interval is ignored, a later one starts after a zero field.
    clear(s); info = campaign_frame(20000, 0, true, 1);
    pointer(down, 100, 330); pointer(up, 100, 330); CHECK(poll().buttons == 0x200);
    for (int at = 20001; at <= 20007; ++at) {
        info = campaign_frame(at, 0, true, 1); pointer(down, 100, 330); pointer(up, 100, 330);
        const unsigned bits = poll().buttons;
        CHECK_MSG(bits == (at < 20004 ? 0x200u : 0u), std::to_string(at));
    }
    std::puts("Menu pulse timing, retry and overshoot correction passed");
    // Encyclopedia article links (group 7): tap navigates with D-pad Down/Up and
    // then follows the link with A; the article is bound by the item context.
    {
        int selected = 0;
        double article = 1000;
        const auto article_frame = [&](double field) {
            Info f;
            for (int id = 0; id <= 2; ++id)
                f.ui_items.push_back(UiItem{.id = double(id), .group = 7, .x0 = 168, .y0 = 146.0 + 16 * id, .x1 = 330,
                                            .y1 = 162.0 + 16 * id, .context = article, .selected = id == selected,
                                            .horizontal = false, .activate = true});
            f.fields = field; f.ui_field = field; f.ui_mode = "menu"; f.ui_token = 264;
            f.width = 640; f.height = 480; f.running = true;
            return f;
        };
        const auto steps = [&](double first_field) { // one closed-loop step per snapshot
            double field = first_field;
            std::vector<unsigned> bits;
            for (int i = 0; i < 12; ++i) {
                info = article_frame(field);
                const unsigned b = poll().buttons;
                if (b != 0) bits.push_back(b);
                if (b == 0x0400) selected = std::min(2, selected + 1);
                else if (b == 0x0800) selected = std::max(0, selected - 1);
                if (b == 0x8000) return bits;
                field += 8;
            }
            return bits;
        };
        clear(s); selected = 0; info = article_frame(2000);
        pointer(down, 250, 146 + 16 * 2 + 8); pointer(up, 250, 146 + 16 * 2 + 8);
        auto bits = steps(2001);
        CHECK_MSG(nth(bits, 0) == 0x0400u && nth(bits, 1) == 0x0400u && last(bits) == 0x8000u && bits.size() == 3,
                  "tap on the third link: Down, Down, A");
        // Tapping the highlighted link only presses A; Up reaches an earlier one.
        clear(s); selected = 2; info = article_frame(2200);
        pointer(down, 250, 146 + 8); pointer(up, 250, 146 + 8);
        bits = steps(2201); CHECK(nth(bits, 0) == 0x0800u && nth(bits, 1) == 0x0800u && last(bits) == 0x8000u);
        clear(s); selected = 1; info = article_frame(2400);
        pointer(down, 250, 162 + 8); pointer(up, 250, 162 + 8);
        bits = steps(2401); CHECK(bits.size() == 1 && nth(bits, 0) == 0x8000u);
        // The article changing under the tap (D-pad right, swipe) cancels it.
        clear(s); selected = 0; info = article_frame(2600);
        pointer(down, 250, 146 + 32 + 8); pointer(up, 250, 146 + 32 + 8);
        article = 2000; info = article_frame(2601);
        CHECK(poll().buttons == 0 && !(s.ui && pulsed(*s.ui)));
        article = 1000;
        // A tap outside every link row does nothing.
        clear(s); info = article_frame(2800);
        pointer(down, 100, 300); pointer(up, 100, 300);
        info = article_frame(2810); CHECK(poll().buttons == 0);
    }
    // Mission briefing (token 263): the location card runs in guest mode 12 and
    // ends on Start; the text briefing (mode 4) turns pages with A / D-pad.
    {
        const auto briefing = [](double field, double guest_mode) {
            Info f;
            f.fields = field; f.ui_field = field; f.ui_mode = "briefing"; f.ui_token = 263;
            f.guest_mode = guest_mode; f.width = 640; f.height = 480; f.running = true;
            return f;
        };
        clear(s); info = briefing(5000, 4);
        pointer(down, 320, 400); pointer(up, 320, 400);
        CHECK_MSG(poll().buttons == 0x8000, "a tap on the text briefing is A, not Start");
        info = briefing(5004, 4); CHECK(poll().buttons == 0);
        clear(s); info = briefing(5100, 4);
        pointer(down, 400, 300); pointer(move, 300, 300); pointer(up, 300, 300);
        CHECK_MSG(poll().buttons == 0x100, "drag left shows the next page (D-pad Right)");
        clear(s); info = briefing(5200, 4);
        pointer(down, 300, 300); pointer(move, 400, 300); pointer(up, 400, 300);
        CHECK_MSG(poll().buttons == 0x200, "drag right shows the previous page (D-pad Left)");
        clear(s); info = briefing(5300, 4);
        pointer(down, 300, 300); pointer(move, 300, 420); pointer(up, 300, 420);
        CHECK_MSG(poll().buttons == 0, "a vertical drag does nothing");
        clear(s); info = briefing(5400, 12);
        pointer(down, 320, 400); pointer(up, 320, 400);
        CHECK_MSG(poll().buttons == 0x1000, "a tap on the location card is Start");

        // The card continues after its display time; the text briefing never does.
        GestureState card;
        const auto at = [&](double field, double guest_mode) { info = briefing(field, guest_mode); return read(card, info, false).buttons; };
        CHECK(at(7000, 12) == 0 && at(7000 + ui::briefing_card_fields - 1, 12) == 0);
        const double due = 7000 + ui::briefing_card_fields;
        CHECK_MSG(at(due, 12) == 0x1000 && at(due + 3, 12) == 0x1000, "automatic Start after the display time");
        CHECK(at(due + 4, 12) == 0 && at(due + 100, 12) == 0);
        at(due + ui::briefing_card_fields + 1, 12); // the unanswered attempt expires
        CHECK_MSG(at(due + ui::briefing_card_fields + 2, 12) == 0x1000, "a dropped Start is repeated");
        GestureState text;
        const auto page = [&](double field) { info = briefing(field, 4); return read(text, info, false).buttons; };
        CHECK(page(8000) == 0 && page(8000 + 10 * ui::briefing_card_fields) == 0);
    }
    std::puts("Briefing location card and text page regressions passed");
}
