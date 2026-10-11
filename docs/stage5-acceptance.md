# Stage 5 acceptance for personal Android delivery

**CLOSED on 2026-10-09 for the user-scoped personal Android profile (ADR-055).**
Stage 6 may begin on a separate user request. This closure does not certify the
deferred device matrix, long performance/thermal sessions or exhaustive numerics.
(Superseded: Stage 6 was withdrawn by ADR-060 on 2026-10-09.)

This evidence was recorded on the former engine shell's APK. ADR-074 replaced
the shell with SDL3; its emulator re-verification is in [android.md](android.md), and a
physical phone rerun of the SDL3 APK is still open.

## Scope and plan (2026-10-09)

The user requests Stage 5 closure while omitting expanded device validation and
long Adreno/Mali performance/thermal sessions. This document is the current
acceptance checklist; earlier per-slice checklists remain historical evidence.
Omitted work is deferred, not represented as a successful test.

1. Accept the named phone touch-mission/save-reload report independently of
   automated native recipes and emulator evidence.
2. Complete the existing ARM64 FPU probe using the pinned N64Recomp helpers:
   mode-sensitive arithmetic/conversions, gradual underflow, signed zero,
   unordered NaN comparisons and guest-thread isolation.
3. Exercise Android system Back and Home/return in a mission, preserving raw
   logs, screenshots, failure attempts and the APK identity.
4. Rerun desktop/native/Lua/Python checks and verify the current APK remains
   identical to the audited 16 KiB Vulkan/OpenGL ES candidate.
5. Update the stage ledger and explicitly list the deferred qualification work.

Risks are confusing a host/helper probe with complete VR4300 exception behavior,
a native recipe with physical touch, and file retention with an actual game
save/load. The physical walkthrough was the remaining human input. The user
confirms the first Terran mission was completed on the phone with touch only and
save/load was checked after a full restart. This is **USER-ACCEPTED**, not a
recorded automated walkthrough or a new measured performance claim.

## Required checks

- [x] Local arm64 APK pipeline links the private game/runtime into the pinned
      former engine; the successful local CMake relink route is the accepted
      personal build path.
- [x] ROM byte-order/SHA-1, private import, Flash storage and legal packaging
      boundaries have implementation, regression and bounded native evidence.
- [x] The default APK excludes ROM; explicit personal bundling reads the verified
      APK asset directly without a second persistent ROM file.
- [x] The user accepts first-Terran touch-only mission and actual save/load on
      an Android 16 phone, with diagnostic pad disabled.
- [x] Actual final ELF/ZIP alignment and 16 KiB Android ARM64 Vulkan/OpenGL ES
      startup/Home-return pass (ADR-054).
- [x] Expanded supported-helper FPU probes pass on macOS arm64, the phone's
      4 KiB kernel and the Android emulator's 16 KiB kernel.
- [x] Android-delivered Back opens/closes the original mission menu and mission
      Home/return freezes/resumes guest/PCM/presentation in the same process.
- [x] 149 Python/Lua checks and 13 CTest checks pass; production gameplay/audio/
      renderer code is unchanged by this closing FPU-test pass.

The local CMake relink of the former engine supplies a complete locally
compiled and audited engine without a remote build request (ADR-042). The
former engine's conventional container build packaging remained an optional
alternative, not an additional delivery gate for this personal profile. It has
not been implemented or certified.

## Evidence and limits

Current private closure evidence is under `local/reports/stage5-close-01/`.
The earlier build and 16 KiB adapter receipts remain under
`local/reports/android-runtime-profile-01/`; they retain their own hashes.

| Evidence | Scope |
|---|---|
| User reply on 2026-10-09 | First Terran touch mission and save/load after restart on the phone; no newly recorded video or exact test-session APK hash |
| `phone-fpu-supported.json`, `emulator-fpu-supported.json` | Same hashed standalone diagnostic executable, exit 0 on both ARM64 kernels |
| `native-final.log`, `python.log` | Completed regression suites |
| `closure.json`, `verify_closure.py` | Revalidated raw mission log/receipts, test completion and executable/APK hashes, including the installed APK; human acceptance remains separately labelled |
| ADR-054 `build.json`, `vulkan/run.json`, `opengles/run.json` | Current APK identity, final ELF/ZIP alignment and actual 16 KiB adapter startup/Home-return |
| `back-home-final/run.json`, `engine.log`, `back-open.png`, `back-closed.png`, `screen.png` | Actual Android system Back opens/closes the original pause menu; mission Home/return freezes fields/tasks/PCM exactly and resumes all lanes in the same process on 16 KiB Vulkan |

The mission probe reaches the map with a native controller recipe and dismisses
advisors with Android taps before testing actual OS Back/Home events. It is not
an emulator touch-only walkthrough. Screenshots show the original Game Paused
menu and the resumed map. Current-launch telemetry passes the runtime validator:
`game -> modal -> game`, identical PID, suspension delta `[0,0,0]` and three
advancing post-return samples. No guest error or native crash is observed.
The cumulative software-audio-underrun count is 1 before Back and remains 1
after return; this probe is not a zero-underrun whole-session audio certificate.
Earlier failed probe attempts remain preserved: startup PID race, insufficient
advisor-dismissal time and an advisor message after closing pause. They do not
replace the successful final receipt or establish a production regression.

`test_guest_fpu.cpp` uses exact halfway operands and independent integer bit
expectations. It checks all four rounding modes for float/double arithmetic,
CVT/TRUNC helpers, double-to-float and integer-to-float conversion; float/double
subnormal inputs/results; negative zero; host NaN arithmetic/comparison; and a
worker that resets inherited FZ/DN/rounding without changing the parent.
Guest initialization also clears FZ16, but guest arithmetic here is 32/64-bit.
This is the established recompilation helper profile, not full VR4300 traps,
signaling-NaN payload semantics or guest FCSR exception certification.

The first diagnostic artificially enabled FZ16 in the parent. On the emulator,
that bit changed from FPCR `0x03880000` to `0x03800000` across the thread test;
the phone did not reproduce it. Those failed receipts are preserved. The final
probe seeds only modes affecting guest 32/64-bit arithmetic, reads the latched
parent FPCR and still verifies FZ16 is clear in initialized guest workers.
The precise source of that emulator/system FPCR difference remains unverified;
it is not claimed to be a game/runtime defect or a resolved FP16 test.

APK SHA-256:
`b1189d2375af40c60ad8ff1cdee3702c577ac8aeed2867cf09cd71ff77d87978`.
Engine library SHA-256:
`2062c9ffcd651f358c9436de9f0384c74f42724024586fc03d00c67dc1fac87b`.
Final Android FPU diagnostic SHA-256:
`274bdc797a8595519bf7f8a8884ee68bc16fc831b450fc73a6f5fdf171c0c59a`.
`make check-apk BUNDLE_ROM=1` rechecks the unchanged APK's alignment and verified
ROM asset during closure. The installed emulator APK has the same hash after
the mission probe. The production build is the existing ADR-054 candidate;
only its standalone diagnostic test and documentation changed in this pass.

## Deferred qualification

By user scope, cross-device Adreno/Mali visual/backend parity, 15-minute
cadence/thermal tests, broader safe-area/orientation/surface-loss scenarios,
audio routing/device loss, physical gamepad hotplug and expanded input workloads
do not block this stage. Their existing debt entries retain their limits.
No midrange performance, broad device compatibility or thermal certification
is asserted. Exhaustive VR4300 numeric/exception coverage remains separate.

## Build and verify

```sh
make test
make build
make run ROM="/absolute/path/to/owned.z64" RUN_SECONDS=35
make build-android BUNDLE_ROM=1 ROM="/absolute/path/to/owned.z64"
make check-apk BUNDLE_ROM=1
make install-android SERIAL=EXPLICIT_DEVICE_SERIAL BUNDLE_ROM=1
make run-android SERIAL=EXPLICIT_DEVICE_SERIAL
make smoke-android SERIAL=EXPLICIT_DEVICE_SERIAL BUNDLE_ROM=1
```

Omit `BUNDLE_ROM=1` and `ROM` from the Android build to use system-picker import.
Use fresh `REPORT=local/reports/NAME` for each smoke. Rebuilt artifacts need
their own audit/runtime receipts. [android-runtime.md](android-runtime.md)
documents page-size/backend options and [android.md](android.md) records the
implementation history. Stage 6 work remains a separate user-directed task.
(Superseded: Stage 6 was withdrawn by ADR-060 on 2026-10-09.)
