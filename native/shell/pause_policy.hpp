#pragma once

namespace sc64::desktop {
struct PauseSources {
    bool requested = false, suspended = false;
    bool paused() const { return requested || suspended; }
};
struct PausePolicy {
    bool user = false, inactive = false, iconified = false, background_probe = false;
    bool in_level = false;

    void observe_mode(int guest_mode) {
        // Mode 3 includes gameplay, its build grid and mission dialogs. Keep
        // the last known mode through blank scanouts instead of unpausing a
        // level just because its presentation image temporarily disappeared.
        if (guest_mode >= 0) in_level = guest_mode == 3;
    }
    bool paused() const {
        return user || iconified || (inactive && in_level && !background_probe);
    }
    bool input_active() const {
        return !paused() && (!inactive || background_probe);
    }
};
}
