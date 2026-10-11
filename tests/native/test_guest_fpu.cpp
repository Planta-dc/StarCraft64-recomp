#include "guest_fpu.hpp"
#include "recomp.h"
#include <cassert>
#include <bit>
#include <cmath>
#include <cstdio>
#include <thread>

SET_FENV_ACCESS()

namespace {
void rounding_and_conversion() {
    const int positive[] = {2, 1, 2, 1}, negative[] = {-2, -1, -1, -2};
    const std::uint32_t single_pos[] = {0x3f800000, 0x3f800000, 0x3f800001, 0x3f800000};
    const std::uint32_t single_neg[] = {0xbf800000, 0xbf800000, 0xbf800000, 0xbf800001};
    const std::uint64_t double_pos[] = {
        0x3ff0000000000000, 0x3ff0000000000000, 0x3ff0000000000001, 0x3ff0000000000000};
    const std::uint64_t double_neg[] = {
        0xbff0000000000000, 0xbff0000000000000, 0xbff0000000000000, 0xbff0000000000001};
    for (unsigned mode = 0; mode < 4; ++mode) {
        set_cop1_cs(mode);
        assert(get_cop1_cs() == mode);
        volatile float ps = 1.75f, ns = -1.75f;
        volatile double pd = 1.75, nd = -1.75;
        assert(CVT_W_S(ps) == positive[mode] && CVT_W_S(ns) == negative[mode]);
        assert(CVT_W_D(pd) == positive[mode] && CVT_W_D(nd) == negative[mode]);
        const auto pl = CVT_L_S(ps);
        const auto nl = CVT_L_S(ns);
        assert(pl == positive[mode] && nl == negative[mode]);
        assert(CVT_L_D(pd) == positive[mode] && CVT_L_D(nd) == negative[mode]);
        assert(TRUNC_W_S(ps) == 1 && TRUNC_W_S(ns) == -1);
        assert(TRUNC_W_D(pd) == 1 && TRUNC_W_D(nd) == -1);
        assert(TRUNC_L_S(ps) == 1 && TRUNC_L_S(ns) == -1);
        assert(TRUNC_L_D(pd) == 1 && TRUNC_L_D(nd) == -1);

        // Exact halfway operands catch compiler folding or a leaked default
        // mode. Integer expectations are independent of the helper result.
        volatile float one_s = 1.0f, half_s = 0x1p-24f;
        volatile double one_d = 1.0, half_d = 0x1p-53;
        assert(std::bit_cast<std::uint32_t>(float(one_s + half_s)) == single_pos[mode]);
        assert(std::bit_cast<std::uint32_t>(float(-one_s - half_s)) == single_neg[mode]);
        assert(std::bit_cast<std::uint64_t>(double(one_d + half_d)) == double_pos[mode]);
        assert(std::bit_cast<std::uint64_t>(double(-one_d - half_d)) == double_neg[mode]);
        volatile double narrow_pos = 0x1.000001p0, narrow_neg = -0x1.000001p0;
        assert(std::bit_cast<std::uint32_t>(CVT_S_D(narrow_pos)) == single_pos[mode]);
        assert(std::bit_cast<std::uint32_t>(CVT_S_D(narrow_neg)) == single_neg[mode]);
        volatile std::int32_t integer_pos = 16777217, integer_neg = -16777217;
        assert(CVT_S_W(integer_pos) == (mode == 2 ? 16777218.0f : 16777216.0f));
        assert(CVT_S_W(integer_neg) == (mode == 3 ? -16777218.0f : -16777216.0f));
    }
}

void exceptional_values() {
    sc64::runtime::initialize_guest_fpu();
    volatile float single_min = std::bit_cast<float>(std::uint32_t(0x00800000)), half_s = .5f;
    volatile double double_min = std::bit_cast<double>(std::uint64_t(0x0010000000000000)), half_d = .5;
    assert(std::bit_cast<std::uint32_t>(MUL_S(single_min, half_s)) == 0x00400000);
    assert(std::bit_cast<std::uint64_t>(MUL_D(double_min, half_d)) == 0x0008000000000000);
    volatile float single_sub = std::bit_cast<float>(std::uint32_t(1)), two_s = 2.0f;
    volatile double double_sub = std::bit_cast<double>(std::uint64_t(1)), two_d = 2.0;
    assert(std::bit_cast<std::uint32_t>(MUL_S(single_sub, two_s)) == 2);
    assert(std::bit_cast<std::uint64_t>(MUL_D(double_sub, two_d)) == 2);
    volatile float minus_zero = std::bit_cast<float>(std::uint32_t(0x80000000));
    assert(std::bit_cast<std::uint32_t>(MUL_S(minus_zero, two_s)) == 0x80000000);
    assert(std::bit_cast<std::uint64_t>(CVT_D_S(minus_zero)) == 0x8000000000000000);
    volatile double minus_zero_d = std::bit_cast<double>(std::uint64_t(0x8000000000000000));
    assert(std::bit_cast<std::uint32_t>(CVT_S_D(minus_zero_d)) == 0x80000000);
    volatile float nan = std::bit_cast<float>(std::uint32_t(0x7fc12345));
    assert(nan != nan && !(nan < two_s) && !(nan == two_s));
    assert(std::isnan(MUL_S(nan, two_s)));
    assert(get_cop1_cs() == 0);
}

void thread_isolation() {
    set_cop1_cs(3);
#if defined(__aarch64__)
    std::uint64_t parent;
    asm volatile("mrs %0, fpcr" : "=r"(parent));
    // Seed modes affecting the guest's 32/64-bit arithmetic. FZ16 is checked
    // after guest initialization but is not a guest arithmetic mode.
    parent |= (1ull << 24) | (1ull << 25);
    // Optional FPCR fields can be read-as-zero on a CPU without the feature.
    // Compare the latched parent state, rather than the requested bit pattern.
    asm volatile("msr fpcr, %0\nisb\nmrs %0, fpcr" : "+r"(parent));
#endif
    std::thread worker([] {
        sc64::runtime::initialize_guest_fpu();
        assert(get_cop1_cs() == 0);
#if defined(__aarch64__)
        std::uint64_t fpcr;
        asm volatile("mrs %0, fpcr" : "=r"(fpcr));
        assert((fpcr & ((1ull << 24) | (1ull << 25) | (1ull << 19))) == 0);
#endif
        rounding_and_conversion();
        exceptional_values();
    });
    worker.join();
    assert(get_cop1_cs() == 3);
#if defined(__aarch64__)
    std::uint64_t after;
    asm volatile("mrs %0, fpcr" : "=r"(after));
    if (after != parent) std::fprintf(stderr, "FPCR parent=%llx after=%llx\n",
        static_cast<unsigned long long>(parent), static_cast<unsigned long long>(after));
    assert(after == parent);
#endif
}
}

int main() {
    fenv_t original;
    assert(fegetenv(&original)==0);
    sc64::runtime::initialize_guest_fpu();
    rounding_and_conversion();
    exceptional_values();
    thread_isolation();
    assert(fesetenv(&original)==0);
    std::puts("SC64 guest FPU: rounding, arithmetic, conversions, subnormals, signed zero, NaN and thread isolation passed");
}
