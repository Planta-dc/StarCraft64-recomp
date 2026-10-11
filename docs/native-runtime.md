# Stage 1 standalone native host

Status: Stage 1 accepted on macOS arm64 with file PCM output. This is a CPU-only
capture backend, with no engine or GPU calls. C++20 host code links the private
recompiled C static library. The supplied ROM is never edited; normalized SHA-1
is checked before registration with the runtime's separate XXH3 identity.

## Plan, risks and open inputs

Convert the three confirmed section maps into section-qualified symbols; retain
menu/game overlay identity even where their VRAM overlaps. Generate transactionally,
build the native archive, implement measured OS/device semantics and execute
startup, interactive menus and a ten-minute session. Save and cold reload must
use the game UI and the same Flash protocol observed in the original emulator.

The approved image and original captures are sufficient inputs. Risks include
missing indirect entries, partial overlay DMA, CPU waits that require interrupt
preemption, incomplete upstream VI/PI/AI wrappers, and capture lifetime/queue
growth. Failures are investigated at their original guest PC; no game routine
is replaced with an empty stub to satisfy the gate.

## Local build

Run the private generation commands in `../tools/recompile/README.md` first. The
verified macOS machine uses LLVM, CMake/Ninja, OpenSSL and SDL2 from Homebrew.
Other desktop hosts require their installed compiler/dependency paths to be
verified separately; the present successful build is macOS arm64 only.

```sh
git -C third_party/N64ModernRuntime submodule update --init --recursive
python3 tools/recompile/patch_runtime.py third_party/N64ModernRuntime \
  local/deps/N64ModernRuntime
python3 tools/recompile/patch_host_runtime.py local/deps/N64ModernRuntime
cmake -S . -B local/build/host -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_C_COMPILER=/opt/homebrew/opt/llvm/bin/clang \
  -DCMAKE_CXX_COMPILER=/opt/homebrew/opt/llvm/bin/clang++ \
  -DCMAKE_PREFIX_PATH=/opt/homebrew
cmake --build local/build/host -j 10
ctest --test-dir local/build/host --output-on-failure
python3 -m unittest discover -s tests -v
```

Prepared runtime patches are private and hash guarded. The scripts record
source revisions and output hashes and refuse unrelated modifications. The
runtime's nested `recomp.h` was byte-compared with the generating revision.
Assertions remain enabled in native dependencies and the game library.

## Capture contract

Each `sp_task` event contains the 16 OSTask words, guest field sequence,
display-list hash, microcode hash and a complete canonical big-endian 8 MiB
snapshot. RAM is stored as immutable SHA-256-addressed 4 KiB pages. The snapshot
is taken synchronously while the submitting guest owns execution, before the
graphics task is enqueued. SP/DP completion follows capture processing.

`task-N.dl.bin` retains the root bytes; its nested lists, objects, palettes and
CPU image bytes are recoverable from the complete snapshot. `vi` events contain
all fourteen registers in the exact pinned `ViRegs` declaration order. `input`
events record pad changes; `flash_*` events record device operations. Audio
rate changes create separate WAV segments. A `report.json` appears only after
the runtime stops and its threads join normally. A directory without this
report is a failed or interrupted run and cannot satisfy acceptance.

The backend does not execute RDP or write rendered framebuffer bytes. CPU
source-image and GBI comparisons are possible at Stage 1; rendered output
parity belongs to Stage 2. Guest framebuffer feedback beyond the accepted
research corpus requires additional handling before it can be certified.

## Run and inspect

Each output directory must be new. Storage contains the checked personal ROM
copy and `sc64.fla`; captures and all build products stay ignored.

```sh
local/build/host/sc64_capture \
  --rom 'StarCraft 64 (USA).z64' \
  --output local/captures/recompile/native-new \
  --storage local/private/recompile/save-new --seconds 60
python3 tools/recompile/inspect_capture.py \
  local/captures/recompile/native-new local/reports/recompile/native-new.json
```

`--inputs private.json` accepts an array of `{field, duration, buttons}` objects.
Buttons use actual libultra pad bits; sticks are zero in this harness. Recipes
are private and input transitions are recorded. `--seconds 600` runs the real
ten-minute interval. SIGINT requests a cooperative stop.

`--silent` preserves timed AI FIFO and WAV production without opening a device.
`SDL_AUDIODRIVER=dummy` exercises the SDL queue through a simulated device; it
cannot establish audible hardware output. The initial environment had no
available default audio device. The host reports this before starting guests.
Sustained SDL dummy menu runs reached the one-second queue guard (D-028); they
are retained as failed diagnostics. The headless stability gate therefore uses
the WAV sink with `--silent`, without dropping samples or bypassing AI timing.
Audible live output remains a Stage 3 requirement.

`inspect_capture.py` verifies page/list/ucode hashes, reconstructs sampled or
all complete RAM snapshots, traverses bounded S2DEX2 list control flow, hashes
CPU background images and validates finalized WAVs. `--stride N` is an explicit
sampling mode and does not certify every captured list. It does not rasterize.

## Acceptance checklist

- [x] Section-qualified symbols and transactional generation implemented.
- [x] Generated code builds into a local static archive with no unhandled instruction diagnostic.
- [x] Flash protocol boundary, corruption/restart/late-publication tests pass.
- [x] Native title and interactive main menu identified against original captures.
- [x] Nonzero PCM verified through the native menu session.
- [x] Original game save and cold-process reload verified natively.
- [x] A real 600-second menu/demo session exits cleanly with continuing task/audio output.
- [x] Capture and queue integrity checked; remaining debt explicitly scoped.

Stage 2 may now begin. Live SDL output is not certified; D-028 remains a Stage 3
audio requirement. No interactive presentation, Android build or campaign parity is claimed.

## Executed native evidence

The private v12 symbol profile contains 2,842 resident functions, 113 menu
functions and 1,290 game functions. Generation emitted 83 C translation units
and 86 total hashed files, with no unhandled instruction or function stub. The
sole diagnostic is an ambiguous call into shared overlay VRAM, resolved by the
actual active function map. A fresh generation reproduced every output byte.

`boot-09` ran 45.036 seconds, emitted/completed 1,680 tasks and finalized 495,616
stereo frames at 11,025 Hz plus the two-frame 4,000 Hz startup segment. Native
task 125/field 1012 contains the original title in CPU-written RGBA16 memory at
physical `0x1767C0`, 640×480. `preview_rgba16.py` reproduced the reviewed PNG;
its raw buffer SHA-256 is
`17c9183a7b29afd0f2a37116449096f0bfe4ac71e3a49a35ef00819eb522843d`.
This preview omits RDP fade effects and VI filtering. Native main-menu census
matches the original and six ordered source images match exactly; sampled
mission-list packets match three to seven original images.

`save-game-01` used original game navigation, ran 130.040 seconds (see its exact
report), completed 6,312 tasks, and issued 388 Flash page DMA writes beyond the
earlier initial formatting. `load-game-01` started a fresh process with only the
same ROM and battery file, ran 90.033 seconds, completed 4,026 tasks and reached
a 320×240 game mode. Its loaded-map census and three ordered source images
match `save-loaded/loaded-map-task-386.rdram.bin`. No emulator state is imported.
The 131,072-byte battery SHA-256 remained
`be487b870db6f81745ed270d197e8a36da38d213598d8ae3a52cf8b6db314d7c`.
Whole rendered-map pixels and saved simulation parity are separate later gates.

The authored regression suite passes 59 Python tests and two CTest
targets. The scheduler/VI tests compile actual transformed runtime functions;
synthetic fixtures are not counted as native game evidence. Flash and VI native
helpers also passed strict C++20 ASan/UBSan probes. Stage 0 was rechecked: 14
original-ROM captures and 139 evidence files pass its independent gate.

The acceptance command consumes complete native reports and immutable snapshot
hashes, refuses a short/interrupted stability run, checks continuing telemetry,
and records its audio sink scope:

```sh
python3 tools/recompile/check_acceptance.py 'StarCraft 64 (USA).z64' \
  --generation local/recompile/symbols-v12-repro/recompile-rd7oiwj1/generation.json \
  --stability local/captures/recompile/stability-03 \
  --reference-comparison local/reports/recompile/boot-09-reference.json \
  --load-reference-comparison local/reports/recompile/load-game-01-reference.json \
  --title-capture local/captures/recompile/boot-09 --title-task 125 \
  --save-capture local/captures/recompile/save-game-01 \
  --load-capture local/captures/recompile/load-game-01 \
  --save local/private/recompile/save-probe-01/sc64.fla \
  --save-before-reload local/reports/recompile/native-save-before-reload.json \
  --output local/reports/recompile/acceptance-new.json
```

Those paths identify this private evidence corpus. Fresh captures need fresh
output names and their own input/provenance checks; they are not bundled with
authored source. The checker samples every 600th complete task snapshot and the
last snapshot, while checking all submission/completion sequence events.

`stability-03` passed: 600.039160708 seconds, 36,000 nominal VI fields, 33,004
submitted/completed tasks and 13,211,652 stereo sample values. All 56 sampled
steady-menu telemetry intervals show continuing task/audio production; task
backlog stays bounded. Process peak resident memory was 101,122,048 bytes
(96.438 MiB). Shutdown joins normally, all WAV segments finalize, and the
acceptance report is `local/reports/recompile/acceptance-final-bounded.json`.
