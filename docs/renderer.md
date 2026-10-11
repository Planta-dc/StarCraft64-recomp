# Stage 2 — Offline S2DEX2 renderer

Current tools live in `tools/renderer`; the offline executable is built in
`local/build/renderer`. To prepare a fresh corpus using the relocated fenced
captures, run `python3 tools/renderer/prepare_corpus.py local/inputs/renderer
--fenced-captures local/captures/renderer` with a new output directory.
`tools/desktop/check_gpu.py` defaults to the resulting
`local/inputs/renderer/manifest.json`. This records current absolute input paths;
historical corpus and run receipts retain their original recorded values.

Stage 2 passes the bounded **native-target RGB** gate on macOS arm64. It is an
independent C++20 `sc64_gfx_core` library, offline executable and synthetic tests.
There is no engine dependency or GL/Vulkan API. This is not yet an interactive
application. Stage 3 must supply presentation, controls and live audio.

## Scope and risks

The input is canonical big-endian 8 MiB RDRAM and the measured S2DEX2 xbus 2.08
root list. The capture adapters check the exact microcode SHA-1
`7d0f686719afde0703d377ccc7a492318c01eec0`. GBI and raw RDP have separate parsers.
Unknown operations fail with PC/raw words. Nested lists, segmented addresses,
packet lengths, memory reads, allocations and command counts are bounded.

Implemented gameplay families: segmented MOVEWORD, DL/ENDDL, BG_COPY, BG_1CYC,
OBJ_LOADTXTR TLUT descriptors, SETOTHERMODE_H/L, three-packet TEXRECT,
SETCIMG/SETTIMG, SETTILE/SETTILESIZE, LOADTILE/LOADTLUT, scissor, primitive,
blend/environment/fog colors, combiner and synchronization. Current draws use
one-cycle/COPY, CI8/RGBA16 TLUT and I8. CI4, I4, IA4/8/16 and RGBA16/32 fetches
also have authored fixtures; that does not establish their use by the game.
Unobserved LOADBLOCK, triangles, object matrices/sprites, BG flipping,
nonzero imageYorig and other cycle families are explicit failures, not stubs.

Remaining questions need experiments, not user input: exact inherited random
state, hidden coverage/AA resolve, scaled S2DEX strip phase and VI filtering.
D-029 records these limits. New framebuffer feedback requires an ordered executor
and expanded original evidence (D-019). Real GPU presentation remains the
Stage 3 capability proof (D-008). No unresolved user preference was needed to
build this offline stage.

## Owned DrawList v1

`native/gfx_core/gfx.hpp` defines the in-memory contract; it is not serialized by
copying host structs. Capture memory and RDP files use canonical big-endian
bytes; RGBA8 payloads use component order R,G,B,A. C++ vectors own all data.

- `FrameIdentity`: task/field, 14 VI words and source RAM SHA-256, filled by the
  eventual runtime adapter; raw offline parsing has no invented VI identity.
- `Rectangle`: signed screen 10.2 exclusive edges, texture S/T 10.5, signed
  derivative 5.10, tile snapshot index, complete target/state and source PC.
  COPY derivatives are normalized to ordinary per-pixel source advance.
- `Texture`: collision-checked content key, canonical physical TMEM/TLUT,
  addressing parameters. Backgrounds additionally own full CPU source colors.
  TMEM indices are physical texels; odd row,
  split RG/BA planes, addressing and filtering are separate sampling operations.
- `State`: complete combiner/othermode, colors and quarter-pixel scissor.
- `initial_ram`: independent canonical 8 MiB packet. Software rendering returns
  another owned RAM image, preserving CPU initialization and ordered target
  stores. COPY preserves palette alpha bits even when alpha compare is disabled.
  One-cycle hidden coverage is not bit exact; RGB metric excludes alpha/coverage.

Rectangles retain fixed point until sampling. The software sampler uses shifts,
mask/mirror/clamp and RDP three-point interpolation, not host bilinear filtering.
Adjacent batches merge only equal texture/target/state; order never changes.
The current implementation keeps ordered rectangles rather than prematurely
rounding them into host float vertices. A Stage 3 backend may generate quad
vertices from this exact basis after capability and GPU comparison tests.

BG_COPY is the presentation of the CPU CI8 image, not an extra CPU overlay.
Source/output aliases are supported by owned source pixels. A texture/palette
load intersecting a preceding draw's target region fails instead of reading stale
pre-task bytes. Only complete presentation packets may be dropped, after guest
memory effects and task completion have been ordered. See ADR-020/021.

Limits: 100,000 GBI/rectangle operations, 32 DL stack entries, 64 MiB owned
texture payload per packet, 1,024-pixel bounded texture/target dimensions,
4,096-byte TMEM and 256-entry TLUT. S2DEX background sources may wrap, but new
phase/flip modes require source experiments before acceptance.

## Build and verify

The default root CMake build also includes the private Stage 1 host. For an
independent renderer build, no ROM or generated game library is needed:

```sh
cmake -S . -B local/build/renderer -G Ninja \
  -DSC64_BUILD_HOST=OFF -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build local/build/renderer -j8
ctest --test-dir local/build/renderer --output-on-failure
python3 -m unittest discover -s tests -v
```

The executed build used LLVM 23.1.2. For differential research only, enable the
pinned Angrylion oracle (`9c8b9ed3e7d7f00dff8bc872ccdd3fba1a3673fc`):

```sh
cmake -S . -B local/build/renderer -DSC64_BUILD_GFX_ORACLE=ON \
  -DSC64_ANGRYLION_DIR="$PWD/local/toolchains/angrylion-upstream"
cmake --build local/build/renderer -j8
```

Angrylion is a separate test executable; neither it nor ares is linked into the
port or `sc64_gfx_core`. Upstream licenses remain with the private checkouts.
The test adapter submits complete RDP commands. Its first arbitrary-chunk
version lost commands at fragment boundaries; those failed reports are retained
and excluded from acceptance.

For address/undefined-behavior checks, configure another build with
`-DCMAKE_CXX_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer'` and
`-DCMAKE_EXE_LINKER_FLAGS='-fsanitize=address,undefined'`, with the host/oracle off.
The native fixtures cover independent endian/TLUT/format/stride/swap expectations,
mirror/clamp/shift, rectangle edges, ownership, malformed packets/control flow,
feedback rejection, COPY alpha-zero stores, alias expansion and batching.

## Original reference contract

Older Stage 0 PNGs are VI scanouts after intervening tasks; they are not exact
pre-task goldens. Stage 2 adds an opt-in source hook to the accepted local ares
harness. `tools/renderer/patch_reference.py` verifies complete source SHA-256
anchors and pinned HEAD before mutation. The hook copies post-task RDRAM and
hidden coverage in Angrylion's FULLSYNC interrupt **after cmd_flush joins the
workers**, before notifying the guest. Pre/post records share a task ID.
`SC64_STAGE2_POST_TASK=1` enables it. Original ROM bytes are never patched.

```sh
python3 tools/renderer/patch_reference.py local/toolchains/ares-64
CCACHE_DIR="$PWD/local/cache/ccache" cmake --build \
  local/toolchains/ares-build --target ares-test -j8
```

`capture_reference.py` normalizes the ROM, verifies the canonical NTSC-U SHA-1
and requires a z64 file before execution, because the ares runner loads it
directly. `--rom` selects the dump (default: the ignored repository-root
`StarCraft 64 (USA).z64`); convert other byte orders with
`tools/rom_info.py --normalized-out local/<name>.z64`.
It uses the existing private original-emulator checkpoints for menu/briefing/2P.
One attempted 1P checkpoint restore stalled without a VI/task; it is excluded.
The accepted 1P experiment cold-boots and loads the original UI Flash save:

```sh
python3 tools/renderer/capture_reference.py main-menu local/captures/renderer/main-menu-02
python3 tools/renderer/capture_reference.py menu local/captures/renderer/menu-01
python3 tools/renderer/capture_reference.py briefing local/captures/renderer/briefing-01
python3 tools/renderer/capture_reference.py one-player local/captures/renderer/one-player-02 --cold
python3 tools/renderer/capture_reference.py two-player local/captures/renderer/reference-2p-01
```

All output paths must be new. The listed names are already present locally;
reproducing them requires a fresh capture root with these same scene-directory
names and passing that root to `--fenced-captures`. No source edit is necessary.
Do not overwrite evidence.

```sh
python3 tools/renderer/prepare_corpus.py local/reports/renderer/new-corpus \
  --fenced-captures local/captures/renderer
python3 tools/renderer/compare.py local/reports/renderer/new-corpus/manifest.json \
  local/reports/renderer/new-comparison --mode gbi
```

The frozen metric is **RGB PSNR >= 40 dB for every case**, full native target,
8-bit range 255. Exact RGB matches have `exact=true`, `psnr_db=null`. No resizing,
masking of failing regions or average-only gate is allowed. Target dimensions are
640×480 menus/briefing, 320×240 1P and 512×384 2P. VI/gamma/deinterlacing are not
included. `oracle_vs_ground_truth` diagnoses inherited-state differences but the
acceptance score uses actual original post-task target bytes, not oracle output.

`compare.py` emits RAM, PNGs, an amplified difference and source/binary hashes.
An explicit visual-review receipt binds all case IDs/contact-sheet hashes to that
comparison. `check_acceptance.py` rechecks binary/input freshness and independently
recomputes each metric from the original post-task snapshots:

```sh
python3 tools/renderer/check_acceptance.py \
  local/reports/renderer/fenced-review-fixed/comparison.json \
  local/reports/renderer/fenced-review-fixed/visual-review.json \
  local/reports/renderer/new-acceptance.json
```

## Native capture preview

Render an existing Stage 1 task. The adapter verifies CAS pages, full RAM,
submitted list and microcode hashes before invoking the interpreter:

```sh
python3 tools/renderer/render_capture.py local/captures/recompile/boot-09 961 \
  local/reports/renderer/new-native-menu
```

The result includes `target-0.png`. It proves the native task can be rendered by
our HLE code; it is not an interactive window or a paired original-frame proof.

## Acceptance checklist

- [x] Independent C++20 build and source-only synthetic fixtures pass.
- [x] Used GBI/RDP/TMEM families in the accepted corpus execute without unknown commands.
- [x] All 20 fenced original frames exceed the frozen individual 40 dB threshold.
- [x] Main/mission menus, portrait briefing, 1P and 2P receive visual review; no missing objects, palette errors or visible tile seams.
- [x] CPU indexed-image composition, alias expansion and explicit feedback rejection are tested.
- [x] Owned atlases/content keys, ordered batching and completion/drop contract are specified.
- [x] ASan/UBSan fixture run passes; the root host build still links and its regressions pass.

The measured minimum is **41.610483871 dB**; four mission-list frames match RGB
exactly. `local/reports/renderer/acceptance-review-fixed.json` is the generated final
gate. Residual amplified differences do not establish bit-exact RDP coverage,
VI output, the full campaign, other desktop platforms or Android.

## Review fixes and regression evidence

The 2026-10-07 review found four defects outside the accepted scene cases.
D-030 through D-033 record their closure:

- Manifest IDs are checked as ASCII filenames, with duplicate rejection, before
  creating any output or invoking the oracle. Both output paths are resolved
  and checked again before invocation. Absolute paths, parent traversal,
  Windows-style paths and escaping symlinks are rejected.
- GBI color/texture image pointers use segment resolution; raw RDP images use
  physical addresses (ADR-022). Tests verify actual guest RAM stores, including
  the untouched region that previously received erroneous writes.
- Negative odd 4-bit S coordinates now round down before byte addressing.
  Hand-expected I4/IA4/CI4 fixtures cover negative even/odd values, row swapping
  and TLUT lookup. These fixtures do not establish new texture use by the game.
- Full-byte S2DEX format/size fields are validated before bit-count shifts or
  source reads. BG_COPY and BG_1CYC reject unsupported pairs deterministically.

The rebuilt host passes three native CTest cases. The standalone renderer and
strict ASan/UBSan fixture build pass; all 64 Python tests pass. Logs are private
under `local/reports/renderer/review-fix-*.log`. A fresh 20-case GBI replay with the
rebuilt binary produces all 60 RGB PNGs byte-identical to the previously reviewed
actual/reference/difference images. Its visual receipt is rebound to the new
comparison hash; the final acceptance checker verifies the new binary and input
hashes and recomputes every score. Earlier evidence remains preserved.
