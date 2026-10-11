// One-to-one port of tests/test_map_taps.lua.
#include "gestures.hpp"
#include <cassert>
#include <cstdio>
#include <optional>
#include <string>
#include <utility>

using namespace sc64::input;

namespace {
Info info(double field, double x = 100, double y = 80) {
    Info i;
    i.fields = field; i.cursor_field = field; i.cursor_x = x; i.cursor_y = y;
    i.cursor_valid = true; i.cursor_divisor = 200; i.ui_mode = "game"; i.ui_field = field;
    i.ui_context = 123; i.ui_token = 3; i.pick_required = true;
    i.cursor_pick = CursorPick{.x = x, .y = y, .context = 123, .buttons = 0x8000};
    return i;
}
// Lua passes `touch~=false`: an omitted flag is a touch contact.
bool tap(GestureState& s, const ContactId& id, Phase phase, double x, double y, const Info& observed,
         bool touch = true) {
    return pointer(s, id, phase, x, y, observed.fields, touch, &observed);
}
unsigned poll(GestureState& s, const Info& observed, bool blocked = false) {
    return read(s, observed, blocked).buttons;
}
}

int main() {
    // A is withheld even when the original cursor is already at the first tap.
    // Different contact IDs, event order, guest poll cadence and second-tap jitter
    // must all coalesce to a single B edge. These are input fixtures, not game proof.
    for (int interval : {0, 4, 12, 17}) for (int poll_step : {1, 2, 5}) {
        for (int jitter : {0, 5, 9}) {
            GestureState s;
            tap(s, "1", Phase::down, 100, 80, info(100));
            tap(s, "1", Phase::up, 100, 80, info(101));
            const int second = 101 + interval;
            for (int f = 101; f <= second - 1; f += poll_step) assert(poll(s, info(f)) == 0);
            tap(s, "2", Phase::down, 100, 80, info(second));
            tap(s, "2", Phase::move, 100 + jitter, 80, info(second + 1));
            assert(!s.drag && poll(s, info(second + 1)) == 0);
            tap(s, "2", Phase::up, 100 + jitter, 80, info(second + 2));
            int edges = 0;
            unsigned previous = 0;
            for (int f = second + 2; f <= second + 30; ++f) {
                const unsigned b = poll(s, info(f, 100 + jitter, 80));
                assert((b == 0 || b == 0x4000) && "double tap must never submit A");
                if (b != 0 && previous == 0) ++edges;
                previous = b;
            }
            assert(edges == 1 && !s.active && s.queue.empty());
        }
    }
    // Cursor travel cannot consume a double tap or emit a selection on arrival.
    {
        GestureState s;
        tap(s, "1", Phase::down, 200, 90, info(100));
        tap(s, "1", Phase::up, 200, 90, info(101));
        const auto first = read(s, info(102), false); assert(first.buttons == 0 && first.x > 0);
        tap(s, "2", Phase::down, 202, 91, info(110));
        tap(s, "2", Phase::up, 202, 91, info(111));
        for (int f = 112; f <= 160; ++f) assert(poll(s, info(f)) == 0);
        // Arrival waits for a snapshot newer than the last steering input.
        std::optional<double> order;
        for (double f = 161; f <= 161 + servo.arrival_margin + 2; ++f) {
            const unsigned b = poll(s, info(f, 202, 91));
            if (b != 0) { assert(b == 0x4000 && f > 161); order = f; break; }
        }
        assert(order);
    }
    // Single taps still use the original arrival hit test (including gathering).
    for (unsigned mask : {0x8000u, 0x4000u}) {
        GestureState s;
        tap(s, "1", Phase::down, 100, 80, info(100)); tap(s, "1", Phase::up, 100, 80, info(101));
        for (int f = 101; f <= 118; ++f) assert(poll(s, info(f)) == 0);
        Info observed = info(119); observed.cursor_pick->buttons = mask;
        assert(poll(s, observed) == mask);
    }
    // A left mouse double click is recognised like a double tap (same-type select
    // or B order); a single click waits for the window; right click stays instant.
    {
        GestureState s;
        tap(s, "mouse", Phase::down, 100, 80, info(100), false);
        tap(s, "mouse", Phase::up, 100, 80, info(101), false);
        assert(s.tap && poll(s, info(101)) == 0);
        tap(s, "mouse", Phase::down, 100, 80, info(104), false);
        tap(s, "mouse", Phase::up, 100, 80, info(105), false);
        const auto order = s.active ? s.active : (s.queue.empty() ? nullptr : s.queue.front());
        assert(order && order->double_tap && order->buttons == 0x4000);
        unsigned b = 0;
        for (int f = 105; f <= 140; ++f) {
            b = poll(s, info(f)); assert(b == 0 || b == 0x4000);
            if (b != 0) break;
        }
        assert(b == 0x4000);
        GestureState single;
        tap(single, "mouse", Phase::down, 100, 80, info(100), false);
        tap(single, "mouse", Phase::up, 100, 80, info(101), false);
        for (int f = 101; f <= 118; ++f) assert(poll(single, info(f)) == 0);
        assert(poll(single, info(119)) == 0x8000);
    }
    // Distant/late taps stay two selections rather than a contextual order.
    for (const auto& c : {std::pair{20, 0}, std::pair{4, 20}}) {
        GestureState s;
        const int second = 101 + c.first;
        const double x = 100 + c.second;
        tap(s, "1", Phase::down, 100, 80, info(100)); tap(s, "1", Phase::up, 100, 80, info(101));
        tap(s, "2", Phase::down, x, 80, info(second)); tap(s, "2", Phase::up, x, 80, info(second + 1));
        int edges = 0;
        unsigned previous = 0;
        for (int f = second + 1; f <= second + 80; ++f) {
            Point target{100, 80};
            if (s.active) target = Point{s.active->x, s.active->y};
            else if (!s.queue.empty()) target = Point{s.queue.front()->x, s.queue.front()->y};
            const unsigned b = poll(s, info(f, target.x, target.y));
            assert(b == 0 || b == 0x8000);
            if (b != 0 && previous == 0) ++edges;
            previous = b;
        }
        assert(edges == 2);
    }
    // A slide of the second contact cancels its pending order before starting A.
    {
        GestureState s;
        tap(s, "1", Phase::down, 100, 80, info(100)); tap(s, "1", Phase::up, 100, 80, info(101));
        assert(poll(s, info(102)) == 0);
        tap(s, "2", Phase::down, 100, 80, info(110)); tap(s, "2", Phase::move, 120, 80, info(111));
        assert(s.drag && s.queue.size() == 1 && !s.tap);
        assert(poll(s, info(111)) == 0);
        assert(poll(s, info(112)) == 0x8000);
    }
    // Focus/ownership clears and changed selection/modal contexts cannot leave B
    // queued. Stale snapshots hold the order until fresh feedback arrives.
    for (const std::string change : {"clear", "blocked", "context", "token", "modal", "stale"}) {
        GestureState s;
        tap(s, "1", Phase::down, 100, 80, info(100)); tap(s, "1", Phase::up, 100, 80, info(101));
        tap(s, "2", Phase::down, 100, 80, info(110)); tap(s, "2", Phase::up, 100, 80, info(111));
        assert(poll(s, info(111)) == 0);
        Info observed = info(112);
        if (change == "clear") clear(s);
        else if (change == "context") observed.ui_context = 456;
        else if (change == "token") observed.ui_token = 4;
        else if (change == "modal") observed.ui_mode = "build";
        else if (change == "stale") observed.ui_field = 90;
        assert(poll(s, observed, change == "blocked") == 0);
        if (change == "stale") assert(poll(s, info(113)) == 0x4000);
        else assert(!s.tap && s.queue.empty() && !s.active);
    }
    std::puts("Double touch taps coalesce to B before cursor arrival; single/mouse/drag ownership passed");
}
