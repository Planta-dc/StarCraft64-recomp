// Menu clicks navigate the original selection through D-pad pulses. UI metadata
// is read-only and owned by the same frame as the image; no guest writes occur.
//
// Pulse timing was measured natively against the original menus (ADR-067): the
// frontend loop samples the pad every 2-3 VI fields, so a press must be held and
// released for at least 3 fields each; 4 adds one field of margin. The main/list
// helpers are level-triggered with a 250 ms repeat gate that a sampled release
// resets, so a hold must also stay well below 15 fields.
//
// A press is repeated when a fresh snapshot retry_fields after it still shows
// no move. Single Player tabs show an accepted press only ~21 fields later and
// ignore input for ~55 fields after a change. After cancel_fields from the first
// press of a step, the next unanswered retry window cancels instead.
//
// Two-Player is unsupported (ADR-070): one input source cannot drive both
// split-screen sides. Main-menu item 1 is its entry; menu 11 (token 267) is its
// setup screen, observed natively after that entry.
#include "gestures.hpp"
#include <algorithm>
#include <cmath>

namespace sc64::input::ui_input {
namespace {
void pulse(UiState& u, unsigned bits, double field, double x = 0, double y = 0) {
    u.bits = bits; u.until_field = field + pulse_fields;
    u.neutral_until = field + pulse_fields + neutral_fields;
    u.x_axis = x; u.y_axis = y;
}
// Both briefing screens share UI token 263. The location card runs in guest
// mode 12 and ends on Start; the text briefing (mode 4) pages with A.
bool text_briefing(const Info& info) { return mode_is(info, "briefing") && info.guest_mode == 4; }
bool location_card(const Info& info) {
    return mode_is(info, "briefing") && info.guest_mode == briefing_card_mode;
}
double distance2(double x, double y, const UiState& u) { return (x - u.x) * (x - u.x) + (y - u.y) * (y - u.y); }
}

bool active(const Info& info) { return info.ui_mode && *info.ui_mode != "game"; }

bool pointer(GestureState& s, const ContactId& id, Phase phase, double x, double y, const Info& info,
             bool right, bool is_touch) {
    if (phase == Phase::down && s.ui && s.ui->close_to) clear(s);
    if (mode_is(info, "game") || (s.ui && s.ui->hud))
        return hud_input::pointer(s, id, phase, x, y, info, right, is_touch);
    if (!active(info)) return false;
    if (!fresh_ui(info)) { clear(s); s.notice = "Waiting for interface frame"; return true; }
    if (phase == Phase::down) {
        if (s.ui && s.ui->contact && *s.ui->contact != id) {
            s.ui->contact.reset(); s.ui->target.reset();
            pulse(*s.ui, button_b, info.fields); // two-finger UI tap is Back/Cancel
            return true;
        }
        // Do not shorten a menu pulse or bypass its neutral interval with a
        // second fast tap. This also prevents adjacent swipes merging one edge.
        if (s.ui && info.fields < s.ui->neutral_until) return true;
        clear(s);
        auto u = std::make_shared<UiState>();
        u->token = info.ui_token; u->mode = info.ui_mode; u->contact = id;
        u->x = x; u->y = y; u->started = info.fields;
        if (mode_is(info, "menu") && info.ui_token == main_menu_token && inside_closed(info.ui_carousel, x, y)) {
            u->carousel = true;
            u->campaign = info.ui_carousel->selected;
        }
        // Encyclopedia article / text briefing page: a horizontal swipe turns it (original D-pad).
        u->pager = (mode_is(info, "menu") && info.ui_token == hud_buttons::encyclopedia_token)
            || text_briefing(info);
        s.ui = u;
        if (right) { pulse(*u, button_b, info.fields); u->contact.reset(); }
        return true;
    }
    const auto u = s.ui;
    if (!u || u->contact != std::optional<ContactId>(id)) return true;
    if (phase == Phase::cancel) { clear(s); return true; }
    if (phase == Phase::move) { u->max_move = std::max(u->max_move, distance2(x, y, *u)); return true; }
    if (phase != Phase::up) return true;
    u->contact.reset();
    if (u->carousel && u->token == info.ui_token && u->mode == info.ui_mode) {
        const auto& c = info.ui_carousel;
        if (!c || !c->ready || c->selected != u->campaign) { clear(s); return true; }
        const double dx = x - u->x, dy = y - u->y;
        if (std::abs(dx) >= 24 && std::abs(dx) > std::abs(dy) * 1.25) {
            // Original Left brings the right-hand campaign to the centre;
            // match that motion to dragging the carousel left on the screen.
            pulse(*u, dx < 0 ? button_left : button_right, info.fields);
        } else if (std::max(u->max_move, dx * dx + dy * dy) <= 100) {
            for (const auto& item : info.ui_items) {
                if (item.group == 5 && inside_closed(item, u->x, u->y) && inside_closed(item, x, y)) {
                    // Enter via Single Player even if a different top menu
                    // button is selected. Original A performs the transition.
                    if (item.selected) u->target = UiTarget{0, 1, std::nullopt, std::nullopt};
                    else u->target = UiTarget{item.id, 5, std::nullopt, std::nullopt};
                    break;
                }
            }
        }
        return true;
    }
    if (u->pager && u->token == info.ui_token && u->mode == info.ui_mode) {
        // Dragging left shows the next article (Right), as for the carousel.
        const double dx = x - u->x, dy = y - u->y;
        if (std::abs(dx) >= pager_swipe_pixels && std::abs(dx) > std::abs(dy) * 1.25) {
            pulse(*u, dx < 0 ? button_right : button_left, info.fields);
            return true;
        }
        // A short tap falls through to the article's link rows below.
    }
    if (u->token != info.ui_token || u->mode != info.ui_mode || std::max(u->max_move, distance2(x, y, *u)) > 100) {
        clear(s); return true;
    }
    if (mode_is(info, "results")) {
        // A selects the original Continue button; tab taps only navigate and
        // never confirm. Wait for all four decoded highlights before accepting.
        if (info.ui_items.size() != 4) { clear(s); return true; }
        bool tab_contact = false;
        for (const auto& item : info.ui_items) {
            if (item.group == 6) {
                const bool began_inside = inside_closed(item, u->x, u->y), ended_inside = inside_closed(item, x, y);
                if (began_inside && ended_inside) { u->target = UiTarget{item.id, 6, std::nullopt, std::nullopt}; return true; }
                tab_contact = tab_contact || began_inside || ended_inside;
            }
        }
        if (!tab_contact) pulse(*u, button_a, info.fields);
    } else if (mode_is(info, "campaign_warning")) {
        if (info.ui_bounds && std::max(u->max_move, distance2(x, y, *u)) <= 100) {
            const bool began_inside = inside_closed(*info.ui_bounds, u->x, u->y);
            if (began_inside == inside_closed(*info.ui_bounds, x, y))
                pulse(*u, began_inside ? button_start : button_b, info.fields);
        }
    } else if (mode_is(info, "message")) {
        u->confirm = true;
    } else if (text_briefing(info)) {
        // A shows the next page; on the last page it starts the mission.
        pulse(*u, button_a, info.fields);
    } else if (mode_is(info, "intro") || mode_is(info, "briefing")) {
        pulse(*u, button_start, info.fields);
    } else {
        for (const auto& item : info.ui_items) {
            if (inside_closed(item, x, y)) {
                if (info.ui_token == main_menu_token && item.group == 1 && item.id == two_player_item) {
                    clear(s); s.notice = two_player_notice; return true;
                }
                u->target = UiTarget{item.id, item.group, item.context, std::nullopt};
                if (item.group == 3)
                    for (const auto& tab : info.ui_items)
                        if (tab.group == 2 && tab.selected) u->target->tab = tab.id;
                return true;
            }
        }
        // The original build panel is modal. Close it with B, then replay the
        // map tap through the normal cursor/A path after a fresh game frame.
        const auto& b = info.ui_bounds;
        const auto outside = [&](double px, double py) { return b && !inside_closed(*b, px, py); };
        if (mode_is(info, "build") && outside(u->x, u->y) && outside(x, y)) u->close_to = Point{x, y};
    }
    return true;
}

std::optional<PadOutput> read(GestureState& s, const Info& info) {
    if (const auto hud_bits = hud_input::read(s, info)) return PadOutput{*hud_bits};
    const double field = info.fields;
    if (fresh_ui(info) && mode_is(info, "menu") && info.ui_token == two_player_setup_token) {
        // Leave with the original Back button, repeated until the screen
        // changes: a dropped press must not strand the user on it.
        clear(s);
        if (!s.two_player_exit) s.two_player_exit = TwoPlayerExit{field, 0};
        auto& e = *s.two_player_exit;
        if (field < e.until_field) return PadOutput{button_b};
        if (field >= e.next_field) {
            e.until_field = field + pulse_fields; e.next_field = field + retry_fields;
            s.notice = two_player_notice;
            return PadOutput{button_b};
        }
        return PadOutput{};
    }
    s.two_player_exit.reset();
    if (fresh_ui(info) && (!s.ui_observed || s.ui_observed->token != info.ui_token
                           || s.ui_observed->mode != info.ui_mode))
        s.ui_observed = UiObserved{info.ui_token, info.ui_mode, field};
    auto u = s.ui;
    if (!u && location_card(info) && fresh_ui(info) && s.ui_observed
        && field - s.ui_observed->since >= briefing_card_fields) {
        // The card never continues by itself in the original (see gestures.hpp).
        // A dropped Start is repeated once this state expires.
        u = std::make_shared<UiState>();
        u->token = info.ui_token; u->mode = info.ui_mode; u->started = field;
        s.ui = u; pulse(*u, button_start, field);
    }
    if (!u) return std::nullopt;
    if (u->close_to) {
        if (!fresh_ui(info) || field - u->started > 180
            || !(mode_is(info, "game") || (mode_is(info, "build") && info.ui_token == u->token))) {
            clear(s); return PadOutput{};
        }
        if (!u->sent_field) {
            if (!mode_is(info, "build")) { clear(s); return PadOutput{}; }
            u->sent_field = info.ui_field;
            pulse(*u, button_b, field);
            return PadOutput{button_b};
        }
        if (mode_is(info, "build")) return PadOutput{field < u->until_field ? button_b : 0};
        const double cursor_field = info.cursor_field.value_or(0);
        if (field < u->neutral_until || info.ui_field.value_or(0) <= *u->sent_field || !info.cursor_valid
            || cursor_field <= *u->sent_field || field - cursor_field > 12)
            return PadOutput{};
        const auto p = *u->close_to;
        clear(s); enqueue(s, p.x, p.y, button_a);
        return PadOutput{};
    }
    const bool campaign_target = u->target && u->target->group == 5;
    if (!fresh_ui(info) || u->token != info.ui_token || u->mode != info.ui_mode
        || field - u->started > (campaign_target ? 1080 : 360)) {
        clear(s); return PadOutput{};
    }
    if (u->contact && !u->carousel && u->mode != "campaign_warning" && u->mode != "results"
        && field - u->started >= 30) {
        s.radial = Radial{u->x, u->y, true}; u->contact.reset();
        return PadOutput{};
    }
    // Original advisor dispatch ignores keys for 750 guest-clock milliseconds.
    // Keep an early tap queued for one second of VI fields, then emit one edge.
    if (u->confirm) {
        if (field - s.ui_observed->since < 60) return PadOutput{};
        u->confirm = false; pulse(*u, button_a, field);
    }
    if (field < u->until_field) return PadOutput{u->bits, u->x_axis, u->y_axis};
    if (field < u->neutral_until) return PadOutput{};
    if (!u->target) return PadOutput{};
    if (campaign_target) {
        const auto& carousel = info.ui_carousel;
        if (!carousel || info.ui_token != main_menu_token) { clear(s); return PadOutput{}; }
        if (!carousel->ready) {
            if (u->wait && field - u->wait->field > campaign_cancel_fields) {
                clear(s); s.notice = "Campaign did not respond; click cancelled";
            }
            return PadOutput{};
        }
    }
    const UiItem* current = nullptr;
    const UiItem* target = nullptr;
    for (const auto& item : info.ui_items) {
        if (u->target->tab && item.group == 2 && item.selected && item.id != *u->target->tab) {
            clear(s); return PadOutput{};
        }
        // Encyclopedia links carry their article; a changed article cancels.
        if (item.group == u->target->group && (!u->target->context || item.context == u->target->context)) {
            if (item.selected) current = &item;
            if (item.id == u->target->id) target = &item;
        }
    }
    const double ui_field = info.ui_field.value_or(0);
    if (!current || !target) {
        // Fresh feedback without an exposed selection (e.g. a custom dialog
        // child) or without the requested item cannot be navigated. Cancel once
        // a newer snapshot agrees instead of stalling until the timeout.
        if (u->unexposed && ui_field > *u->unexposed) {
            clear(s); s.notice = "Menu item is not exposed; use the controller panel";
        } else if (!u->unexposed) u->unexposed = ui_field;
        return PadOutput{};
    }
    u->unexposed.reset();
    if (u->wait) {
        auto& w = *u->wait;
        if (ui_field <= w.field || current->id == w.id) {
            const double limit = campaign_target ? campaign_cancel_fields : cancel_fields;
            const bool unanswered = current->id == w.id && ui_field >= w.sent + retry_fields;
            if (field - w.field > limit + retry_fields || (unanswered && field - w.field > limit)) {
                clear(s); s.notice = "Menu did not respond; click cancelled";
            } else if (unanswered) {
                // The press was dropped (or the menu was still locked): repeat
                // it. A late acknowledgement causing a double move is corrected
                // by the closed-loop route from fresh feedback.
                w.sent = ui_field; w.retries += 1;
                pulse(*u, w.bits, field, w.x, w.y);
                return PadOutput{u->bits, u->x_axis, u->y_axis};
            }
            return PadOutput{};
        }
        u->wait.reset();
    }
    if (current->id == target->id) {
        u->target.reset();
        if (campaign_target) return PadOutput{}; // side clicks select; a second click enters
        if (target->activate) { pulse(*u, button_a, field); return PadOutput{button_a}; }
        return PadOutput{};
    }
    if (target->columns.value_or(0) > 0) {
        const double n = *target->columns;
        const double dx = floored_mod(target->id, n) - floored_mod(current->id, n);
        const double dy = std::floor(target->id / n) - std::floor(current->id / n);
        const double x = dx == 0 ? 0 : (dx > 0 ? .65 : -.65);
        const double y = dx != 0 ? 0 : (dy > 0 ? -.65 : .65);
        pulse(*u, 0, field, x, y);
        u->wait = UiWait{current->id, ui_field, ui_field, 0, 0, x, y};
        return PadOutput{0, x, y};
    }
    bool forward = target->id > current->id;
    // Left advances the six-entry ring. Prefer it only when that route is
    // shorter (or tied); numeric ordering takes five steps across the seam.
    if (campaign_target) forward = floored_mod(target->id - current->id, 6) <= 3;
    const unsigned bits = campaign_target ? (forward ? button_left : button_right)
        : target->horizontal ? (forward ? button_right : button_left) : (forward ? button_down : button_up);
    pulse(*u, bits, field);
    u->wait = UiWait{current->id, ui_field, ui_field, 0, bits, 0, 0};
    return PadOutput{bits};
}
}
