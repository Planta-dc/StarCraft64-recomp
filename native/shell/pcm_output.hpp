#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <span>

namespace sc64::desktop {
// Keep a backend's callback-size choice from becoming a stack/allocation limit.
template<class Mix> void render_pcm16(std::span<std::int16_t> stereo, Mix mix) {
    std::array<float,2048> scratch;
    for (std::size_t offset=0;offset<stereo.size();) {
        const auto count=std::min(stereo.size()-offset,scratch.size());
        mix(scratch.data(),unsigned(count/2));
        for (std::size_t i=0;i<count;++i)
            stereo[offset+i]=std::int16_t(std::clamp(scratch[i]*32768.f,-32768.f,32767.f));
        offset+=count;
    }
}
}
