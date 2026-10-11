# Stage 0: reproducible investigation workflow

## Plan, risks and outstanding inputs

Order: identify the supplied image, generate a tentative segmentation, identify
OS candidates, capture original execution, reconcile addresses and device use,
then decide the rendering path. Do not implement the port during this stage.

Stage 0 is complete for the supplied revision and named scene corpus. The
investigation resolved the two overlapping plain-code overlays, active S2DEX2,
CPU CI8 scene construction, CPU audio/animation and Flash save/reload. Evidence
and bounded unknowns are in `research.md`. No game port is implemented yet.

Commands below use a POSIX shell on Linux/macOS or WSL2. The completed run used
macOS arm64, a local Linux container for n64sym/IDO references, and the locally
built original-ROM ares/Angrylion harness. These are actual research runs;
Windows/Linux native game and Android execution remain later gates.

## 1. Analyze and normalize without changing the source

From the project root, set a task-specific root variable:

```sh
SC64_ROOT="$PWD"
mkdir -p local/roms local/reports local/splat-work local/symbols local/captures
python3 tools/rom_info.py "StarCraft 64 (USA).z64" \
  --normalized-out local/roms/sc64.ntsc-u.z64 \
  --output local/reports/rom-info-normalized.json \
  --expect-sha1 a36d91b5aac7bb95df0d7de5f9814f5270e25c2b
python3 -m unittest discover -s tests -v
```

Both output paths must be new. Use a new report name on subsequent runs; the
tool deliberately has no overwrite flag. Omitting `--normalized-out` normalizes
only in memory. Exit 0 means a report was produced, exit 2 means invalid input,
hash mismatch, an unsafe output path, or an I/O failure. No runtime is started.

Review `input.sha1` versus `normalized.sha1`, raw entrypoint, region/revision,
IPL3 family and identifier offsets. Preserve raw header fields. Do not interpret
the release word as the publication year or derive save hardware from the header.
Write research observations with the normalized hash as their scope.

## 2. Pin splat and create a tentative configuration

The checked entry point is `python -m splat create_config ROM`. Installing a
source checkout isolates its version from whichever package may be on PATH.
The transitive Python dependencies must also be recorded before reproducible
research runs; installing a pinned splat alone does not pin rabbitizer/spimdisasm.

```sh
mkdir -p third_party
git clone https://github.com/AngheloAlf/splat.git third_party/splat
git -C third_party/splat checkout --detach 1d09139b886f0bece632bd8f367ccc1d3318ca2a
python3 -m venv .venv
.venv/bin/python -m pip install -e "third_party/splat[mips]"
.venv/bin/python -m pip freeze > local/reports/python-environment.txt
.venv/bin/python -m splat --help
mkdir -p "$SC64_ROOT/local/splat-work/new-run"
cd "$SC64_ROOT/local/splat-work/new-run"
"$SC64_ROOT/.venv/bin/python" -m splat create_config "$SC64_ROOT/local/roms/sc64.ntsc-u.z64"
```

In this revision, the title-derived output is `starcraft64.yaml`, accompanied by
`symbol_addrs.txt` and possibly `reloc_addrs.txt`. `create_config` writes files in
the current directory and can overwrite them, so use a fresh work directory.
Its output is heuristic, especially for nontraditional startup. Examine it
before splitting. Confirm its SHA-1, absolute/relative `target_path`, `base_path`,
entry VRAM, guessed main/BSS bounds and final ROM-size sentinel.

```sh
"$SC64_ROOT/.venv/bin/python" -m splat split starcraft64.yaml
cd "$SC64_ROOT"
```

All generated assembly, binary subsegments and tentative symbols stay under
`local/splat-work`. No generated linker/script/assembly is automatically promoted
to public source. Review outputs and record the exact tool/dependency versions.

### Map executable loading rather than guessing code ranges

1. Disassemble startup from the header entry mapping. Follow its jump, copy,
   zero/BSS and OS initialization operations; validate against RAM in execution.
2. Give every segment a unique identity: ROM start/end, RAM start/end, compressed
   source range if any, decoded hash, relocations and lifetime.
3. Trace PI DMA and CPU writes to ranges later executed. A data DMA is not an
   overlay until the destination is executed; compressed assets are not compressed
   code merely because both use the same archive.
4. If code is decompressed, analyze the decoded image privately with a parent
   hash and a reproducible decoder. Keep original-ROM offsets and decoded-image
   offsets distinct; a synthetic recompiler image needs its own mapping manifest.
5. Trace indirect calls, jump tables, secondary entrypoints and overlapping VRAM
   overlays. Identify where code can replace a section at the same address.
6. Correct splat's segments and function sizes from this evidence. Do not run an
   address-only converter over labels and call the result complete symbols.

## 3. Find libultra candidates with n64sym

The upstream README recommends a RAM dump over a ROM scan because startup
mapping/compression can make ROM-derived addresses inaccurate. Initial ROM
candidates remain useful; save them separately from validated runtime symbols.

Build the pinned utility on Linux/WSL2 with a C++ compiler and Make:

```sh
git clone https://github.com/shygoo/n64sym.git third_party/n64sym
git -C third_party/n64sym checkout --detach ccf4600f3389f1a84bde23339225cf372fdf7712
make -C third_party/n64sym
third_party/n64sym/bin/n64sym local/roms/sc64.ntsc-u.z64 \
  -s -f splat -o local/symbols/n64sym-rom-candidates.txt
```

The inspected Makefile assumes static GNU linking. It is not a verified native
macOS build recipe; use a local Linux development environment for this utility
or port its build system separately and record the patch. Do not upload the ROM
to an online symbol-finding service.

After a capture produces canonical big-endian RDRAM starting at physical zero:

```sh
third_party/n64sym/bin/n64sym local/captures/menu/rdram-before.bin \
  -s -f splat -o local/symbols/n64sym-menu-candidates.txt
```

Use the default `0x80000000` RAM displacement only for that exact zero-based
dump layout. A partial dump needs a checked displacement; verify the pinned
tool's `-h` parsing and its resulting addresses before trusting them.

Built-in signatures span several library versions; a hit does not identify a
unique libultra revision. To narrow the version, use legally available local
reference libraries or build matching variants of the reverse-engineered
[ultralib project](https://github.com/decompals/ultralib). Its documented pattern,
for example for the L ROM variant, is:

```sh
git clone https://github.com/decompals/ultralib.git third_party/ultralib
git -C third_party/ultralib checkout --detach e24c836796df4bf520ff8b11a5c9d2cea3a66cbd
make -C third_party/ultralib VERSION=L TARGET=libgultra_rom COMPARE=0 setup
make -C third_party/ultralib VERSION=L TARGET=libgultra_rom COMPARE=0
third_party/n64sym/bin/n64sym local/captures/menu/rdram-before.bin \
  -l third_party/ultralib/build/L/libgultra_rom/libgultra_rom.a \
  -f splat -o local/symbols/n64sym-L-candidates.txt
```

This is an example reference variant, **not a claim that SC64 uses L**. Follow
ultralib's build dependencies/compiler setup and supported version/target matrix.
Repeat only plausible variants, preserving compiler settings and library hashes.
Modern-GCC output generally cannot replace historical compiler output for byte
matching.

### Validate names and runtime coverage

For each candidate record original ROM/RAM/overlay address, size, reference
variant/object, matching ranges, relocation masks, conflicting names, callers
and confidence. Perform exact comparisons where relocations do not change bytes;
for relocated instructions, explain each ignored field and compare the remaining
instructions and control flow. Resolve aliases and secondary entries explicitly.

Rename validated functions in the symbol input to their actual libultra names.
In the inspected N64Recomp symbol-input path, replacement selection is an
exact-name lookup in `src/symbol_lists.cpp`, not a magic TOML option. Then check
that the pinned librecomp/ultramodern version implements the matching wrapper and
that its ABI/device semantics cover the observed use. Search both OS entrypoints
and compiler helper routines; identification alone is not wrapper compatibility.

Produce a reviewed census with columns: guest symbol, location, size, matching
evidence, calls by scene, replacement symbol, implementation source and status.
Any unmatched hardware access must be traced. Do not copy the whole upstream
replacement list into the game's inventory without confirming those functions.

## 4. Record original display lists and memory attribution

Follow [the executed capture workflow](reference-capture.md). It pins and builds
ares-64 with the original Angrylion reference core, source-only hooks and native
adapter regressions. Authored controller recipes reproduce the named scenes.
There is no invented stock `--dump-display-lists` option. The actual capture
schema is `events.jsonl` plus referenced bounded canonical RAM/DMEM/data blobs,
input, PNG/WAV, Flash and end-state files under ignored `local/captures/`.

Capture before SP task execution, at every DP flush and on VI scanout. Include
nested object/texture/palette dependencies through bounded full RAM snapshots.
Attribute logical CPU accesses in interpreter windows including cache hits;
attribute actual reference RDP stores and last-writer ownership separately.
Record AI and save-device activity, not only display lists. Distinguish the
runner's initial inactive-video fallback ticks from actual VI fields.

The accepted original corpus contains title/menu, mission selection, briefing,
1P, actual 2P split screen, indexed opening animation, 4 MiB requirement UI and
Flash save/cold reload. Per-field final runs also record all 14 VI register words.
Task snapshots precede execution, so Stage 2 must explicitly pair task effects
and later VI output before defining differential-image metrics.

## 5. Decode and decide

The inspected libgfxd/gfxdis do not supply the needed S2DEX2 object decoder.
Use `tools/research/summarize_capture.py`, checked against pinned S2DEX2 headers,
for bounded control-flow/background-object census and fragmented raw RDP parsing.
This is a research decoder, not a renderer. A full offline replay backend is
Stage 2. Reject conditional lists or microcode switches requiring unimplemented
semantics instead of reporting a partial decode as complete.

The captured base is CI8, not an independent RGBA16 CPU framebuffer layer.
BG_COPY converts it via TLUT into RGBA16, then RDP draws the UI. Preserve byte
aliasing, palette/image generations and command order. Address overlap with a
color image is insufficient proof of feedback; sampled complete windows found
no consumption of last-RDP-owned bytes. New scenes require new coverage.

The resulting decisions are ADR-006/007/013/014/015. `docs/research.md` records
actual microcode hashes, section intervals, CPU producer/decoder anchors,
Flash protocol, replacement inventory and VI modes with methods of verification.

## Verify the completed stage

```sh
python3 -m unittest discover -s tests -v
python3 tools/research/check_acceptance.py "StarCraft 64 (USA).z64" \
  --output local/reports/research/acceptance-new.json
```

The synthetic suite contains 21 tests. The private gate rechecks real traces,
whole overlay equality, scene modes, Flash identity, library/BOLT evidence and
native adapter probes. The recorded original-screen review remains a separate
part of acceptance; hashes alone do not prove image correctness. Stage 0 is
accepted. No native recompilation, presentation, touch or Android acceptance is claimed.
