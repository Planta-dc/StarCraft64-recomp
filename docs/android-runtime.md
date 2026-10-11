# Stage 5: Android runtime profiles

Current status: Stage 5 is closed for the personal Android scope (ADR-055).
See [stage5-acceptance.md](stage5-acceptance.md) for the later mission Back/Home,
expanded helper FPU probes, phone user acceptance and deferred qualification.
The plan and receipts below retain the scope of the preceding ADR-054 slice.

## Plan and entry gate (2026-10-09)

Stage 4 desktop control is accepted; Stage 5 remains in progress. The next
bounded slice proves native startup and Home/return on an actual 16 KiB Android
kernel, with each requested graphics adapter of the former engine shell checked
at runtime.
Static ELF/ZIP alignment and a successful run on the 4 KiB phone cannot establish
this result. Stage 6 remains gated on the complete Stage 5 acceptance checklist.
(Superseded: Stage 6 was withdrawn by ADR-060 on 2026-10-09.)

1. Verify the pinned engine's Android argument delivery and graphics API.
2. Add actual adapter telemetry and explicit page-size/backend requirements to
   the existing smoke tool. Reject an incompatible device before app mutation.
3. Require presentation progress as well as guest/PCM progress, including after
   Home/return. Fence log collection to the current launch and bind the run to
   the audited, installed APK.
4. Run regression checks and the desktop application before building Android.
5. Run the same APK on the official Android 16 ARM64 16 KiB image through Vulkan
   and OpenGL ES. Preserve logs, artifact hashes and failed runs separately.

## Risks and open inputs

Precompiled engine libraries may assume 4 KiB host pages. A requested graphics
adapter may fall back, and guest progress alone may hide a stalled presentation
after surface recovery. Emulated GPU/audio hardware cannot certify physical
Adreno/Mali performance or perceptual sound. No additional user input is needed
for this compatibility experiment. Physical touch mission completion, safe
areas, audio rerouting, other devices and sustained thermal runs stay separate.

## Verified interfaces

Current shell (ADR-074): `Sc64Activity.getArguments()` forwards the string-array
extra `com.nomadic.sc64.ARGUMENTS` (only `sc64.render_driver` is accepted);
`tools/android/run.py --backend` passes
`--config=sc64.render_driver=opengles2|vulkan`, which selects the SDL renderer
by name before creation. The active renderer is published as `render_driver` in
compact Android telemetry, and the tool compares that observed value rather than
the request. Suspension lines `SC64 Android suspended=N fields=… tasks=…
samples=…` come from the SDL background event watch.

The pinned former engine shell (before ADR-074) passed arguments through its
own activity's command-line intent extra with
`--graphics-adapter=opengles|vulkan` and reported `graphics_family` 3/4; the
receipts below were produced that way and stay historical.

The runtime tool keeps only cadence intervals that do not cross an Android
suspension event. A post-return interval must advance guest fields/tasks/PCM and
presentation. `runtime_profile_accepted` describes these bounded checks; the
separate `physical_device_accepted` remains false. Failures retain
`acceptance_error`. With SDL 3.4.18 the Vulkan request fails this gate on Home
return on the emulator (D-053); OpenGL ES passes.

## Reproduce

Build the desktop application and run the normal regressions first:

```sh
make test
make build
make run ROM="/absolute/path/to/owned.z64" RUN_SECONDS=35
make build-android BUNDLE_ROM=1 ROM="/absolute/path/to/owned.z64"
```

Use the SDK Manager's official
`system-images;android-36;google_apis_ps16k;arm64-v8a` image and create a separate
AVD. Verify `adb -s DEVICE shell getconf PAGE_SIZE` returns `16384` before
testing. The [Android page-size guide](https://developer.android.com/guide/practices/page-sizes#16kb-emulator)
documents the image and runtime check. This run uses image revision 7, archive
`arm64-v8a-ps16k-36_r07.zip`, Google SHA-1
`dda632745023567113d9954101709c6526a3c250`, and Emulator 37.1.11.0.
The downloaded image and separate `sc64-16k` AVD remain under ignored `local/`.
They do not change the existing AVD or the phone's kernel.

Install the audited candidate on the explicit emulator serial:

```sh
make install-android SERIAL=emulator-5580 BUNDLE_ROM=1
make smoke-android SERIAL=emulator-5580 BUNDLE_ROM=1 PAGE_SIZE=16384 \
  ANDROID_BACKEND=vulkan SMOKE_SECONDS=55 \
  REPORT=local/reports/my-runtime-vulkan
make smoke-android SERIAL=emulator-5580 BUNDLE_ROM=1 PAGE_SIZE=16384 \
  ANDROID_BACKEND=opengles SMOKE_SECONDS=55 \
  REPORT=local/reports/my-runtime-gles
```

Set `ADB=/absolute/path/to/adb` when it is absent from PATH. Choose fresh report
directories. The tool restarts the app, sends Home after ten seconds, returns
after eighteen seconds and checks advancing telemetry after return. Each run
audits the APK, compares its installed hash and verifies that the selected file
has not changed. It never changes display settings, the device page size or app
data. Without a bundled ROM, import a verified ROM into that device beforehand.

For a different device, `PAGE_SIZE=4096` verifies that profile; omit `PAGE_SIZE`
to record the observed value without requiring one. Backend requests need the
`render_driver` telemetry of the SDL3 shell; an APK built before ADR-074 cannot
pass them.

## Slice acceptance

- [x] Pinned API/Intent path verified; no direct graphics API calls added.
- [x] Incorrect page size/ABI, backend fallback and stalled presentation are
      rejected by synthetic regression checks.
- [x] Desktop build, native application and existing Python/Lua/CTest gates pass.
- [x] Candidate APK links locally and passes signature/private-data/alignment audit.
- [x] Vulkan startup, guest/PCM/presentation and Home/return on 16 KiB ARM64.
- [x] OpenGL ES startup, guest/PCM/presentation and Home/return on 16 KiB ARM64.
- [x] Existing COP1 rounding/subnormal executable runs on that 16 KiB environment.

## Implemented result and evidence

Private evidence is under `local/reports/android-runtime-profile-01/`:

| Receipt | Verified result |
|---|---|
| `python-final-02.log`, `native.log` | 149 Python/Lua checks and 13 CTest checks pass |
| `desktop-live/run.json` | Actual 35.86-second desktop run exits 0; engine/resources unchanged; Vulkan family 4, presentation and PCM advance, zero software PCM underruns |
| `build.json` | Local build, signature, private-data/ROM identity and final ELF/ZIP 16 KiB alignment checks pass |
| `vulkan/run.json` | Same installed APK on 16384-byte ARM64 kernel; actual family 4; same process, advancing guest/PCM/presentation after Home; suspended guest counters remain unchanged |
| `opengles/run.json` | Same APK/kernel; actual family 3; same process and all post-return lanes advance; suspension delta is one VI field, zero tasks/samples |
| `fpu.json` | Executable exits 0 on that kernel: four COP1 rounding modes and one non-flushed subnormal |
| `opengles/screen-after.png` | Menu visibly renders after dismissing Android's first-launch immersive-mode guidance; outside the timed smoke window |

Both 55-second smoke windows end during the intro; neither is a timed menu or
mission performance receipt. Their last counters show zero software underruns,
dropped PCM and hardware xruns. Later screenshots show the menu, initially
obscured by Android's immersive guidance. The unobscured OpenGL ES screenshot
was inspected, but no exact Android frame comparison was performed.

APK SHA-256:
`b1189d2375af40c60ad8ff1cdee3702c577ac8aeed2867cf09cd71ff77d87978`.
Native library SHA-256:
`2062c9ffcd651f358c9436de9f0384c74f42724024586fc03d00c67dc1fac87b`.
APK size: 44533246 bytes. FPU executable SHA-256:
`075b9b5f2d4dcfa59342275212c7227ee64edd7ef3754bbfc321ce4eb6712d71`.
The FPU result does not certify all VR4300 arithmetic, exceptional values or
guest FCSR exceptions. D-012 retains that broader numeric coverage.

Full mission gameplay, independent frame parity on Android, physical GPU/audio
quality, sustained cadence and thermal behavior are not acceptance claims of
this bounded slice. See [stage5-acceptance.md](stage5-acceptance.md) for the current
closed Stage 5 gate and its explicit exclusions.
