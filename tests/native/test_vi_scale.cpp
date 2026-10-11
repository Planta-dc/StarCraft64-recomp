#include "vi_scale.hpp"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace vi = sc64::runtime::vi;
void require(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }
template<typename Function> void rejects(Function operation, const char* message) {
    bool threw = false;
    try { operation(); } catch (const std::exception&) { threw = true; }
    require(threw, message);
}
struct Context { vi::Scale x, y; std::uint32_t state = 0; std::uint32_t framebuffer = 0; };
int main() {
    try {
        Context contexts[2];
        int current = 0;
        auto& pending = contexts[current ^ 1];
        pending.framebuffer = 0x123456;
        require(vi::compose_x(pending.x, pending.state, 0x00100400) == 0x00100400, "default X copies nominal including offset");
        require(vi::compose_y(pending.y, pending.state, 0x02000800) == 0x02000800, "default Y copies nominal including field offset");
        vi::set_x(pending.x, pending.state, 0.5f, 0x00100400);
        require(pending.x.scale == 512, "X override computed at setter");
        vi::set_y(pending.y, pending.state, 0.7f);
        require(pending.y.scale == 0x02000800, "Y override remains deferred until context swap");
        require(vi::compose_x(pending.x, pending.state, 0x00100400) == 0x00100200, "X retains nominal subpixel offset");
        require(vi::compose_y(pending.y, pending.state, 1024) == 716, "opening animation Y scale uses float32 truncation");
        current ^= 1;
        contexts[current ^ 1] = contexts[current];
        auto& next = contexts[current ^ 1];
        require(next.framebuffer == 0x123456 && next.state == (vi::x_updated | vi::y_updated), "copied context retains state and framebuffer");
        require(vi::compose_y(next.y, next.state, 0x02000800) == 0x02000599, "alternate field recomputes nominal Y with its offset");
        vi::set_x(next.x, next.state, 2.0f, 3072);
        vi::set_y(next.y, next.state, 2.0f);
        require(vi::compose_x(next.x, next.state, 3072) == 2048, "X setter masks low 12 bits");
        require(vi::compose_y(next.y, next.state, 3072) == 6144, "Y SDK conversion has no X-style mask");
        next.state = vi::mode_updated;
        require(vi::compose_x(next.x, next.state, 819) == 819, "mode reset removes stale X override");
        require(vi::compose_y(next.y, next.state, 1638) == 1638, "mode reset removes stale Y override");
        vi::set_x(next.x, next.state, 0.12345f, 1024);
        require(next.x.scale == 126, "fractional X rounds toward zero");
        rejects([&] { vi::set_y(next.y, next.state, std::numeric_limits<float>::quiet_NaN()); }, "NaN rejected before conversion");
        rejects([&] { vi::set_x(next.x, next.state, -1.0f, 1024); }, "negative X rejected before conversion");
        rejects([&] { vi::set_x(next.x, next.state, std::numeric_limits<float>::infinity(), 1024); }, "infinite X rejected before conversion");
        rejects([&] { vi::multiply(4294967296.0f, 1); }, "u32 conversion overflow rejected");
        std::cout << "PASS: VI X/Y scale, field offsets, float32 truncation, context copies and mode reset\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
