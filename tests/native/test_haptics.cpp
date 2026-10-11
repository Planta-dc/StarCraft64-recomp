// One-to-one port of tests/test_haptics.lua.
#include "devices.hpp"
#include <cassert>
#include <cstdio>

int main() {
    using namespace sc64::input;
    haptics::State s;
    // Rising pointer A edge pulses once; holding it does not repeat.
    auto pulse = haptics::update(s, 0x8000, true, 1);
    assert(pulse && pulse->milliseconds == 12 && pulse->amplitude == 90);
    assert(!haptics::update(s, 0x8000, true, 2));
    // B order outranks A on the same edge and is stronger.
    haptics::update(s, 0, true, 3);
    pulse = haptics::update(s, 0xC000, true, 4);
    assert(pulse && pulse->milliseconds == 22 && pulse->amplitude == 170);
    // Keyboard/gamepad presses never vibrate, but still update edge state.
    haptics::update(s, 0, false, 5);
    assert(!haptics::update(s, 0x4000, false, 6));
    assert(!haptics::update(s, 0x4000, true, 7) && "held controller B is not a new pointer edge");
    // Pulses closer than MIN_GAP coalesce.
    haptics::update(s, 0, true, 8);
    assert(haptics::update(s, 0x8000, true, 8.01));
    haptics::update(s, 0, true, 8.02);
    assert(!haptics::update(s, 0x8000, true, 8.03));
    assert(!haptics::update(s, 0, true, 9));
    assert(haptics::update(s, 0x8000, true, 9.1));
    // Non-confirmation buttons (stick, C, Z) do not vibrate.
    haptics::update(s, 0, true, 10);
    assert(!haptics::update(s, 0x2000, true, 11));
    std::puts("haptics ok");
}
