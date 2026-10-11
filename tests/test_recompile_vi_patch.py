from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sc64_vi_patch", ROOT / "tools/recompile/patch_vi_runtime.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ViPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = ROOT / "third_party/N64ModernRuntime/ultramodern/src/events.cpp"
        if not cls.source.is_file():
            raise unittest.SkipTest("pinned runtime unavailable")

    def test_scale_patch_drift_and_double_application_rejected(self) -> None:
        patched = MODULE.patch_vi_events(self.source.read_text())
        self.assertIn("sc64::runtime::vi::compose_y", patched)
        self.assertIn("next_state->state = sc64::runtime::vi::mode_updated", patched)
        with self.assertRaisesRegex(ValueError, "already applied"):
            MODULE.patch_vi_events(patched)
        with self.assertRaisesRegex(ValueError, "source drift"):
            MODULE.patch_vi_events(self.source.read_text().replace("int retrace_count = 1;", "int retrace_count = 2;"))

    def test_actual_context_update_and_setters(self) -> None:
        compiler = shutil.which("clang++") or shutil.which("c++")
        if compiler is None:
            self.skipTest("C++20 compiler unavailable")
        patched = MODULE.patch_vi_events(self.source.read_text())
        state_start = patched.index("struct ViState {")
        state_end = patched.index("static struct {", state_start)
        state = patched[state_start:state_end]
        body_start = patched.index("        std::thread thread;", state_end)
        body_end = patched.index("    } vi;", body_start)
        context = patched[body_start:body_end]
        set_mode_start = patched.index('extern "C" void osViSetMode(')
        set_mode_end = patched.index("#define OS_VI_GAMMA_ON", set_mode_start)
        setters_start = patched.index('extern "C" void osViSetXScale(')
        setters_end = patched.index("void ultramodern::submit_rsp_task", setters_start)
        setters = patched[setters_start:setters_end]
        # Compile the actual transformed updater, getters and setters with the
        # real installed source headers. The fixture supplies only host storage.
        fixture = r'''#include <cstdint>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>
#include <string>
#include <stdexcept>
#include <ultramodern/renderer_context.hpp>
#include "vi_scale.hpp"
u32 osVirtualToPhysical(PTR(void) pointer) { return static_cast<u32>(pointer) & 0x1fffffff; }
''' + state + "\nstruct Harness {\n" + context + "\n};\nstruct { Harness vi; std::mutex message_mutex; } events_context{};\n" + patched[set_mode_start:set_mode_end] + setters + r'''
void require(bool valid, const char* error) { if (!valid) throw std::runtime_error(error); }
int main() {
    std::vector<uint8_t> rdram(1024);
    OSViMode* mode = reinterpret_cast<OSViMode*>(rdram.data());
    mode->comRegs.xScale = 0x00100400;
    mode->comRegs.hStart = 0x006c02ec;
    mode->comRegs.ctrl = 0x3206;
    mode->fldRegs[0].yScale = 1024;
    mode->fldRegs[1].yScale = 0x02000800;
    mode->fldRegs[0].origin = 0x280;
    mode->fldRegs[1].origin = 0x500;
    auto& vi = events_context.vi;
    auto* next = vi.get_next_state();
    next->framebuffer = static_cast<int32_t>(0x80123000u);
    osViSetMode(rdram.data(), static_cast<int32_t>(0x80000000u));
    osViSetXScale(0.5f);
    osViSetYScale(0.7f);
    require(vi.get_cur_state()->state == 0, "pending scale must not mutate current context");
    vi.update_vi();
    require(vi.regs.VI_X_SCALE_REG == 0x00100200 && vi.regs.VI_Y_SCALE_REG == 716, "field zero composition");
    require(vi.regs.VI_ORIGIN_REG == 0x123280, "field zero origin");
    require(vi.get_next_state()->x.factor == 0.5f && vi.get_next_state()->y.factor == 0.7f, "scale factors copied through actual swap");
    require(osViGetCurrentFramebuffer() == static_cast<int32_t>(0x80123000u), "current framebuffer getter");
    require(osViGetNextFramebuffer() == osViGetCurrentFramebuffer(), "next framebuffer getter after copy");
    vi.field = 1;
    vi.update_vi();
    require(vi.regs.VI_Y_SCALE_REG == 0x02000599 && vi.regs.VI_ORIGIN_REG == 0x123500, "field one scale and origin");
    vi.get_next_state()->state |= VI_STATE_REPEATLINE;
    vi.update_vi();
    require(vi.regs.VI_Y_SCALE_REG == 0 && vi.regs.VI_ORIGIN_REG == 0x123000, "repeatline overrides scale and origin");
    vi.get_next_state()->state |= VI_STATE_BLACK;
    vi.update_vi();
    require(vi.regs.VI_H_START_REG == 0, "black overrides horizontal start");
    osViSetMode(rdram.data(), static_cast<int32_t>(0x80000000u));
    require(vi.get_next_state()->state == 1, "mode clears scale black repeat flags exactly");
    vi.update_vi();
    require(vi.regs.VI_X_SCALE_REG == 0x00100400 && vi.regs.VI_Y_SCALE_REG == 0x02000800, "new mode ignores copied stale factors");
    require(vi.regs.VI_H_START_REG == 0x006c02ec && vi.regs.VI_ORIGIN_REG == 0x123500, "new mode clears black/repeatline effects");
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / "vi.cpp", Path(directory) / "vi"
            source.write_text(fixture)
            compiled = subprocess.run([compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-I", str(ROOT / "native/runtime"), "-I", str(ROOT / "third_party/N64ModernRuntime/ultramodern/include"), "-I", str(ROOT / "third_party/N64ModernRuntime/thirdparty"), str(source), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
