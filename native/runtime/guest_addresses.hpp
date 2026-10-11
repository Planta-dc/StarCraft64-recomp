#pragma once
#include <cstdint>

// NTSC-U guest addresses shared by the live-RAM observers and the canonical
// snapshot readers (research.md records how each was verified). Observers read
// live word-swapped RAM through the virtual address; snapshot readers index the
// canonical 8 MiB image with physical().
namespace sc64::runtime::guest {
constexpr std::uint32_t game_mode = 0x800a5ab4;     // s16: 3 mission, 4 frontend menus
constexpr std::uint32_t split_screen = 0x800afefc;  // u8: non-zero in split-screen
constexpr std::uint32_t physical(std::uint32_t virtual_address) { return virtual_address & 0x1fffffff; }
}
