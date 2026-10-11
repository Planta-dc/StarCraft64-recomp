# StarCraft 64 native port implementation plan

## Objective and current boundary

> ADR-074 (2026-10-11) replaced the former engine shell with an authored SDL3
> shell and ported the Lua adapters to C++. Engine-specific steps below record
> the plan as executed for Stages 3–5; see [desktop.md](desktop.md) for the
> current shell.

Deliver a personal-use native NTSC-U port with desktop development and Android
RTS touch control. Recompile the supplied game's MIPS code to C with N64Recomp;
use librecomp/ultramodern for OS/devices; interpret the game's graphics with an
owned HLE implementation; submit GPU work exclusively through the shell's
graphics abstraction (SDL_Renderer since ADR-074).
RT64 and direct OpenGL/Vulkan calls are excluded from the shipped architecture.
Accurate emulator renderers are research references only.

Native code uses **C++20**, as approved by the user. Python tools use 3.10+.
Generated game code stays C and private. Desktop includes macOS, Linux and
Windows; the locally available macOS arm64 environment is the first integration
target. Android arm64 follows desktop acceptance. Web is a separate later study.

Current artifacts include the original-ROM research harness, private native
game/runtime, tested gfx_core, a personal macOS arm64 desktop application and
controller-translated mouse/touch input. **Stages 0–3 have bounded desktop
acceptance; Stage 4 is closed for desktop control scope by user acceptance
(ADR-038). Stage 5 is closed for the personal Android scope (ADR-055).**
The phone menu audio fix is user-accepted (ADR-051); the user also confirms a
touch-only first Terran mission and save/load after restart on the phone. Actual
16 KiB Vulkan/OpenGL ES startup/Home-return, mission Back/Home and expanded
helper FPU probes have bounded receipts. Expanded device qualification and long
Adreno/Mali performance/thermal sessions are deferred by user scope. The current
checklist is [stage5-acceptance.md](stage5-acceptance.md). Historical stage/slice
plans below retain their original broader goals. Sources are pinned in
`toolchain-sources.md`.

### Measured design inputs from Stage 0

| Area | Accepted evidence | Implementation consequence |
|---|---|---|
| Graphics | S2DEX2 xbus 2.08; BG_COPY, BG_1CYC, OBJ_LOADTXTR; RDP texrect/LOADTILE/TLUT, 1-cycle/COPY | Objects and palette ordering are mandatory; triangles and other unobserved families remain conditional |
| CPU base scene | CI8 terrain/units, then BG_COPY to RGBA16 and RDP UI; indexed view aliases framebuffer allocation | Preserve guest software renderer; snapshot CI8/TLUT inputs; do not add a duplicate RGBA CPU layer |
| VI | Menu 640×480 interlaced; 1P 320×240 progressive; 2P 512×384 interlaced | Use VI/native coordinates, not raw PNG dimensions; field cadence remains separate from host presentation frames |
| Executable map | Resident ROM `[0x1000,0xD6640)`; menu/game overlays share VRAM `0x8011FBF0` | Distinct section identity and actual DMA load registration; both overlays are plain, not compressed |
| OS | GCC 2.0J family, 51 replacement body candidates | Use reviewed names, resolve boundaries/aliases and implement actual runtime gaps |
| Persistence | 128 KiB Flash, original save UI and cold reload | Custom PI write/status path required; do not rely on standard osFlash names alone |
| Audio | CPU PCM producer and AI DMA, no audio RSP task in corpus | Recompile CPU mixer normally; implement AI sink, not guessed audio microcode |
| Animation | CPU indexed row decoder, S2DEX background presentation | Preserve CPU decoder; no replacement video codec without evidence |
| Memory hazards | No CPU reads of last-RDP-owned bytes in complete sampled windows | Retain alias generations and ordered memory model; new feedback evidence reopens scene coverage |

See `research.md` for anchors, scope and verification. These inputs override
initial untested assumptions. Original emulator timing is not a physical-console
certification; D-016 remains a native scheduling validation requirement.

## Delivery rules

Before each stage, issue a short plan naming the concrete output, dependency
gate, risks and user inputs that are still needed. Resolve routine choices from
the existing project constraints; ask only when an answer changes scope or
acceptance. After each stage, record the actual build command, tool versions,
verification command, output hashes, acceptance checklist and remaining debt.

Do not cross a gate on a documentation-only or synthetic-test-only claim when
it calls for original/runtime evidence. A successful build does not certify
runtime behavior. Maintain a traceable relation between private captures and
public metadata; unknown used opcodes/devices must produce explicit failures.
Every TODO references `debt.md`. Each architecture change adds/revises an ADR.

ROMs, resources, assembly, microcode, generated C, native libraries, captures and
personal builds remain ignored. Do not upload them to CI or a remote build service.
Authored source and synthetic fixtures can be tested publicly without retail
material; private reference gates run locally. All dependencies retain licenses.

## Dependency gates

| Stage | Entry requirement | Working output | Exit proof |
|---|---|---|---|
| 0 | Supplied image | Repeatable original capture and reviewed hardware/code map | Active GBI/audio, saves, libultra and rendering method known |
| 1 | Stage 0 accepted | Desktop native capture host with actual game/audio | Menu/title, save/reload and 10-minute stable run |
| 2 | Stage 1 accepted | Offline gfx_core and software frame renderer | Ten-plus original frames meet frozen metric and visual gates |
| 3 | Stage 2 accepted | Desktop engine-shell application with graphics/audio/input | Menu to first mission, guest cadence and lifecycle proof |
| 4 | Stage 3 accepted | Desktop gestures through original controller input; optional pad/editor | User-accepted desktop scope, bounded native UI/gesture gates and reported mouse-only mission (ADR-038) |
| 5 | Stage 4 desktop accepted; CLOSED scoped (ADR-055) | Local personal APK; phone mission/save user acceptance; 16 KiB adapter/lifecycle and FPU receipts | Current checklist in stage5-acceptance.md; expanded device and long Adreno/Mali performance/thermal checks deferred |
| 6 | WITHDRAWN by user (ADR-060) | Original typography/nearest sampling with fixed Fit | Fresh rollback checks in presentation.md; no HD/widescreen deliverable |

## Cross-cutting runtime contract

The game's libultra threads run under ultramodern. Guest RAM is presented as
8 MiB, with validated endian-aware access and OS memory-size values. Derive the
exact mapping/startup requirements from Stage 0; do not treat the raw entrypoint
as an entire segment map or force an arbitrary decompressed image into the ROM
address space.

The runtime renderer adapter receives graphics tasks on ultramodern's graphics
thread. It snapshots/consumes all required bytes and interprets them without
host graphics API calls. SP/DP completion must reflect required guest-visible memory effects;
the upstream early-SP-completion assumption must be tested against this game.
Game memory cannot be recycled while the parser still reads it. If needed,
adjust completion order or capture dependencies before signaling completion.

VI events run on an independent guest-clock schedule, initially comparing
upstream nominal 60 Hz with measured original timing. The shell can present at a
different rate; that must not speed up gameplay/audio. Distinguish VI fields,
graphics tasks, completed guest frames and displayed host frames in telemetry.

A FrameMailbox owns three slots. Producer and consumer use explicit ownership,
generation counters and release/acquire synchronization or a small verified lock
protocol. A consumer-owned slot is never overwritten. A published packet owns
its vertices, state, texture bytes and target dependencies; no mutable guest
pointers or GPU handles cross from guest threads.

Only disposable *presentation* may be superseded. Every task and persistent
color-image/TMEM/guest-memory side effect is processed in order. If a packet is a
delta depending on prior GPU rendering, either package the complete dependency
chain, materialize a complete snapshot, or retain that GPU work with bounded
backpressure. Never drop deltas because the host is slow.

Pause is a guest-wide safe-point protocol: stop new guest execution, settle or
freeze task queues, suspend VI/timers/audio consistently, clear transient input
and snapshot/flush persistence as appropriate. Resume rebases deadlines and
restores the established state without accumulated wall-time ticks. Do not
asynchronously suspend threads holding locks. Shutdown wakes waits, stops sinks,
joins producers and releases resources on their owning threads.

## Stage 0 — Original-game investigation (accepted)

### Executed plan and risks resolved

Identify/normalize the supplied ROM, run tentative splat/n64sym analysis, build
legally available reference objects, then instrument original execution. Capture
startup, title/menu, mission list/briefing, 1P, 2P, opening animation and save UI.
Attribute CPU and RDP writes with complete bounded interpreter windows; inspect
VI, AI, PI/Flash and accessory commands. Verify full overlay ROM/RAM equality
and save/reload in a cold process that imports only cartridge battery data.

The experiment found and corrected emulator adapter byte order, unaligned
palette handling and fragmented RDP command accounting. No guest code was
modified. These corrections and discriminating native probes are recorded in
ADR-015. Runtime mapping separated a false resident audio-signature candidate
from actual menu-overlay code. All unresolved production work has explicit debt.

No additional user input is needed to close this supplied-image investigation.
Windows/Linux native port work and Android hardware choice belong to later gates.
Rumble actuation, Brood War-specific 4 MiB gating and complete campaign coverage
are bounded unknowns; they do not become verified by the accepted 2P gate.

### Build and verify

Use `research-workflow.md` for ROM/splat/n64sym and `reference-capture.md` for the
executed C++20 emulator build, authored input recipes, local reports and checker.
The libultra workflow documents reference variants and per-section mapping.
The completed suite contains 21 synthetic tests; native RDP probes and the
original execution corpus are separate evidence. Check hashes before reusing
captures; refuse missing/incomplete streams. There is no port build at Stage 0.

### Acceptance

- [x] ROM identity/header/entry/IPL3 recorded without changing the source.
- [x] Active S2DEX2 text and CPU audio execution established across captured scenes.
- [x] FlashRAM original save and cold restart/reload; peripheral observations scoped.
- [x] Reviewed libultra family/body inventory and required replacement gaps.
- [x] Resident and two plain overlapping-VRAM overlays mapped for Stage 1 inputs.
- [x] Ten-plus reviewed reference images cover menu, briefing, 1P, 2P and animation.
- [x] CPU indexed base, RDP presentation, sampled feedback and VI modes attributed.
- [x] ADR-006/007/013/014/015 resolve initial graphics/code/audio premises.

Stage 1 subsequently passed its separate native gate on macOS arm64 with file
PCM output. Title/menu, original save/cold reload and a real ten-minute run are
recorded in `native-runtime.md`; live output remains D-028.

## Stage 1 — Symbols, recompilation and standalone desktop host (accepted)

### Plan

First convert the reviewed segmentation and function metadata to the pinned
N64Recomp format; then run the recompiler; then link a minimal host whose graphics
adapter captures tasks without a GPU. Preserve CPU audio production, connect actual AI PCM and implement the
FlashRAM/PI path established in Stage 0. Shell integration does not begin here.

### Symbol conversion

The implemented converter is `tools/recompile/splat_to_syms.py`. Input
must contain explicit section identity and complete function boundaries; labels
alone cannot supply reliable sizes. Reject contradictory VRAM/ROM maps, duplicate
names, out-of-section ranges, instruction misalignment and unexplained overlap.
Preserve distinct overlays sharing a guest address, tail/secondary entrypoints,
jump tables, delay-slot semantics and reviewed alias decisions. Store raw results
under `local/symbols/`; promote only reviewed metadata without code bytes.

The inspected upstream symbol emitter uses `[[section]]` with `name`, `rom`,
`vram`, `size` and a `functions` array of name/address/size records. Relocations
belong to their sections. Check the corresponding parser in the pinned tree and
round-trip a synthetic section before writing the real converter. Do not invent
a flattened function schema or an overlays TOML table based on memory.

In the checked config parser, `[input]` accepts `entrypoint`, `symbols_file_path`,
`rom_file_path`, `output_func_path` and `manual_funcs`; `[patches]` accepts `stubs`,
`ignored` and **`renamed`**, not an arbitrary `renames` mapping. `renamed` is suffix
renaming, not libultra name identification. Exact replacement names come from
`src/symbol_lists.cpp`; write the validated libultra names into symbol input.
Consult source for each other key before using it. Do not emit a runnable
game-specific TOML until section/overlay evidence exists.

### Recompiler and host

Keep generated game C and lookup/overlay files under `local/generated/game`.
Run the pinned N64Recomp CLI against the reviewed config and archive complete
diagnostics privately. Zero unhandled instructions is necessary but does not
prove complete reachable-code coverage. Trace unresolved indirect targets and
overlay transitions in representative runs. Stubs are allowed only with debt
records and explicit noncritical proof; gameplay/device/audio behavior cannot
be hidden behind no-ops to satisfy a boot milestone.

Build game C as a local static archive and owned host code as C++20. Separate
compiler options per target; test `-fno-strict-aliasing`, `-ffp-contract=off` and
signed-overflow assumptions against generated helpers instead of enabling
`-fwrapv` globally by habit. Pin recompiler/runtime ABI headers together.

Implement a `RendererContext` adapter covering the inspected virtual methods.
It accepts tasks, captures complete dependencies and maps VI presentation into
the shared capture schema. No window/GPU backend is required. Audit raw
`osDpSetNextBuffer` submissions as well as OSTask display lists; an OSTask-only
host may miss direct RDP buffers. Narrow fork patches belong in authored source
with upstream revision, reason and regression evidence.

All current observed RSP tasks are S2DEX graphics. Preserve the CPU mixer and
indexed-animation routines as guest code; wire `osAiSetNextBuffer`/AI buffer
semantics to the actual PCM sink. Do not introduce an audio RSP recompilation
job solely from the initial plan. If a later task hash/type requires RSPRecomp,
inspect its current parser and IMEM/DMEM contract, add reference evidence, then
implement hash-dispatch and compare its PCM/memory writes. Generated RSP code
stays private. Unsupported used tasks fail with an evidence ID.

Enforce normalized SHA-1 at import/start, even though upstream uses a different
hash scheme. Expose 8 MiB guest memory and validate the startup copy/OS globals.
Implement the verified save device and its status/erase/program/read semantics,
with a fixed format and length, safe writes, process-restart tests and isolation
between ROM profiles. Read-only/read-write save errors must be reported.

### Risks and open inputs

Overlay function boundaries/load registration, OS alias resolution, custom
Flash PIO, FPU/CP0 behavior and task-buffer lifetime can prevent native boot
even with a clean recompiler run. Use the accepted maps and D-017/018 to drive
concrete probes. No new user input is needed
when the approved image/profile and the captured reference runs are sufficient.

### Build and verify

Root CMake targets now build `sc64_game`, `sc64_capture`, and `sc64_flash_test`.
`tools/recompile/README.md` documents private symbol generation; the native workflow
is in `native-runtime.md`. Compare native task/VI/audio traces with the original
corpus, then run a timed ten-minute idle/menu/demo session with bounded logging,
assertions, thread/queue telemetry and memory diagnostics. Exercise save/reload
and clean stop/restart, not only startup.

### Acceptance

- [x] Validated symbols and sections; all overrides audited, no game-function stubs.
- [x] Zero unhandled instructions and no unresolved indirect target in the native corpus.
- [x] Desktop native title/menu identified from captured CPU bytes, GBI and nonzero PCM.
- [x] CPU audio/AI retained with canonical file PCM; no observed RSP workload dropped.
- [x] Original game save survives cold-process restart/reload with the verified device protocol.
- [x] Ten-minute menu run completes with timed AI/WAV output, no crash or deadlock; telemetry bounds task queues.
- [x] Complete pre-task native snapshots, VI and original scene matches support Stage 2 differential work.

The accepted sink is WAV, not sustained SDL dummy playback; D-028 must close for
Stage 3 live audio. Source images and GBI census do not establish rendered-pixel
parity. Physical NTSC timing and complete campaign behavior remain separate gates.

## Stage 2 — Offline gfx_core and software reference (accepted RGB corpus)

### Plan and scope

Build a platform-independent interpreter using only the recorded GBI/RDP
families and modes. Maintain a command-coverage manifest with scene/task evidence
for every implemented operation. S2DEX2 BG_COPY, BG_1CYC and OBJ_LOADTXTR
are mandatory. Snapshot the CPU CI8/TLUT base, convert it through the original
BG_COPY command and preserve later RDP layers and ordered palette updates.
Support GBI control flow/segmented resolution; new microcode switching requires
new evidence. Preserve native 2P 512×384 and interlaced VI presentation.

Unknown used commands fail with PC/raw words/ucode identity. Bound every pointer,
DL stack, branch traversal, descriptor, texture load and output allocation.
Distinguish GBI commands, multi-packet texrect parameters and raw RDP command
lengths. Interpret pipeline syncs and target changes as ordering/state semantics,
not automatically as host GPU stalls.

### Implemented DrawList contract

`native/gfx_core/gfx.hpp` implements the owned in-memory v1 contract described
in [Stage 2 workflow](renderer.md). It is authored host data, not recovered
game structs. Integer rectangles preserve UV derivatives; GPU vertices are
produced by the future backend. TMEM textures own decoded physical RGBA8 atlases
and addressing state; background records own the full CPU source image.

| Record | Required information |
|---|---|
| Frame header | Schema, field/task sequence, source memory generations, VI state and active rectangle |
| Vertex data | Signed fixed-point/subpixel position, UV basis/derivatives and color with documented units |
| Ordered command | Texture/combiner/othermode keys, scissor, target generation, vertex/index range, cycle mode |
| Texture payload | Decoded RGBA8, dimensions, TMEM source/format/stride, TLUT, addressing/filter parameters, hash |
| Target operation | Target address/format/dimensions, load/preserve/clear behavior and required writeback/dependencies |

Keep texrect X/Y quarter-pixel values and S/T fixed-point data/derivatives exact
until the rasterization transform. Expand objects into explicit primitives only
after interpreting their matrices/scales/record formats. Resource keys are
content-based and collision checked; guest pointer addresses alone cannot be
texture identities. Specify integer widths, overflow/range policy, serialization
endianness, ownership and bounded memory budget. Reject future-schema captures.

### Texture and state correctness

Model TMEM loads, line/stride, odd-row swaps and split-bank cases exactly for
observed formats. Cover the requested CI4/CI8/I4/I8/IA4/IA8/IA16/RGBA16/RGBA32
when the corpus uses them; add YUV/depth or other formats only if evidence demands
them. Capture TLUT state and palette changes. Test observed LOADTILE and partial loads, adding LOADBLOCK/DXT only on
evidence; test overlapping tiles, mip/mask/shift/clamp/mirror and boundary pixels.
The cache key includes bytes, palette and all decoding/addressing parameters.

Implement the observed 1-cycle and COPY semantics first. Add 2-cycle/FILL
only if a new accepted capture uses them. Texrect
edge inclusion, derivative scaling, half-pixel transforms and COPY's special
rules must be compared against original results, not copied from host quad
intuition. N64 filtering is not automatically ordinary host bilinear filtering.
Preserve signed intermediates and avoid float rounding that creates tile seams.

Parse complete combiner/blender/othermode state, including alpha comparison,
dither/depth/coverage when used. The software backend is an independently
validated reference for our interpreter, not an automatic oracle for itself.
Ordinary host blend state may not express every N64 blend/coverage operation;
if an observed mode requires feedback or a reference fallback, define that path
before claiming support. Order and memory-side effects limit batching: only
adjacent equivalent commands with no intervening dependency may merge.

### Offline rendering and metric

Implement a runner reading the Stage 1 capture schema and emitting native
resolution PNGs, per-frame metrics and difference images. Compare against the
accurate original emulator corpus and inspect on-screen UI/palettes/edges.
Use consistent active rectangles and decide whether VI filtering/deinterlacing
is included; do not compare an unfiltered render target to filtered scanout and
claim matching semantics. Validate software fixtures with hand-calculated cases
and independent original outputs to avoid shared decoder/rasterizer mistakes.

**Frozen acceptance metric:** RGB PSNR >= 40 dB on each of at least ten frames,
with 8-bit range 255 and identical dimensions, and no visible palette errors,
missing objects, tile seams or ordering errors. Exact matches have infinite
PSNR. Twenty original pre/post tasks pass: minimum 41.610483871 dB, four exact
RGB matches. Compare full native RGBA16 targets before VI; filtered scanout and
hidden coverage remain D-029. The threshold was frozen before judging outputs
and was not lowered. Averaged scene metrics cannot hide a failing frame.

### Risks, build and acceptance

Main risks: S2DEX variant differences, captured mutable texture dependencies,
CPU/RDP feedback, fixed-point edge rules and blend/coverage approximation. The
working build is a CMake gfx_core/offline-render target created during this
stage; record actual commands when it exists. Targeted fixtures plus captured
frame regressions are required, followed by a documented visual pass.

- [x] Every opcode/state/format used by the accepted RGB corpus executes; new unsupported modes fail explicitly.
- [x] Synthetic TMEM/TLUT/addressing and fixed-point tests pass with independent expected values.
- [x] At least ten original frames pass the frozen per-frame metric.
- [x] Menu, briefing, 1P and split-screen have no visible seams/palette/object errors.
- [x] CPU-image composition/writeback preserves observed ordering and feedback semantics.
- [x] Batching and cache invalidation preserve baseline output.
- [x] DrawList ownership, target dependencies and mailbox-drop policy are finalized in an ADR.

**Executed result:** `local/reports/renderer/acceptance-review-fixed.json`; 20 fenced
original frames, visual review, C++ fixtures/ASan/UBSan and root host regressions.
The software renderer also renders native Stage 1 task packets. No interactive
shell window, live audio or Android proof is implied.

## Stage 3 — Desktop engine-shell integration

### Executed desktop status (2026-10-07)

The macOS arm64 local relink of the former engine, native session/virtual-time
bridge, independent miniaudio output and the former engine's compiled-quad
presentation are implemented. The
backend uses the accepted CPU rasterizer to generate the native target texture
(ADR-008); it does not yet implement GPU RDP geometry/combiner execution. Twenty
accepted targets passed exact GPU presentation checks, and the user confirmed
audible sound. Current-build freeze/resume/paused shutdown passed the bound live
checks. The Wasteland location card was visually identified, and the same guest
pad route reaches its map. Live keyboard events were subsequently recorded in
an interactive launch without an input recipe. The revised schema 2 resource
integrity, resume and paused-stop gates passed in `resume-stage4-gate-01` and
`paused-stop-stage4-gate-01`. Stage 4 is now permitted on the macOS arm64
desktop baseline. Other platform and device debts remain separate.
See [desktop.md](desktop.md) for
the actual build/run procedure, API audit, limitations and acceptance checklist.

### Plan and capability proof

Prove the former engine's graphics/render submission with a small owned
capability scene linked against its pinned SDK before connecting the game, using
its actual declarations and supported resource paths rather than invented
members, foreign GPU contexts or direct GL/Vulkan commands. If the preferred
route cannot be linked or safely ordered, use the software/reference rasterizer
to create a frame texture, upload it on the engine's render thread and display
an ordinary quad. Record measured bandwidth/CPU cost and the changed performance
risk in ADR-008.

### Extension, host and lifecycle

Package the authored bridge and private game/runtime archives locally with the
pinned engine's native-extension conventions (C++20, archive ABI/architecture,
PIC, system audio dependencies and link order). Keep the authored bridge separate
from generated C and verify no game library is copied as an engine resource.

Initialize owned host state and Lua registration in the verified lifecycle
callbacks. Do not start gameplay until an accepted ROM has been imported and
validated. Loading can fail/cancel/retry without leaking threads. Finalization
must handle partial initialization, multiple Lua contexts and shutdown while
paused. Expose ready/loading/error/paused/stopped state to the UI.

Use actual event enums from the pinned engine. Desktop iconify/deiconify is one
signal; activation/deactivation and a verified Android/native lifecycle bridge
are required later. Focus loss clears held buttons/gestures; it enters the pause
protocol only inside a mission (guest mode 3, including build and modal UI).
Front-end screens continue with input blocked. Desktop iconify and explicit user
pause always freeze the guest (ADR-041). Distinguish app suspension from an audio-device change. Resume must
recover GPU resources if the engine backend requires it and restart audio
without changing guest game speed. All resource destruction remains work on the
shell's main thread after the game/graphics producers have stopped.

### Presentation backend

Consume immutable DrawLists on the engine/render thread. Use bounded dynamic
vertex/index-buffer rings and documented update/lifetime rules. Do not assume a
three-frame ring is safe if the GPU can still use an old buffer; use supported
engine upload paths, resource versions or explicit completion facilities only
when the pinned API exposes them.

Create an RGBA texture cache keyed by Stage 2 state/content identities, with
collision checking, LRU limits, deferred deletion and per-frame upload telemetry.
Never evict resources referenced by current/in-flight draws. Handle content
updates, palette changes, target aliases and resumed/context-recreated resources.
Choose a measured memory cap by desktop/mobile profile rather than an unbounded
cache; reject an allocation cleanly when the backend cannot support it.

Start with an uber-shader representing the observed combiner/cycle inputs and
material variants only when required. Map the verified blender subset to engine
state; route unsupported coverage/feedback cases through the Stage 2 fallback.
Prove the GPU path matches software/original frames before shader specialization
or batch reordering. Preserve scissor origin, draw order, target boundaries,
depth/cull where used and engine state ownership across the surrounding GUI.

Render into the active native N64 target size from captured VI/color-image state,
not a hardcoded assumed 320x240. Present via integer scaling or selected filtering
and letterbox. Record viewport origin and scale for inverse touch mapping. Keep
GUI overlay rendering and the game offscreen pass independent but consistently
ordered. Display-rate changes affect presentation only.

### Audio and ROM/persistence UI

Connect the verified AI PCM path to a bounded sink outside engine sound. Choose
miniaudio for a portable sink or AAudio for Android after checking current source
and platform support. Preserve signed sample format, channel order, guest AI
frequency/buffer boundaries and sample count. Resample to the actual device
rate and handle underruns, device changes and pause flush/drain with telemetry.
Audio callbacks perform no allocation, blocking guest locks, Lua or graphics work.
The [AAudio guide](https://developer.android.com/ndk/guides/audio/aaudio/aaudio)
is the implementation reference; no AAudio prototype is assumed in this plan.

Desktop file selection imports a local ROM into a private store and checks its
normalized SHA-1 before activation. Android later supplies a SAF content stream,
not necessarily a filesystem path: copy it locally with bounded size, normalize,
verify and commit atomically. Cancel/failure leaves the previous valid import
usable. Save files and configuration use platform-private storage, explicit
profile/version checks and robust writes. The ROM never enters the app bundle.

### Proposed Lua contract

Names below are project APIs to implement, not existing engine functions:

| Call | Intended behavior |
|---|---|
| `sc64.load_rom(path)` | Request validated local import/start; return a request/state result and report completion/error |
| `sc64.set_pad(player, buttons, sx, sy)` | Queue/clamp an input snapshot for a guest polling boundary |
| `sc64.touch(event)` | Queue structured phase/id/coordinates/time; direct semantics arrive in Stage 4 |
| `sc64.pause(enabled)` | Request the guest safe-point protocol; report actual resulting state |
| `sc64.get_info()` | State, accepted profile, timing/audio/queue/cache counters, last error |

Define return values, asynchronous completion, coordinate units, player range,
button bit layout, analog range and error behavior in a versioned binding contract
before coding. Lua/GUI calls enqueue requests; they do not touch executing guest
RAM or call the graphics API from a guest thread.

### Risks, build and verify

Public header declarations do not guarantee context availability, shader
creation, state ordering or lifetime correctness. Capability tests must settle
those points. Build any engine linking the game archive locally; record the
SDK/hash/platform and the exact invocation once it is configured, then test
actual engine runs rather than source-only compilation. Initially use
keyboard/physical controller on desktop.

### Acceptance

- [ ] Capability scene compiles, links and renders through the engine's public SDK only.
- [ ] Desktop shell reaches title/menu and the first mission with actual sound/input.
- [ ] Reference captures remain within Stage 2 metrics on the shell's GPU path.
- [ ] Guest VI cadence matches the measured nominal NTSC target (approximately 60 fields/s), independent of host presentation FPS.
- [ ] Minimize, focus loss, resume, device changes and clean shutdown do not corrupt state or leak resources.
- [ ] ROM rejection/cancel/retry and save/reload work from private storage.
- [ ] Thread assertions confirm no graphics calls from game/runtime worker threads.
- [ ] Bounded buffers/caches and telemetry remain stable during a ten-minute mission/menu run.

## Stage 4 — Touch control for RTS (CLOSED desktop scope)

The user accepts closure on 2026-10-08 (ADR-038). The desktop controller path
and reported mouse-only mission support Stage 5 entry. The original physical
touch-only mission criterion moves to D-041 without being certified. The design
and historical checklist below retain remaining work as Stage 5/device or
expanded-workload checks; [input.md](input.md) defines closure.

The permanent virtual controller was rejected in human testing. The default
Stage 4 path is now gesture-to-controller translation, with an optional F3
diagnostic pad/editor. Read-only cursor feedback is established for NTSC-U 1P
and fed from owned display-task snapshots. See [input.md](input.md).

### Plan: gesture controller

Implement mouse hover/left select/right order, tap select, one-finger selection
drag, two-finger contextual tap and a transient command panel. Steer the original
stick using fresh cursor feedback; only press A/B after reaching the point.
Bound the queue and cancel on focus, resize, pause, stale feedback during a drag
and competing controller input. Preserve original hit testing and order logic.

The original manual documents A-held drag selection. A separate selection patch
is unnecessary for this path. Human desktop testing confirms usable cursor
selection/orders. Interface input now uses researched read-only mode/widget/font
feedback to navigate original selections and confirm messages, pause buttons and
build-grid items (ADR-028). Camera pan, groups, expanded modal equivalence and
physical multi-touch require further validation under D-041/D-042. The physical
touch-only mission gate now belongs to Stage 5 (ADR-038).

### Original-game investigation for direct actions

Use controlled emulator input and RAM pre/post deltas to identify cursor,
camera, selection, command/build state and group behavior. Version-checked cheat
mineral/gas addresses are tentative state anchors, not definitions of structures.
Cross-reference the code reading/writing each candidate. Record coordinates,
units, player ownership, bounds, timing and pointer lifetime in `research.md`.

Controller translation needs no guest write or world transform. If later work
requires a direct guest patch, prove select/order functions and prerequisites before choosing
RECOMP_PATCH or queued guest-memory access. Inspect the pinned patch mechanism
and header definitions before writing patch declarations. Every patch includes
ROM/overlay identity, function address/name, expected behavior, entry/exit state
and a reversible baseline comparison. Apply requests in the guest execution
context at a safe point, not from the shell's UI thread.

### Direct-touch semantics to validate

| Gesture | Requested behavior | Evidence needed |
|---|---|---|
| Tap unit/UI | Move cursor then select/activate | Original cursor/button hit testing and command-state rules |
| Tap terrain with selection | Context-sensitive move/attack/order | Original target classification and order dispatch |
| One-finger drag | Selection rectangle | Original support; otherwise a separate patch design and scope decision |
| Two-finger drag | Camera pan | Camera units/bounds and split-screen ownership |
| Long press | Radial command menu | Legal actions for current selection/build/modal state |
| Hot command/group panel | Common build/group actions | Identified original paths and behavior, not invented shortcuts |

If original drag selection is absent, record that result and estimate a patch
that creates a selection through proven guest functions. Do not assume that
writing a rectangle into RAM creates a selected group. If implementation would
require a new selection subsystem, review that concrete scope before proceeding.
The physical touch-only mission remains a Stage 5 exit criterion (D-041); it
does not block the user-accepted desktop Stage 4 closure (ADR-038).

Inverse mapping first converts OS/shell touch units into the actual rendered
viewport: reject letterbox taps, divide by the selected scale, account for the
active N64 rectangle/VI transform and select the player viewport. The controller path lets the game resolve
world coordinates; only a later direct-order patch needs a proven world mapping. Validate HiDPI,
resizing, orientation, integer and filtered scaling. Do not invent an affine
world transform if original hit testing uses another representation.

Arbitrate tap/drag/long-press/camera gestures so a second finger cancels a pending
select rather than issuing an accidental order. UI/modal layers consume input
before terrain actions. Add visible feedback for cursor, selection, invalid
commands and long-press activation without exposing research internals to players.

### Risks, build and acceptance

Risks are unproven state addresses, modal-command ambiguity, cursor latency
and cross-thread patch races if a later direct guest patch is introduced. Build using the accepted desktop
pipeline. First replay synthetic multi-pointer events and record gameplay
equivalence against the physical-pad baseline. Then perform the mission walkthrough
using direct touch events on desktop/touch hardware or an explicit event replay;
Android validation follows in Stage 5.

- [ ] Editable virtual-pad layout persists and input clears on every cancel/focus path.
- [x] Read-only 1P cursor anchors have original runtime and code evidence.
- [ ] Gesture equivalence in modal states and complete mission has runtime evidence.
- [ ] Tap, orders, selection, camera, command/build and groups work in relevant game states.
- [ ] Letterbox/viewport/HiDPI/resize coordinate checks pass.
- [ ] Physical controller connect/disconnect toggles the overlay correctly.
- [ ] The first Terran mission is completed through direct touch with the virtual gamepad disabled; record the complete walkthrough.

2026-10-08 human report: the user completed a mission with the mouse alone.
This supports the desktop controller-translation path. The mission identity and
physical-touch walkthrough were not provided, so the touch-only checkbox remains
open under Stage 5 / D-041. Esc and Android system Back are now aliases for the original B/Back action;
Android hardware validation remains in Stage 5.

## Stage 5 — Android, local builds and optimization (CLOSED scoped)

Stage 5 closes on 2026-10-09 under ADR-055 and
[stage5-acceptance.md](stage5-acceptance.md). Follow [android.md](android.md) for
the packaging implementation and historical platform risks. A personal arm64 APK builds
locally and runs in the Android 16 emulator (ADR-042) and physical phone.
SAF import, AAudio PCM, cold ROM restart and bounded Home/return have emulator
evidence; phone menu sound has scoped user acceptance (ADR-051). ADR-052's
texture optimization preserves all 20 original-corpus outputs and reduces
offline main-menu interpretation time by approximately 76%; this is not a
phone frame-rate certification. The user accepts the first Terran touch-only
mission and save/load after restart on the phone. Back/Home on the mission map and
expanded helper FPU probes also pass. Full numeric exceptions and broader
device/backend/thermal qualification remain deferred. ADR-054 verifies bounded startup and
Home/return on a real 16 KiB Android 16 ARM64 emulator through both Vulkan and
OpenGL ES. See [performance.md](performance.md) and
[android-runtime.md](android-runtime.md).

### Local arm64 toolchain and linking

Pin Android SDK/NDK, API level, compiler, CMake and the matching former engine.
Compile the actual generated game/RSP code locally for `arm64-v8a` with the NDK
toolchain, archive it as `libsc64_game.a`, then link into the native extension.
The accepted personal build used the direct local CMake relink of the former
engine (ADR-042/ADR-055); its conventional container build packaging was an
optional alternative under D-035. Record compiler switches and library hashes;
the static archive alone does not prove the final engine/ABI works.

Baseline generated-code switches are `-O2 -fno-strict-aliasing -ffp-contract=off`;
verify their application to the generated C target. Evaluate `-fwrapv` with
signed-overflow probes and generated helper inspection. Avoid fast-math and
unmeasured architecture-specific vector transformations. Check PIC, link order,
exception/thread/runtime library settings and symbol resolution against the
final link compiler's ABI. Do not let generated C appear in a remote build payload.

16 KiB support is a final ELF/package/runtime property, not a property of `.a`
files. Use the current [Android page-size guidance](https://developer.android.com/guide/practices/page-sizes)
to check all final LOAD segment alignments and APK native-library alignment,
including the engine/shell, libc++ and audio dependencies. Test on a real 16 KiB system
or the supported image and verify its page size. Remove fixed 4096-byte host-page
assumptions; guest 8 MiB RDRAM and N64 address granularity are separate concepts.
Recheck the pinned final linker options if the final link uses an older NDK.

Test guest FPU behavior on ARM64: rounding modes, signed zero, NaN comparisons,
conversions, denormals and FCR31 exceptions used by executed code. Save/restore
FPCR state where required at guest-thread/host boundaries and avoid leaking guest
modes into audio or the shell. Compare results to the original/captured numeric
workloads; a successful compilation is not floating-point compatibility proof.

### Platform integration design and broader qualification

Implement the SAF import bridge through the platform API after checking installed
NDK/JNI interfaces. A content URI is copied as a stream into private storage,
bounded, normalized and SHA-1 checked; errors/cancel and process recreation are
explicit UI states. Persist saves/configs separately. Do not require a globally
readable external-storage path or bundle a ROM for convenience.

Verify actual Android activation/pause/surface/device behavior; desktop iconify
callbacks are not the Android protocol. Exercise Home/return, lock/unlock,
permission/file-picker cancellation, interruption, surface recreation and cold
process restart with persistence. Reopen the audio stream when needed without
holding its callback lock; reinitialize shell resources on their owning thread.

### Performance experiments (expanded device/thermal qualification deferred)

Freeze device/backend profiles before claiming performance: at least one named
midrange Adreno device and one named midrange Mali device, their OS/driver/thermal
conditions, and supported GLES3/Vulkan builds. The exact hardware is an open input,
not a generic assertion that all midrange phones work.

Collect guest thread time, task latency, VI jitter/missed scheduling, PCM queue
depth/underruns, interpretation/rasterization time, mailbox replacements, texture
uploads/bytes, cache usage/evictions, draw calls and GPU/presentation timings via
available engine/system profiling. Compare menu, 1P battle, split-screen and
cinematic workloads; repeat the mission walkthrough. Run a minimum 15-minute
continuous session per device/backend and record temperature/throttling plus
beginning/middle/end performance, not only a cold-start average.

Optimize only measured bottlenecks: reduce redundant decode/upload work, reuse
immutable resources, batch adjacent equivalent draws, avoid copying all RDRAM in
the production parser, and specialize shaders only if justified. Preserve a
slow reference path for differential checks. Each optimization reruns its
affected reference frames and gameplay/input/save tests.

### Build, verify and acceptance

Document the exact local NDK/archive/engine-relink build sequence, archive
selection and private APK output when implemented. Device installation/testing
is performed only after the desktop gates. The current commands and scoped
implementation/device receipts are in `android.md`; `performance.md` documents
the completed texture-processing optimization slice.

- [x] Local arm64 game archives link into the matching former Android engine;
      the observed audio path is CPU PCM, with no required RSP audio archive.
- [x] Local build audit verifies no remote private-input uploads or generated
      source in the APK; only the user-authorized personal option includes ROM.
- [x] ROM import/private persistence have bounded native evidence; touch-only
      first Terran mission and save/load after restart are USER-ACCEPTED on the phone.
- [x] All final native libraries/package alignment pass and the app runs on a
      verified 16 KiB environment (bounded Android 16 ARM64 Vulkan/OpenGL ES
      startup and Home/return, ADR-054).
- [x] Established ARM64 helper FPU profile passes on desktop, phone and 16 KiB
      Android; exhaustive guest exception/FP16 behavior remains unqualified.
- [x] Actual Android Back opens/closes the original mission menu; Home/return
      freezes/resumes guest/PCM/presentation in the same mission process.
- [x] Desktop/native/Lua/Python regressions pass (13 CTest and 149 Python/Lua).

Expanded device/input/surface/audio-recovery profiles and Adreno/Mali original
frame parity plus 15-minute cadence/thermal runs are deferred by user scope.
They are not asserted successful or required by the current Stage 5 closure.

## Stage 6 — Withdrawn optional presentation experiment

The user withdrew Stage 6 on 2026-10-09 after rejecting HD fonts and finding the
Original/Sharp/Smooth choices unnecessary. ADR-060 supersedes the experimental
presentation decisions. Stage 6 is cancelled by scope change, not certified as
an implemented HD/widescreen feature.

All replacement fonts, sampling variants, presentation preference persistence,
scale selectors and their bindings/CLI options are removed. Original font artwork
and nearest sampling remain; aspect-preserving Fit is fixed across desktop and
Android. Rendering, pointer inversion and GUI layout share this viewport. No
wider world-view patch is enabled; widescreen work is no longer a closure gate.

- [x] User resolves scope: remove the complete optional presentation experiment.
- [x] Original typography and image shader restored; fixed Fit replaces selection.
- [x] Old preferences/launch keys cannot re-enable withdrawn features.
- [x] Fresh desktop/Android rebuilds, regressions, original pixel and bounded
  phone installed-artifact/Home-return checks complete (presentation.md).

Build/run and final evidence are in [presentation.md](presentation.md). Preserve
Stage 5 acceptance, saves, signing identity and historical private reports. Future
HD or wider-camera work requires a new explicit request and original-behavior
experiments; the cancelled experiment is not a claim of compatibility.
