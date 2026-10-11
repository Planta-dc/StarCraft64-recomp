#pragma once
#include <array>
#include <cstdint>
#include <span>
#include <string>

namespace sc64::runtime {
// FIPS 180-4 digests for ROM, microcode and fixture identity. These replace
// platform crypto libraries; they are integrity checks, not security controls.
std::array<std::uint8_t, 20> sha1_digest(std::span<const std::uint8_t> bytes);
std::array<std::uint8_t, 32> sha256_digest(std::span<const std::uint8_t> bytes);
std::string sha1_hex(std::span<const std::uint8_t> bytes);
std::string sha256_hex(std::span<const std::uint8_t> bytes);
}
