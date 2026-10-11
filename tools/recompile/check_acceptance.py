#!/usr/bin/env python3
"""Local Stage 1 gate: generation integrity, native execution and file audio."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rom_info import NTSC_U_SHA1 as ROM_SHA1
from inspect_capture import find_task, inspect, iter_events, reconstruct
from run_recompiler import inspect_output


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_stability(result: dict) -> None:
    report = result["report"]
    require(report is not None and report["clean_shutdown"], "Native run did not join normally")
    require(report["rom_sha1"] == ROM_SHA1, "Native profile differs")
    require(600 <= report["elapsed_seconds"] < 605, "A real 600-second run is required")
    require(35900 <= report["fields"] <= 36100, "Nominal 60-field cadence differs")
    require(result["completed_sequence_valid"] and report["tasks"] == report["completed_tasks"], "Graphics task sequence incomplete")
    require(report["tasks"] > 1000 and report["audio_samples"] > 600 * 11025 * 2 * 0.85, "Task/audio output insufficient")
    require(any(w["rate"] == 11025 and w["nonzero_bytes"] > 0 for w in result["audio"]), "Nonzero native PCM missing")
    require(result["event_counts"].get("runtime_error", 0) == 0, "Native runtime reported errors")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--stability", type=Path, required=True)
    parser.add_argument("--reference-comparison", type=Path, required=True)
    parser.add_argument("--load-reference-comparison", type=Path, required=True)
    parser.add_argument("--title-capture", type=Path, required=True)
    parser.add_argument("--title-task", type=int, required=True)
    parser.add_argument("--save-capture", type=Path, required=True)
    parser.add_argument("--load-capture", type=Path, required=True)
    parser.add_argument("--save", type=Path, required=True)
    parser.add_argument("--save-before-reload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Report output must be new")
    root = Path(__file__).resolve().parents[2]
    require(hashlib.sha1(args.rom.read_bytes()).hexdigest() == ROM_SHA1, "Supplied canonical ROM differs")
    generation = json.loads(args.generation.read_text())
    generated = root / "local/generated/game"
    actual = inspect_output(generated, (args.generation.parent / "recompiler.log").read_text())
    require(actual["files"] == generation["files"], "Generated artifacts differ from successful generation")
    config = args.generation.parent.parent / "sc64.toml"
    require(hashlib.sha256(config.read_bytes()).hexdigest() == generation["config_sha256"], "Recompiler config changed")
    require(re.search(r"(?m)^stubs\s*=\s*\[\s*\]", config.read_text()) is not None, "Unexpected guest stubs")
    runtime = root / "local/deps/N64ModernRuntime"
    patch = json.loads((runtime / "sc64-host-patch.json").read_text())
    for name, digest in patch["patched_sha256"].items():
        require(hashlib.sha256((runtime / name).read_bytes()).hexdigest() == digest, "Prepared runtime changed: " + name)
    stability = inspect(args.stability, stride=600)
    check_stability(stability)
    telemetry = []
    for event in iter_events(args.stability):
        if event["kind"] == "telemetry" and event["field"] >= 2100:
            telemetry.append(event)
    require(len(telemetry) >= 50, "Continuing native telemetry missing")
    for before, after in zip(telemetry, telemetry[1:]):
        require(after["completed_tasks"] > before["completed_tasks"] and after["audio_samples"] > before["audio_samples"], "Game/audio stalled during stability window")
        require(after["submitted_tasks"] - after["completed_tasks"] <= 2, "Graphics queue grows")
    require(max(t["audio_peak_queue_bytes"] for t in telemetry) <= 11025 * 4, "Audio queue bound exceeded")
    comparison = json.loads(args.reference_comparison.read_text())
    scenes = {m["reference_snapshot"].split("-task-")[0] for m in comparison["matches"] if len(m["matching_image_indices"]) >= 3}
    require({"main-menu", "mission-list"} <= scenes, "Native interactive menus lack original-image/census evidence")
    title = find_task(args.title_capture, args.title_task)
    require(title is not None, "Reviewed CPU title snapshot missing")
    title_ram = reconstruct(args.title_capture, title, set())
    title_sha256 = hashlib.sha256(title_ram[0x1767c0:0x1767c0 + 640 * 480 * 2]).hexdigest()
    require(title_sha256 == "17c9183a7b29afd0f2a37116449096f0bfe4ac71e3a49a35ef00819eb522843d", "CPU title buffer differs from reviewed native title")
    saved = inspect(args.save_capture, stride=600)
    loaded = inspect(args.load_capture, stride=600)
    for result in [saved, loaded]:
        require(result["complete"] and result["report"]["clean_shutdown"] and result["completed_sequence_valid"], "Save/load run incomplete")
    require(saved["event_counts"].get("flash_dma_write", 0) > 4, "Only initial Flash formatting was recorded")
    require(loaded["event_counts"].get("flash_dma_read", 0) > 0, "Cold game did not read Flash")
    require(any(len(mode) == 12 and mode[1] == 320 for mode in loaded["vi_mode_registers"]), "Cold reload did not reach a 320-pixel game mode")
    load_comparison = json.loads(args.load_reference_comparison.read_text())
    require(any(m["reference_snapshot"].startswith("loaded-map-task-") and
                m["native_field"] > 2500 and len(m["matching_image_indices"]) >= 3
                for m in load_comparison["matches"]), "Cold map lacks original loaded-map census/image evidence")
    battery = args.save.read_bytes()
    before = json.loads(args.save_before_reload.read_text())
    require(len(battery) == 131072 and hashlib.sha256(battery).hexdigest() == before["sha256"], "Battery save changed across cold load")
    result = dict(schema="sc64-stage1-acceptance-v1", passed=True, rom_sha1=ROM_SHA1,
        generated_files=len(actual["files"]), generated_c_files=actual["function_source_files"],
        native_stability=stability["report"], telemetry_samples=len(telemetry),
        max_resident_bytes=max(t.get("max_resident_bytes", 0) for t in telemetry),
        native_scenes=sorted(scenes), flash_sha256=before["sha256"],
        cpu_title_sha256=title_sha256,
        save_writes=saved["event_counts"]["flash_dma_write"], cold_load=loaded["report"],
        limitation="File PCM output and native menu/save workload on macOS arm64. SDL dummy long-run output, rendered pixels, complete campaign, other desktop platforms and Android remain uncertified.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
