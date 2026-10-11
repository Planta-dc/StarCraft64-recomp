#pragma once
#include "gfx.hpp"
#include <span>
#include <stdexcept>

namespace sc64::desktop {
// The core owns canonical big-endian bytes; librecomp owns word-swapped RAM.
// Call on the submitting guest thread before task completion is observable.
inline void commit_rdp_writes(const gfx::SoftwareResult& result,
                              std::span<std::uint8_t> word_swapped_ram) {
    if (word_swapped_ram.size()!=result.ram.size() || word_swapped_ram.size()%4)
        throw std::runtime_error("RDP writeback RAM extent mismatch");
    for (const auto& write:result.writes)
        if (write.address>result.ram.size() || write.length>result.ram.size()-write.address)
            throw std::runtime_error("RDP writeback range outside RDRAM");
    // Validate every range before mutating RAM. Never copy unrelated CPU bytes
    // from an old packet, and never infer stores by comparing byte values.
    for (const auto& write:result.writes)
        for (std::size_t a=write.address,end=a+write.length;a<end;++a)
            word_swapped_ram[a^3]=result.ram[a];
}
}
