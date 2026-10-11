// Coalesce physical touch taps and left mouse clicks before the cursor servo
// emits a controller edge. Timing belongs to the contacts, not to their delayed
// arrival at the cursor.
#include "gestures.hpp"
#include <algorithm>

namespace sc64::input::map_taps {
namespace {
bool fresh(const Info* info) {
    if (!info) return false;
    return mode_is(*info, "game") && !info->paused && info->ui_context && fresh_ui(*info);
}
bool same(const Action& action, const Info* info) {
    return fresh(info) && action.context == info->ui_context && action.token == info->ui_token;
}
void discard(GestureState& s, const std::shared_ptr<Action>& action) {
    std::erase(s.queue, action);
    if (s.active == action) {
        s.active.reset(); s.target.reset(); s.stable.reset(); s.drive.reset(); s.follow.reset();
    }
    if (s.tap == action) s.tap.reset();
}
}

void defer(GestureState& s, const std::shared_ptr<Action>& action, double field, const Info* info) {
    if (!fresh(info)) return;
    action->tap_until = field + 18; // 300 ms at the original NTSC field cadence
    action->context = info->ui_context; action->token = info->ui_token;
    s.tap = action;
}
void down(GestureState& s, Contact& contact, double field, const Info* info) {
    const auto first = s.tap;
    if (!first || field >= first->tap_until.value_or(0) || !same(*first, info)
        || (contact.x - first->x) * (contact.x - first->x) + (contact.y - first->y) * (contact.y - first->y) > 144)
        return;
    s.tap.reset();
    contact.order_tap = first; first->tap_held = true;
}
void cancel(GestureState& s, Contact& contact) {
    if (contact.order_tap) { discard(s, contact.order_tap); contact.order_tap.reset(); }
}
bool release(GestureState& s, Contact& contact, double x, double y, const Info* info) {
    const auto action = contact.order_tap;
    if (!action) return false;
    contact.order_tap.reset();
    if (!same(*action, info)) { discard(s, action); return true; }
    action->x = x; action->y = y; action->buttons = button_b; action->auto_pick = false;
    // Arrival may turn this into a same-type selection (gestures read).
    action->double_tap = true;
    action->tap_held = false; action->tap_until.reset();
    s.stable.reset();
    return true;
}
bool valid(GestureState& s, const std::shared_ptr<Action>& action, const Info& info) {
    if (!action->context) return true;
    if (!mode_is(info, "game") || info.ui_context != action->context || info.ui_token != action->token) {
        discard(s, action); return false;
    }
    return true;
}
bool ready(GestureState& s, const std::shared_ptr<Action>& action, double field, const Info& info) {
    if (action->context && !same(*action, &info)) return false;
    if (action->tap_held || (action->tap_until && field < *action->tap_until)) return false;
    if (s.tap == action) s.tap.reset();
    return true;
}
}
