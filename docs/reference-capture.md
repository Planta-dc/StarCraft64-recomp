# Executed Stage 0 capture workflow

Stage 0 uses an instrumented desktop emulator running the original user-supplied
ROM. This harness is not a recompiled game, a port renderer or a distributable
personal game build. All byte-bearing outputs, upstream builds and references
stay under ignored `local/` or `third_party/`. The source hooks are C++20.
The evidence ledger and acceptance boundaries are in [research.md](research.md).

## 1. Obtain and pin the research sources

The completed run used macOS arm64, LLVM/Clang 23.1.2, CMake 4.4.4 and Ninja.
Linux is an upstream runner target; a Linux build of this authored patch was not
executed. This does not establish Windows or Android compatibility.

From the repository root, on a fresh checkout of dependencies:

```sh
mkdir -p local/toolchains local/reports/research local/cache/ccache

git clone https://github.com/HailToDodongo/ares-64.git local/toolchains/ares-64
git -C local/toolchains/ares-64 checkout --detach 6b65e1beacf8b2af66aaee72541ab154382b7e6a
git -C local/toolchains/ares-64 submodule update --init --recursive

git clone https://github.com/ata4/angrylion-rdp-plus.git local/toolchains/angrylion-upstream
git -C local/toolchains/angrylion-upstream checkout --detach 9c8b9ed3e7d7f00dff8bc872ccdd3fba1a3673fc

python3 tools/research/patch_ares.py local/toolchains/ares-64 \
  --reference local/toolchains/angrylion-upstream
```

The patcher rejects a different HEAD and checks exact source anchors. Reapplying
it produces the same source contents. It copies the original upstream RDP core,
keeping the fork's API header and adding a headless compatibility bridge. The
fork's GUI texture viewers/metrics are unavailable in this research adapter;
they are not used by the capture runner. Retain upstream licenses. The BOLT
audit tool separately records its GPL-3.0 codec provenance.

## 2. Build the actual desktop runner

On the inspected macOS host:

```sh
cmake -S local/toolchains/ares-64 -B local/toolchains/ares-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DARES_BUILD_HEADLESS=ON -DARES_SKIP_DEPS=ON \
  -DARES_ENABLE_VULKAN=OFF -DARES_ENABLE_CHD=OFF \
  -DARES_PROFILE_ACCURACY=ON -DARES_UNITY_CORES=ON \
  -DCMAKE_C_COMPILER=/opt/homebrew/opt/llvm/bin/clang \
  -DCMAKE_CXX_COMPILER=/opt/homebrew/opt/llvm/bin/clang++
CCACHE_DIR="$PWD/local/cache/ccache" \
  cmake --build local/toolchains/ares-build --target ares-test -j10
```

The target copies its pinned PIF firmware from `mia/Firmware/Nintendo 64/` into
`local/toolchains/ares-build/test-runner/Firmware/Nintendo 64/`. The wrapper sets
`SC64_RESEARCH_FIRMWARE` to the runner directory, avoiding the fork's macOS CLI
app-bundle path assumption. No user-ROM byte goes to a build service. The renderer
is the CPU Angrylion reference; this research choice does not alter the shipped
port's own graphics path.

## 3. Replay authored controller inputs

`tools/research/recipes.json` contains controller inputs and dependency paths only,
not extracted assets or guest instructions. `run_capture.py` launches the pinned
runner with `run_scene.js`, refuses an existing output directory and confines
capture output to ignored `local/`. Use a fresh root when repeating a corpus:

```sh
python3 tools/research/run_capture.py reference-cold \
  --captures local/captures/research-replay
python3 tools/research/run_capture.py reference-4mb \
  --captures local/captures/research-replay
```

`reference-cold` boots with Rumble Pak and records title, indexed opening animation
and main menu. `reference-4mb` boots with 4 MiB and selects two-player mode,
recording the game's Expansion Pak requirement. The port will expose 8 MiB.

For the mission/briefing/save chain, replay the following recipes, each using
`--captures local/captures/research-replay`:

```text
reference-menu -> reference-menu-02 -> mission-01 -> mission-02
-> game-1p-01 -> game-1p-02 -> save-options-01 -> save-options-02
-> save-options-03 -> save-options-04 -> save-game-01 -> save-game-02
```

The options steps preserve the exact recorded navigation, including a missed
one-field key poll and subsequent correction. Do not treat that history as a
universal menu script. For future new input, hold buttons for six fields and
allow settling time; the game need not poll every VI field.

Then run `save-restart -> save-loaded`, and separately `cold-saved-mission-02`.
The cold recipes use **no emulator state**, import only `save-game-02/end.flash.bin`
before guest advancement, and reach the original saved-slot UI and Wasteland.
`cold-saved-mission-02` attaches a formatted Controller Pak, records 24 final
fields and verifies that cartridge Flash persists despite that accessory.

For 2P, use `reference-cold -> menu-2p-01 -> game-2p-01`, then run
`reference-2p-fields` and `feedback-2p` independently from the game's end state.
For decoder attribution, run `intro-decode` using `reference-menu/title.state`.
Savestates are navigation helpers, not cartridge-save proof. The adapter replays
VI register state after loading; backend RDP state is not a general serialized
replay contract. Stage 2 must establish explicit task/image state pairing.

The accepted historical corpus is `local/captures/research/`. Its exact inputs are
also retained in each `input.json`. The scripts use `out=`, `state=` and `flash=`
prefixes because the fork's argument canonicalizer otherwise strips the final
component of an existing directory. Pass the ROM as a file path, not a directory.

## 4. Capture contents and completeness

| Boundary | Recorded evidence |
|---|---|
| SP start | All 16 OSTask words from DMEM `0xFC0`, actual text/data blobs and hashes; bounded pre-task full canonical RAM, DMEM and root data |
| DP processing | Every raw command flush, XBUS or RAM source, words in guest order; analyzer carries multiword fragments |
| VI | Actual field index, CPU profile cycle count, decoded modes; final cold/2P field runs include all 14 register words and per-field PNGs |
| CPU | Complete logical cached/uncached accesses during named interpreter windows; PC/page/count/byte/range attribution |
| RDP stores | Reference rasterizer writes by RAM page; last-writer ownership tracked per byte during attribution windows |
| Feedback | CPU reads of bytes still owned by an earlier RDP write, compared to physical RAM after the real cache/bus read |
| Loading | PI DMA ranges/direction/caller PC and first-executed page snapshots |
| Saves/peripherals | Flash command words and Joybus operation/bank probes; end 128 KiB Flash image |
| Audio | AI buffer/address/length/DAC/caller evidence, bounded PCM blobs and audible WAV |
| End state | Canonical physical RAM plus separate CPU-visible cache overlay, Flash and navigation state |

Interpreter windows switch CPU and RSP away from JIT for bounded attribution,
then restore JIT. CPU access counts outside those windows are not complete.
Execution-page snapshots are first JIT block-entry samples, not an exhaustive
instruction trace or every overwritten page generation. Address overlap alone
is not feedback. No last-RDP-byte CPU read appeared in the named 1P/2P windows;
new campaign cases still need their own coverage.

VI fields differ from runner `waitFrames` during initial inactive-video fallback.
Emulator cycle samples are useful comparisons, not physical-console timing
certification. Do not impose the raw PNG width as the game's framebuffer width.
Menu is 640×480, 1P is 320×240, 2P is 512×384; see the ledger for exact VI words.

## 5. Reference adapter corrections and native probes

Three discriminating checks found research adapter defects:

1. The fork keeps RSP DMEM in MSB byte order, while Angrylion reads native u32
   words. Convert the XBUS staging words through the RSP accessors. Otherwise
   valid SyncFull commands disappear.
2. The fork's altered texture loader rejects the title's valid palette address
   `0x2A6FC6`. Use the entire pinned original Angrylion core; do not patch guest
   addresses or merely bypass an arbitrary crash.
3. A partial RDP command must load `length - position` remaining words. The
   upstream `length - 1` calculation can swallow the next SyncFull.

Build the synthetic probe against the actual corrected reference library:

```sh
/opt/homebrew/opt/llvm/bin/clang++ -std=c++20 -O2 \
  tools/research/rdp_adapter_probe.cpp \
  -Ilocal/toolchains/ares-64/thirdparty/angrylion-rdp-plus/src/core \
  local/toolchains/ares-build/ares/n64/libangrylion-rdp-plus.a \
  -pthread -o local/toolchains/rdp-adapter-probe
local/toolchains/rdp-adapter-probe fragment
local/toolchains/rdp-adapter-probe native-word
local/toolchains/rdp-adapter-probe byte-array
```

Expected SyncFull interrupt counts are respectively `1`, `1`, `0`. The last
case deliberately demonstrates incorrect byte-array input. The uncorrected
upstream fragment case produced `0`. These are native reference-core regression
checks, separate from original-game evidence. The Controller Pak VFS and macOS
firmware-path corrections also live in the patcher; neither modifies game code.

## 6. Decode, audit and recheck acceptance

Generate reports to **new filenames**:

```sh
python3 tools/research/summarize_capture.py \
  local/captures/research/cold-saved-mission-02 \
  --rom "StarCraft 64 (USA).z64" \
  --output local/reports/research/cold-saved-mission-summary-new.json
python3 tools/research/bolt_audit.py "StarCraft 64 (USA).z64" \
  --compare-extracted local/extracted/stage0 \
  --output local/reports/research/bolt-audit-new.json
python3 -m unittest discover -s tests -v
python3 tools/research/check_acceptance.py "StarCraft 64 (USA).z64" \
  --output local/reports/research/acceptance-new.json
```

The BOLT comparison needs the existing private extraction; without it, omit
`--compare-extracted` for a bounds/codec audit without independent equality.
Use the [libultra workflow](../tools/research_libultra/README.md) to regenerate
`local/reports/libultra-resident/inventory.json` from the accepted loaded RAM.
The acceptance checker redecodes RDP streams in 14 named captures and available
bounded GBI snapshots, validates complete command
streams, task hashes, scene modes, CI8 background copies, whole overlay equality,
Flash identity, library/BOLT reports and native probe counts. It writes evidence
and authored-source hashes locally, never game payloads to public documentation.

The completed synthetic suite has 21 tests. The research gate additionally
requires the original-screen review recorded in `research.md`; file existence
and checksums alone cannot recognize a playable map or valid saved-slot UI.
The final ignored report is `local/reports/research/acceptance-final.json`: PASS
with 14 captures and 139 hashed evidence files. A fresh replay after rebuilding
produced byte-identical title/intro/menu PNGs; the patcher also passes a repeated
source-content hash comparison. Stage 2 PSNR, native ten-minute stability, desktop lifecycle and Android cadence
remain separate future acceptance criteria. No Stage 1 code was generated here.
