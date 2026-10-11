#pragma once
#include <cfenv>
#include <cstdint>
#include <stdexcept>
#if defined(__x86_64__) || defined(_M_X64)
#include <xmmintrin.h>
#endif

namespace sc64::runtime {
// Guest workers own their floating-point environment. Never call this on the
// shell main or audio callback thread: the guest changes its rounding mode later.
inline void initialize_guest_fpu() {
    if (std::fesetenv(FE_DFL_ENV) != 0) throw std::runtime_error("Guest FPU initialization failed");
#if defined(__aarch64__)
    std::uint64_t fpcr;
    asm volatile("mrs %0, fpcr" : "=r"(fpcr));
    fpcr &= ~((1ull << 24) | (1ull << 25) | (1ull << 19)); // FZ, DN, FZ16
    asm volatile("msr fpcr, %0\nisb" : : "r"(fpcr));
#elif defined(__x86_64__) || defined(_M_X64)
    _mm_setcsr(_mm_getcsr() & ~(0x8000u | 0x0040u)); // FTZ, DAZ
#endif
}
}
