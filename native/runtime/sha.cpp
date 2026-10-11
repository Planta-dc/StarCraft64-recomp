#include "sha.hpp"
#include <bit>

namespace sc64::runtime {
namespace {
// Shared Merkle-Damgard padding: 64-byte blocks, big-endian 64-bit bit length.
template <typename Compress>
void blocks(std::span<const std::uint8_t> bytes, Compress compress) {
    std::size_t offset = 0;
    for (; offset + 64 <= bytes.size(); offset += 64) compress(bytes.data() + offset);
    std::array<std::uint8_t, 128> tail{};
    const std::size_t rest = bytes.size() - offset;
    for (std::size_t i = 0; i < rest; ++i) tail[i] = bytes[offset + i];
    tail[rest] = 0x80;
    const std::size_t length = rest + 1 + 8 <= 64 ? 64 : 128;
    const std::uint64_t bits = std::uint64_t(bytes.size()) * 8;
    for (int i = 0; i < 8; ++i) tail[length - 1 - i] = std::uint8_t(bits >> (8 * i));
    compress(tail.data());
    if (length == 128) compress(tail.data() + 64);
}
std::uint32_t load(const std::uint8_t* p) {
    return std::uint32_t(p[0]) << 24 | std::uint32_t(p[1]) << 16 | std::uint32_t(p[2]) << 8 | p[3];
}
template <std::size_t N>
std::array<std::uint8_t, N * 4> store(const std::array<std::uint32_t, N>& words) {
    std::array<std::uint8_t, N * 4> result{};
    for (std::size_t i = 0; i < N; ++i)
        for (int b = 0; b < 4; ++b) result[i * 4 + b] = std::uint8_t(words[i] >> (24 - 8 * b));
    return result;
}
template <std::size_t N>
std::string hex(const std::array<std::uint8_t, N>& digest) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string result;
    result.reserve(N * 2);
    for (auto byte : digest) { result += digits[byte >> 4]; result += digits[byte & 15]; }
    return result;
}
constexpr std::array<std::uint32_t, 64> k256 = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
}

std::array<std::uint8_t, 20> sha1_digest(std::span<const std::uint8_t> bytes) {
    std::array<std::uint32_t, 5> h = {0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0};
    blocks(bytes, [&](const std::uint8_t* block) {
        std::array<std::uint32_t, 80> w{};
        for (int i = 0; i < 16; ++i) w[i] = load(block + 4 * i);
        for (int i = 16; i < 80; ++i) w[i] = std::rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
        auto [a, b, c, d, e] = h;
        for (int i = 0; i < 80; ++i) {
            std::uint32_t f, k;
            if (i < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
            else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
            else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
            else { f = b ^ c ^ d; k = 0xca62c1d6; }
            const std::uint32_t t = std::rotl(a, 5) + f + e + k + w[i];
            e = d; d = c; c = std::rotl(b, 30); b = a; a = t;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e;
    });
    return store(h);
}

std::array<std::uint8_t, 32> sha256_digest(std::span<const std::uint8_t> bytes) {
    std::array<std::uint32_t, 8> h = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    blocks(bytes, [&](const std::uint8_t* block) {
        std::array<std::uint32_t, 64> w{};
        for (int i = 0; i < 16; ++i) w[i] = load(block + 4 * i);
        for (int i = 16; i < 64; ++i) {
            const auto s0 = std::rotr(w[i - 15], 7) ^ std::rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            const auto s1 = std::rotr(w[i - 2], 17) ^ std::rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        auto [a, b, c, d, e, f, g, hh] = h;
        for (int i = 0; i < 64; ++i) {
            const auto t1 = hh + (std::rotr(e, 6) ^ std::rotr(e, 11) ^ std::rotr(e, 25))
                + ((e & f) ^ (~e & g)) + k256[i] + w[i];
            const auto t2 = (std::rotr(a, 2) ^ std::rotr(a, 13) ^ std::rotr(a, 22))
                + ((a & b) ^ (a & c) ^ (b & c));
            hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
    });
    return store(h);
}

std::string sha1_hex(std::span<const std::uint8_t> bytes) { return hex(sha1_digest(bytes)); }
std::string sha256_hex(std::span<const std::uint8_t> bytes) { return hex(sha256_digest(bytes)); }
}
