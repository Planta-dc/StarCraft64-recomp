#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>

namespace sc64::runtime {
inline constexpr std::size_t rom_size = 0x2000000;
inline constexpr std::string_view rom_sha1 = "a36d91b5aac7bb95df0d7de5f9814f5270e25c2b";

// Converts a z64/n64/v64 dump to big-endian z64 order in place.
inline void normalize_rom_byte_order(std::span<std::uint8_t> bytes) {
    if (bytes.size() != rom_size) throw std::runtime_error("Expected a 32 MiB ROM dump");
    const std::uint32_t magic = std::uint32_t(bytes[0]) << 24 | std::uint32_t(bytes[1]) << 16
        | std::uint32_t(bytes[2]) << 8 | bytes[3];
    const int lane_xor = magic == 0x80371240 ? 0 : magic == 0x37804012 ? 1 : magic == 0x40123780 ? 3 : -1;
    if (lane_xor < 0) throw std::runtime_error("Unsupported ROM byte order");
    if (!lane_xor) return;
    for (std::size_t i = 0; i < bytes.size(); i += 4) {
        const std::array<std::uint8_t, 4> word{bytes[i], bytes[i+1], bytes[i+2], bytes[i+3]};
        for (int lane = 0; lane < 4; ++lane) bytes[i+lane] = word[lane ^ lane_xor];
    }
}

// Normalizes, then requires the researched NTSC-U image. The SHA-1 provider
// differs per link profile (OpenSSL host, runtime/sha.hpp shell) and returns lowercase hex.
template<class Sha1>
void validate_rom(std::span<std::uint8_t> bytes, Sha1&& sha1) {
    normalize_rom_byte_order(bytes);
    if (std::string(sha1(std::span<const std::uint8_t>(bytes))) != rom_sha1)
        throw std::runtime_error("ROM SHA-1 does not match the researched NTSC-U revision");
}
}
