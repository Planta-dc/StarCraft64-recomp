#include "sha.hpp"
#include <cassert>
#include <string>
#include <vector>

namespace {
std::span<const std::uint8_t> bytes(const std::string& text) {
    return {reinterpret_cast<const std::uint8_t*>(text.data()), text.size()};
}
}

int main() {
    using namespace sc64::runtime;
    // FIPS 180-4 / NIST CAVP examples, including both padding block counts.
    assert(sha1_hex(bytes("")) == "da39a3ee5e6b4b0d3255bfef95601890afd80709");
    assert(sha1_hex(bytes("abc")) == "a9993e364706816aba3e25717850c26c9cd0d89d");
    assert(sha1_hex(bytes("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"))
           == "84983e441c3bd26ebaae4aa1f95129e5e54670f1");
    assert(sha256_hex(bytes("")) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    assert(sha256_hex(bytes("abc")) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    assert(sha256_hex(bytes("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"))
           == "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
    const std::vector<std::uint8_t> million(1000000, 'a');
    assert(sha1_hex(million) == "34aa973cd4c4daa4f61eeb2bdbad27316534016f");
    assert(sha256_hex(million) == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    // Lengths 55/56/63/64 cross the one- versus two-block padding boundary.
    assert(sha256_hex(bytes(std::string(55, 'a')))
           == "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318");
    assert(sha256_hex(bytes(std::string(56, 'a')))
           == "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a");
    assert(sha256_hex(bytes(std::string(64, 'a')))
           == "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb");
}
