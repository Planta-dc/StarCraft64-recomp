#!/usr/bin/env python3
"""Source-backed VI scale patch composed by patch_host_runtime.py.

This module transforms an already prepared events.cpp string and does not write
any dependency files. Its anchors match pinned N64ModernRuntime, independently
of the host's scheduling/capture/VI-initialization transformations.
"""
from __future__ import annotations


def replace(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"VI runtime source drift at {before[:100]!r}")
    return text.replace(before, after, 1)


def patch_vi_events(text: str) -> str:
    if '#include "vi_scale.hpp"' in text:
        raise ValueError("VI patch already applied; compose from the pinned base again")
    text = replace(text, '#include "ultramodern/renderer_context.hpp"',
        '#include "ultramodern/renderer_context.hpp"\n#include "vi_scale.hpp"')
    text = replace(text, "    int retrace_count = 1;\n};", "    int retrace_count = 1;\n    sc64::runtime::vi::Scale x;\n    sc64::runtime::vi::Scale y;\n};")
    text = replace(text, "            uint32_t yScale = field_regs->yScale;", """            const uint32_t xScale = sc64::runtime::vi::compose_x(next_state->x, next_state->state, common_regs->xScale);
            uint32_t yScale = sc64::runtime::vi::compose_y(next_state->y, next_state->state, field_regs->yScale);""")
    text = replace(text, "            regs.VI_X_SCALE_REG = common_regs->xScale; // TODO implement osViSetXScale", "            regs.VI_X_SCALE_REG = xScale;")
    text = replace(text, "            regs.VI_Y_SCALE_REG = yScale; // TODO implement osViSetYScale", "            regs.VI_Y_SCALE_REG = yScale;")
    text = replace(text, """    events_context.vi.get_next_state()->framebuffer = frameBufPtr;
}""", """    auto* next_state = events_context.vi.get_next_state();
    next_state->framebuffer = frameBufPtr;
    next_state->state |= sc64::runtime::vi::buffer_updated;
}""")
    # A mode change clears prior per-context scale overrides, black/repeatline
    # flags, and other pending state, exactly as osViSetMode does in libultra.
    text = replace(text, """    next_state->mode = mode;
    next_state->control = next_state->mode->comRegs.ctrl;
}""", """    next_state->mode = mode;
    next_state->state = sc64::runtime::vi::mode_updated;
    next_state->control = next_state->mode->comRegs.ctrl;
}""")
    text = replace(text, """extern "C" void osViSetXScale(float scale) {
    if (scale != 1.0f) {
        assert(false);
    }
}""", """extern "C" void osViSetXScale(float scale) {
    std::lock_guard lock{ events_context.message_mutex };
    auto* next_state = events_context.vi.get_next_state();
    if (next_state->mode == nullptr) throw std::logic_error("VI mode must exist before X scale");
    sc64::runtime::vi::set_x(next_state->x, next_state->state, scale, next_state->mode->comRegs.xScale);
}""")
    text = replace(text, """extern "C" void osViSetYScale(float scale) {
    if (scale != 1.0f) {
        assert(false);
    }
}""", """extern "C" void osViSetYScale(float scale) {
    std::lock_guard lock{ events_context.message_mutex };
    auto* next_state = events_context.vi.get_next_state();
    sc64::runtime::vi::set_y(next_state->y, next_state->state, scale);
}""")
    # SDK getters disable interrupts while observing the context pointers.
    text = replace(text, 'extern "C" PTR(void) osViGetNextFramebuffer() {\n',
        'extern "C" PTR(void) osViGetNextFramebuffer() {\n    std::lock_guard lock{ events_context.message_mutex };\n')
    text = replace(text, 'extern "C" PTR(void) osViGetCurrentFramebuffer() {\n',
        'extern "C" PTR(void) osViGetCurrentFramebuffer() {\n    std::lock_guard lock{ events_context.message_mutex };\n')
    return text
