// Port of tests/test_hud_input.lua: HUD command hints, minimap navigation,
// cancellation, cursor policy and the HUD FIFO cadence.
#include "devices.hpp"
#include "gestures.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <utility>

namespace {
[[noreturn]] void fail(const char* file, int line, const char* expr) {
    std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", file, line, expr);
    std::abort();
}
}
#define CHECK(expr) do { if (!(expr)) fail(__FILE__, __LINE__, #expr); } while (0)

using namespace sc64::input;
namespace policy = cursor_policy;

namespace {
// The Lua fixture compared the returned hint by table identity; the owned
// C++ snapshot is compared by value.
bool same_item(const UiItem& a, const UiItem& b) {
    return a.id == b.id && a.group == b.group && a.x0 == b.x0 && a.y0 == b.y0 && a.x1 == b.x1 && a.y1 == b.y1
        && a.columns == b.columns && a.buttons == b.buttons && a.context == b.context && a.label == b.label
        && a.selected == b.selected && a.horizontal == b.horizontal && a.activate == b.activate;
}
bool is(const std::optional<Feedback>& feedback, const UiItem& item) {
    return feedback && same_item(feedback->item, item);
}
}

int main() {
    using enum Phase;
    GestureState s;
    const UiItem item{.id = 1, .group = 4, .x0 = 195, .y0 = 178, .x1 = 240, .y1 = 195, .buttons = 2, .context = 123};
    Info info;
    info.fields = 100; info.ui_field = 100; info.ui_token = 3; info.ui_mode = "game"; info.ui_items = {item};
    info.running = true; info.paused = false; info.cursor_valid = true; info.cursor_field = 100;
    info.width = 320; info.height = 240;
    const auto tick = [&](double field) {
        info.fields = field; info.ui_field = field; info.cursor_field = field;
        return read(s, info, false);
    };
    CHECK(!ui_pointer(s, "1", down, 100, 100, info)); // terrain remains owned by gestures
    CHECK(ui_pointer(s, "1", down, 220, 185, info));
    CHECK(is(ui_feedback(s, info), item) && tick(100).buttons == 0);
    CHECK(ui_pointer(s, "1", up, 220, 185, info));
    {
        const auto [bits, x, y] = tick(101);
        CHECK(bits == 2 && x == 0 && y == 0 && !s.hover); // no cursor warp or A
    }
    CHECK(is(ui_feedback(s, info), item));
    CHECK(tick(107).buttons == 0 && is(ui_feedback(s, info), item));
    CHECK(tick(113).buttons == 0 && !ui_feedback(s, info));
    tick(119); CHECK(!s.ui);
    ui_pointer(s, "1", down, 220, 185, info);
    ui_pointer(s, "1", move, 240, 185, info);
    CHECK(!ui_feedback(s, info) && !s.ui && s.drag);
    CHECK(!ui_pointer(s, "1", up, 220, 185, info));
    pointer(s, "1", up, 220, 185, info.fields, true);
    CHECK(s.drag && s.drag->released && s.queue.size() == 1 && s.queue.front()->hold);
    clear(s);
    ui_pointer(s, "1", down, 220, 185, info);
    ui_pointer(s, "2", down, 100, 100, info);
    CHECK(s.two && s.two->suppress_tap && !s.ui);
    const std::array<std::pair<ContactId, Point>, 2> points{{{"1", {220, 185}}, {"2", {100, 100}}}};
    for (const auto& [id, point] : points) {
        CHECK(!ui_pointer(s, id, up, point.x, point.y, info));
        pointer(s, id, up, point.x, point.y, info.fields, true);
    }
    CHECK(tick(122).buttons == 0 && !s.ui);
    ui_pointer(s, "1", down, 220, 185, info);
    ui_pointer(s, "1", up, 220, 185, info);
    info.ui_items = {UiItem{.id = 1, .group = 4, .x0 = 195, .y0 = 178, .x1 = 240, .y1 = 195, .buttons = 2,
                            .context = 124}};
    CHECK(!ui_feedback(s, info) && tick(123).buttons == 0 && !s.ui);
    info.ui_items = {item};
    ui_pointer(s, "1", down, 220, 185, info); info.ui_field = 100;
    CHECK(read(s, info, false).buttons == 0 && !ui_feedback(s, info));
    info.ui_field = info.fields;
    ui_pointer(s, "1", up, 220, 185, info); tick(124);
    CHECK(!s.ui); // stale press still owns its release; it cannot select terrain
    CHECK(ui_pointer(s, "1", down, 220, 185, info, true)); // right click over a hint cannot issue a terrain B
    ui_pointer(s, "1", up, 220, 185, info); CHECK(tick(125).buttons == 0);
    ui_pointer(s, "1", down, 220, 185, info); ui_pointer(s, "1", up, 220, 185, info);
    CHECK(read(s, info, true).buttons == 0 && !ui_feedback(s, info));
    const auto region = policy::region(info, 1000, 800, false);
    CHECK(region && (*region)[0] == 0 && (*region)[1] == .03125 && (*region)[2] == 1 && (*region)[3] == .96875);
    CHECK(!policy::region(info, 1000, 800, true));
    info.ui_mode = "modal"; CHECK(!policy::region(info, 1000, 800, false));
    info.ui_mode = "game"; info.paused = true; CHECK(!policy::region(info, 1000, 800, false));
    info.paused = false; info.cursor_field = 90; CHECK(!policy::region(info, 1000, 800, false));
    info.cursor_field = 123; info.width = 640; CHECK(!policy::region(info, 1000, 800, false));
    // Hover and unlabelled padding belong to the actually painted HUD canvas.
    clear(s); info.width = 320; info.ui_context = 123;
    info.ui_bounds = Bounds{.x0 = 176, .y0 = 160, .x1 = 312, .y1 = 220, .context = 123};
    tick(130); set_target(s, 220, 185);
    CHECK(tick(131).buttons == 0 && !s.hover);
    set_target(s, 100, 64);
    CHECK(ui_pointer(s, "mouse", move, 220, 185, info) && !s.hover);
    CHECK(ui_pointer(s, "1", down, 300, 215, info)); // padding cannot select hidden terrain
    ui_pointer(s, "1", up, 300, 215, info); CHECK(tick(132).buttons == 0 && s.queue.empty());
    // A missing label cancels its button, but a subsequent slide still becomes a drag.
    ui_pointer(s, "1", down, 220, 185, info); info.ui_items = {};
    CHECK(tick(133).buttons == 0 && s.ui && s.ui->contacts.contains("1"));
    CHECK(ui_pointer(s, "1", move, 100, 64, info));
    CHECK(!s.ui && s.drag && !ui_feedback(s, info));
    CHECK(!ui_pointer(s, "1", up, 100, 64, info));
    pointer(s, "1", up, 100, 64, info.fields, true);
    CHECK(s.drag && s.drag->released && s.queue.size() == 1 && s.queue.front()->hold);
    clear(s);
    // One missing present frame keeps the recently painted region protected.
    info.ui_items = {item}; tick(135); info.ui_bounds.reset();
    CHECK(ui_pointer(s, "mouse", move, 220, 185, info));
    info.fields = 148; info.ui_field = 148;
    CHECK(!ui_pointer(s, "mouse", move, 300, 215, info));
    // Two quick taps remain distinct edges with a full neutral interval.
    clear(s); tick(150);
    ui_pointer(s, "1", down, 220, 185, info); ui_pointer(s, "1", up, 220, 185, info);
    CHECK(tick(151).buttons == 2);
    ui_pointer(s, "1", down, 220, 185, info); ui_pointer(s, "1", up, 220, 185, info);
    CHECK(tick(152).buttons == 2 && tick(157).buttons == 0 && tick(168).buttons == 0 && tick(169).buttons == 2);
    CHECK(tick(175).buttons == 0); tick(187); CHECK(!s.ui);
    clear(s); info.ui_mode = "game"; info.cursor_valid = true;
    pointer(s, "mouse", down, 100, 100, 140, false);
    info.fields = 170; info.cursor_field = 170; info.ui_field = 170;
    CHECK(read(s, info, false).buttons == 0 && s.radial); // mouse can open Build/Pause without Tab
    // Minimap clicks bypass both cursor movement and A/B pulses.
    clear(s);
    info = Info{};
    info.fields = 200; info.cursor_field = 200; info.ui_field = 200; info.ui_mode = "game"; info.ui_token = 3;
    info.running = true; info.width = 320; info.height = 240; info.cursor_valid = true;
    info.minimap = Bounds{.x0 = 17, .y0 = 159, .x1 = 80, .y1 = 222, .context = 456};
    set_target(s, 100, 100);
    CHECK(ui_pointer(s, "mouse", move, 60, 200, info, false, false));
    CHECK(!s.hover && !s.minimap_request);
    CHECK(ui_pointer(s, "mouse", down, 60, 200, info, false, false));
    {
        const auto [buttons, sx, sy] = read(s, info, false);
        CHECK(buttons == 0 && sx == 0 && sy == 0 && s.queue.empty());
    }
    auto r = take_minimap(s, info);
    CHECK(r && r->x == 60 && r->y == 200 && r->context == 456 && r->field == 200);
    CHECK(!take_minimap(s, info));
    ui_pointer(s, "mouse", move, 60.5, 200.25, info, false, false);
    CHECK(!take_minimap(s, info)); // stationary pointer does not keep resetting camera/cache
    ui_pointer(s, "mouse", move, 70, 210, info, false, false);
    ui_pointer(s, "mouse", up, 70, 210, info, false, false);
    ui_pointer(s, "mouse", move, 70, 210, info, false, false);
    r = take_minimap(s, info); CHECK(r && r->x == 70 && !s.minimap && !s.hover);
    CHECK(!ui_pointer(s, "mouse", down, 80, 200, info, false, false));
    CHECK(!ui_pointer(s, "mouse", down, 60, 200, info, true, false));
    clear(s);
    ui_pointer(s, "1", down, 60, 200, info, false, true);
    CHECK(!take_minimap(s, info)); // touch commits only after an unambiguous tap
    ui_pointer(s, "1", up, 62, 201, info, false, true);
    CHECK(take_minimap(s, info));
    ui_pointer(s, "1", down, 60, 200, info, false, true);
    ui_pointer(s, "2", down, 100, 100, info, false, true);
    ui_pointer(s, "1", up, 60, 200, info, false, true);
    ui_pointer(s, "2", up, 100, 100, info, false, true);
    CHECK(!take_minimap(s, info) && !s.two && s.queue.empty());
    ui_pointer(s, "1", down, 60, 200, info, false, true);
    ui_pointer(s, "1", move, 40, 170, info, false, true);
    ui_pointer(s, "1", up, 60, 200, info, false, true);
    CHECK(!take_minimap(s, info) && !s.drag);
    ui_pointer(s, "mouse", down, 60, 200, info, false, false);
    info.minimap->context = 457;
    CHECK(!take_minimap(s, info));
    ui_pointer(s, "mouse", up, 60, 200, info, false, false);
    ui_pointer(s, "mouse", down, 60, 200, info, false, false);
    info.fields = 213;
    CHECK(!take_minimap(s, info));
    clear(s); CHECK(!ui_pointer(s, "1", down, 60, 200, info));
    info.fields = 200; info.paused = true;
    CHECK(!ui_pointer(s, "1", down, 60, 200, info));
    info.paused = false; info.width = 640;
    CHECK(!ui_pointer(s, "1", down, 60, 200, info));
    info.width = 320; info.minimap.reset();
    CHECK(!ui_pointer(s, "1", down, 60, 200, info));
    info.minimap = Bounds{.x0 = 17, .y0 = 159, .x1 = 80, .y1 = 222, .context = 456};
    // A completed HUD hint cannot mask a new minimap click.
    s.ui = std::make_shared<UiState>(); s.ui->hud = true;
    CHECK(ui_pointer(s, "1", down, 60, 200, info));
    CHECK(take_minimap(s, info) && !s.ui);
    read(s, info, true); CHECK(!s.minimap);
    std::puts("HUD, minimap navigation, cancellation and cursor policy passed");

    // Three rapid taps preserve all edges and the complete twelve-field release gap.
    clear(s); info.ui_items = {item}; tick(200);
    const auto tap = [&] {
        CHECK(ui_pointer(s, "1", down, 220, 185, info));
        CHECK(ui_pointer(s, "1", up, 220, 185, info));
    };
    tap(); CHECK(tick(200).buttons == 2);
    CHECK(tick(206).buttons == 0); tick(207); tap(); CHECK(tick(207).buttons == 0);
    tick(214); tap(); CHECK(tick(214).buttons == 0);
    for (double field = 215; field <= 217; ++field) CHECK(tick(field).buttons == 0);
    for (double field = 218; field <= 223; ++field) CHECK(tick(field).buttons == 2);
    for (double field = 224; field <= 235; ++field) CHECK(tick(field).buttons == 0);
    for (double field = 236; field <= 241; ++field) CHECK(tick(field).buttons == 2);
    CHECK(tick(242).buttons == 0); tick(254); CHECK(!s.ui);
    // Completion does not discard a map hover received during the cooldown.
    clear(s); tick(300); tap(); CHECK(tick(301).buttons == 2); CHECK(tick(307).buttons == 0);
    CHECK(!ui_pointer(s, "mouse", move, 150, 80, info));
    pointer(s, "mouse", move, 150, 80, 307, false);
    CHECK(s.hover && s.hover->x == 150 && s.hover->y == 80);
    CHECK(tick(308).buttons == 0); tick(319);
    CHECK(!s.ui && s.hover && s.hover->x == 150 && s.hover->y == 80);
    // A changed hint cancels the entire FIFO rather than issuing stale orders.
    clear(s); tick(400); tap(); tick(400); tick(407); tap(); tick(414); tap();
    info.ui_items = {}; CHECK(tick(415).buttons == 0 && !s.ui);
    std::puts("HUD FIFO cadence, stale queue cancellation and map hover preservation passed");
}
