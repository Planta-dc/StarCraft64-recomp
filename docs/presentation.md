# Presentation: fixed Fit after Stage 6 withdrawal

The user withdrew Stage 6 on 2026-10-09 (ADR-060). HD fonts were already rejected;
image-filter and scale choices are now also removed. This is a cancelled
experiment, not a certified HD/widescreen deliverable.

## Current behavior

The original font artwork, software-rendered image and nearest-sampling shader
are preserved. Fit always uses the largest aspect-preserving viewport, with black
letterboxes. The native info reports `scale_mode="fit"`; there is no setter or
persisted choice. The common viewport has no integer rounding path and is shared
by rendering, GUI and pointer inversion. Existing `presentation-v1` preferences
and old `sc64.scale`/`sc64.filter` keys are unused. Saves and ROM storage remain.

Removed: HD observers/atlas/GUI, extra raster, Original/Sharp/Smooth filters,
Image/Scale/Text buttons, F2/F5/F7 bindings, Lua presentation setters, filter/scale
CLI/Make options and preference persistence. The original temporary controller
panel returns to its 60-node budget. No widescreen guest patch was enabled.

Static GPU probes retain guest-autostart and GUI isolation: one fixture owns its
mailbox and no status message can contaminate pixel comparison. This diagnostic
invariant is independent of the cancelled presentation feature. The existing
GPU checker now verifies the entire Fit viewport and black bars, including
fractional dimensions, against nearest source-pixel sampling. At an exact texel
boundary, either adjacent source texel is accepted to account for GPU interpolation
precision; filtered blends or displaced samples elsewhere fail. Exact equality
with the mathematical upper-side reference is reported separately.

## Build and verify

Use prepared private inputs and the pinned local toolchain:

```sh
make test
make build
make run ROM="/path/to/your.z64"
make build-android BUNDLE_ROM=1 ROM="/path/to/your.z64"
make check-apk BUNDLE_ROM=1
make install-android BUNDLE_ROM=1 SERIAL=YOUR_DEVICE
make run-android SERIAL=YOUR_DEVICE
```

Default APK builds exclude ROM; omit `BUNDLE_ROM=1` and import a personal dump.
Use an explicit current ADB serial. To check desktop original pixels:

```sh
python3 tools/desktop/run.py --gpu-probe local/inputs/renderer/manifest.json \
  --seconds 6 --storage local/private/pixel-fixtures \
  --output local/reports/new-fit-check
python3 tools/desktop/check_gpu.py local/reports/new-fit-check/gpu
```

All output paths must be fresh and ignored. The removed filter/scale options are
unsupported. A bounded Android Home/return check uses `make smoke-android` with
an explicit serial, audited APK and matching `BUNDLE_ROM` choice.

## Historical evidence and acceptance

Earlier reports in `local/reports/stage6-presentation-01/` and
`local/reports/stage6-text-01/` are preserved unchanged. They identify withdrawn
artifacts and do not certify this build. The authored pre-rollback diff/source
is archived under `local/reports/presentation-removal-01/withdrawn-source/` with
`authored-before-rollback.patch`. The original text/camera observations remain
in `research.md`; no wider execution/visibility experiment is asserted.

Fresh rollback reports are under `local/reports/presentation-removal-01/`.

- [x] 151 Python checks and 13 CTest checks pass (`tests-03.log`), including Lua
  input fixtures, forced Fit, fractional mapping and nearest-boundary rejection.
- [x] Final desktop build passes 20 original-frame comparisons (`original-02/`).
  Native RGB is exact against the fenced baseline for all 20. GPU RGB is exact
  for 16; four 512×384 split-screen frames at 3.75× have differences exclusively
  at exact texel boundaries, each equal to an adjacent source pixel. All 20 pass
  the nearest rule; original menu and split-screen GPU readbacks were inspected.
- [x] Final local Android build/APK audit passes; `resources-audit.json` decodes
  the pinned manifest and confirms removed resources/settings are absent. Stale
  `presentation.luac` was archived and removed before the final desktop rebuild.
- [x] `phone-02/run.json` verifies the installed APK hash and a 45-second Vulkan
  Home/return window on the phone / Android 16. Guest cadence is 59.92–60.14 fields/s;
  guest, PCM and presentation freeze/resume correctly, with the same process and
  no reported guest error/crash. This is a bounded native probe, not physical
  touch or subjective audio acceptance. Later screenshots captured a sleeping
  display and are not visual evidence.

| Final artifact | SHA-256 |
|---|---|
| Desktop executable | `6f805053e51a165efbc98a2b3fd397fe29cd2bec1d93e776e012bed6017c1c85` |
| Personal bundled-ROM APK | `a7188263645ce276d5c8dc1931925618ab6ba636e72c08509c6836b04b6facea` |

Build receipts are preserved as `desktop-build-final.json` and
`android-build-final.json`. Earlier attempts remain unchanged: `original-01`
predates stale-resource cleanup; `phone-01` was rejected because a rebuild
replaced the selected APK during its probe. Neither is final acceptance.

No new touch mission, long thermal run, expanded device matrix or widescreen
semantics is claimed by this rollback. Stage 5 retains its accepted scope.
