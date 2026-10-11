#pragma once

#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace sc64::runtime::vi {
// Field layout and arithmetic follow pinned libultra's __OSViScale and
// visetxscale.c / visetyscale.c / viswapcontext.c (OS 2.0J family).
inline constexpr std::uint32_t mode_updated = 0x01;
inline constexpr std::uint32_t x_updated = 0x02;
inline constexpr std::uint32_t y_updated = 0x04;
inline constexpr std::uint32_t buffer_updated = 0x10;
inline constexpr std::uint32_t scale_mask = 0x0fff;

struct Scale {
    float factor = 0.0f;
    std::uint32_t scale = 0;
};

inline void validate_factor(float factor) {
    // Retail SDK does not apply the debug-build clamps. Reject invalid host
    // conversions explicitly instead of invoking undefined C++ float-to-u32.
    if (!std::isfinite(factor) || factor < 0.0f) throw std::invalid_argument("invalid VI scale factor");
}

inline std::uint32_t multiply(float factor, std::uint32_t nominal) {
    validate_factor(factor);
    const float result = factor * static_cast<float>(nominal);
    if (!(result < 4294967296.0f)) throw std::out_of_range("VI scale conversion exceeds u32");
    return static_cast<std::uint32_t>(result);
}

inline void set_x(Scale& x, std::uint32_t& state, float factor, std::uint32_t nominal) {
    const auto computed = multiply(factor, nominal & scale_mask) & scale_mask;
    x.factor = factor;
    x.scale = computed;
    state |= x_updated;
}

inline void set_y(Scale& y, std::uint32_t& state, float factor) {
    validate_factor(factor);
    y.factor = factor;
    state |= y_updated;
}

inline std::uint32_t compose_x(Scale& x, std::uint32_t state, std::uint32_t nominal) {
    if (state & x_updated) x.scale |= nominal & ~scale_mask;
    else x.scale = nominal;
    return x.scale;
}

inline std::uint32_t compose_y(Scale& y, std::uint32_t state, std::uint32_t nominal) {
    if (state & y_updated) y.scale = multiply(y.factor, nominal & scale_mask) | (nominal & ~scale_mask);
    else y.scale = nominal;
    return y.scale;
}
}
