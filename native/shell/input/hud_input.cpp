// Visible original command hints are controller buttons, not terrain targets.
#include "gestures.hpp"

namespace sc64::input::hud_input {
namespace {
// HUD hints and canvas bounds are half-open: x1/y1 lie outside.
bool fresh(const Info& info) { return mode_is(info, "game") && fresh_ui(info) && !info.paused; }
bool same(const std::optional<UiItem>& a, const std::optional<UiItem>& b) {
    return a && b && a->group == 4 && b->group == 4 && a->id == b->id && a->context == b->context
        && a->label == b->label && a->buttons == b->buttons && a->x0 == b->x0 && a->y0 == b->y0
        && a->x1 == b->x1 && a->y1 == b->y1;
}
std::optional<UiItem> current(const std::optional<UiItem>& target, const Info& info) {
    if (!fresh(info)) return std::nullopt;
    for (const auto& item : info.ui_items) if (same(target, item)) return item;
    return std::nullopt;
}
std::optional<UiItem> hit(double x, double y, const Info& info) {
    if (!fresh(info)) return std::nullopt;
    for (const auto& item : info.ui_items)
        if (item.group == 4 && item.buttons.value_or(0) > 0 && inside_half_open(item, x, y)) return item;
    return std::nullopt;
}
std::optional<Bounds> region(GestureState& s, const Info& info) {
    if (!mode_is(info, "game") || info.paused) { s.hud_region.reset(); return std::nullopt; }
    if (fresh(info) && info.ui_bounds)
        s.hud_region = HudRegion{*info.ui_bounds, info.ui_context, info.ui_field.value_or(0)};
    const auto& r = s.hud_region;
    if (r && r->context == info.ui_context && info.fields - r->field >= 0
        && info.fields - r->field <= max_feedback_age)
        return r->bounds;
    s.hud_region.reset();
    return std::nullopt;
}
void freeze_hover(GestureState& s) {
    s.hover.reset();
    if (!s.active && !s.drag) { s.drive.reset(); s.stable.reset(); s.settle_until = 0; s.follow.reset(); }
}
// HUD completion owns only its UI state. A later mouse move on the map already
// belongs to the map controller and must survive the neutral gap.
void finish(GestureState& s) { s.ui.reset(); }
void cancel(UiState& u) {
    u.cancelled = true; u.pressed = false; u.pulse.reset(); u.queue.clear(); u.flash.reset();
}
double distance2(double x, double y, const UiState& u) { return (x - u.x) * (x - u.x) + (y - u.y) * (y - u.y); }
}

bool pointer(GestureState& s, const ContactId& id, Phase phase, double x, double y, const Info& info,
             bool right, bool is_touch, bool map_replay) {
    auto u = s.ui;
    // A map gesture keeps every contact, including a second finger pressed on
    // a hint. HUD ownership applies only while deciding whether this is a tap.
    if (!(u && u->hud) && (!s.contacts.empty() || s.drag || s.two || s.pan)) {
        s.hud_mouse.reset();
        return false;
    }
    const auto b = region(s, info);
    if (!is_touch && inside_half_open(b, x, y)) s.hud_mouse = Point{.x = x, .y = y};
    else s.hud_mouse.reset();
    if (!(u && u->hud) || ((phase == Phase::down || phase == Phase::move) && u->contacts.empty())) {
        const auto item = hit(x, y, info);
        if (!inside_half_open(b, x, y) && !item) {
            if (phase == Phase::down && u && u->hud) clear(s);
            return false;
        }
        freeze_hover(s);
        if (phase != Phase::down) return true;
        if (!u || !u->hud) {
            clear(s);
            u = std::make_shared<UiState>();
            u->hud = true; u->started = info.fields; u->token = info.ui_token; u->mode = "game";
            u->neutral_until = 0;
            s.ui = u;
        }
        u->contact = id; u->contacts.insert(id); u->x = x; u->y = y;
        u->origin = HudOrigin{x, y, info.fields, is_touch, right};
        u->hud_target = right ? std::nullopt : item;
        u->pressed = u->hud_target.has_value();
        if (!u->hud_target) cancel(*u); else u->cancelled = false;
        return true;
    }
    const auto origin = u->origin;
    const bool second = phase == Phase::down && std::optional<ContactId>(id) != u->contact && !u->contacts.empty();
    const bool sliding = u->contacts.contains(id) && (phase == Phase::move || phase == Phase::up)
        && distance2(x, y, *u) > 9;
    if (map_replay && origin && !origin->right && fresh(info) && info.ui_token == u->token && (second || sliding)) {
        // Replay only the uncommitted press and this event. No hint pulse or
        // terrain tap may leak from the abandoned HUD candidate.
        const auto first = u->contact.value_or(ContactId{});
        clear(s);
        input::pointer(s, first, Phase::down, origin->x, origin->y, origin->field, origin->touch);
        input::pointer(s, id, phase, x, y, info.fields, is_touch);
        if (s.two) s.two->suppress_tap = true;
        return true;
    }
    if (phase == Phase::down) {
        u->contacts.insert(id); cancel(*u);
        return true; // competing fingers cannot select terrain or issue another hint
    }
    if (!u->contacts.contains(id)) return false;
    if (!current(u->hud_target, info) || distance2(x, y, *u) > 100 || phase == Phase::cancel) cancel(*u);
    if (phase == Phase::up || phase == Phase::cancel) {
        u->contacts.erase(id);
        if (std::optional<ContactId>(id) == u->contact && !u->cancelled && same(u->hud_target, hit(x, y, info))) {
            if (u->queue.size() < 8) {
                u->queue.push_back(*u->hud_target);
                u->flash = HudPulse{*u->hud_target, info.fields + 12};
            } else s.notice = "Command queue full";
        }
        u->pressed = false;
    }
    return true;
}

std::optional<unsigned> read(GestureState& s, const Info& info) {
    const auto b = region(s, info);
    if (!s.drag && !s.two && !s.pan && s.contacts.empty() && s.hover && inside_half_open(b, s.hover->x, s.hover->y))
        freeze_hover(s);
    const auto u = s.ui;
    if (!u || !u->hud) return std::nullopt;
    bool valid = fresh(info) && info.ui_token == u->token && info.fields - u->started <= 360;
    if (u->pressed && !current(u->hud_target, info)) valid = false;
    if (u->pulse && !current(u->pulse->target, info)) valid = false;
    for (const auto& target : u->queue) if (!current(target, info)) valid = false;
    if (!valid) {
        cancel(*u);
        // Retain ownership until release, even if the selected unit disappears.
        if (u->contacts.empty()) finish(s);
        return 0u;
    }
    if (u->pulse && info.fields < u->pulse->until_field) return unsigned(u->pulse->target.buttons.value_or(0));
    u->pulse.reset();
    if (!u->queue.empty() && !u->cancelled && info.fields >= u->neutral_until) {
        const auto target = u->queue.front();
        u->queue.erase(u->queue.begin());
        u->pulse = HudPulse{target, info.fields + 6};
        u->flash = HudPulse{target, info.fields + 12};
        u->neutral_until = info.fields + 18;
        return unsigned(target.buttons.value_or(0));
    }
    if (u->queue.empty() && u->contacts.empty() && info.fields >= u->neutral_until) finish(s);
    return 0u;
}

std::optional<Feedback> feedback(GestureState& s, const Info& info) {
    const auto u = s.ui;
    if (u && u->hud) {
        if (!u->cancelled) {
            if (u->pressed && current(u->hud_target, info)) return Feedback{*u->hud_target, .3};
            if (u->flash && info.fields < u->flash->until_field && current(u->flash->target, info))
                return Feedback{u->flash->target, .3};
        }
        if (!u->contacts.empty()) return std::nullopt;
    }
    if (s.hud_mouse && inside_half_open(region(s, info), s.hud_mouse->x, s.hud_mouse->y)) {
        if (auto item = hit(s.hud_mouse->x, s.hud_mouse->y, info)) return Feedback{*item, .12};
    }
    return std::nullopt;
}
}
