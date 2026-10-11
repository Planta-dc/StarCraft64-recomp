#!/usr/bin/env python3
"""Verify private native snapshots and census S2DEX2 lists, without rendering."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from summarize_capture import iter_events, traverse_gbi

UCODE_SHA1 = "7d0f686719afde0703d377ccc7a492318c01eec0"


def reconstruct(directory: Path, event: dict, verified: set[str]) -> bytes:
    if event["rdram_size"] != 0x800000 or event["page_size"] != 4096 or len(event["pages"]) != 2048:
        raise ValueError("Invalid complete RDRAM snapshot shape")
    chunks = []
    for key in event["pages"]:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Invalid page digest")
        data = (directory / "pages" / (key + ".bin")).read_bytes()
        if len(data) != 4096 or (key not in verified and hashlib.sha256(data).hexdigest() != key):
            raise ValueError("Page content differs from its digest")
        verified.add(key)
        chunks.append(data)
    ram = b"".join(chunks)
    if hashlib.sha256(ram).hexdigest() != event["rdram_sha256"]:
        raise ValueError("Complete RAM snapshot digest differs")
    return ram


def find_task(directory: Path, task: int) -> dict | None:
    """Return the first native sp_task event for ``task`` without reading the rest."""
    events = iter_events(directory)
    try:
        return next((event for event in events if event["kind"] == "sp_task" and event["task"] == task), None)
    finally:
        events.close()


def inspect(directory: Path, stride: int = 1) -> dict:
    counts, lists, modes, verified = Counter(), [], set(), set()
    tasks, completed = [], []
    submitted = 0
    last_task = None
    for event in iter_events(directory):
        counts[event["kind"]] += 1
        if event["kind"] == "sp_task":
            # Keep only selected packets. A long run contains tens of thousands
            # of 2,048-entry manifests; retaining all defeats explicit sampling.
            if submitted % stride == 0:
                tasks.append(event)
            submitted += 1
            last_task = event
        elif event["kind"] == "task_completed":
            completed.append(event["sequence"])
        elif event["kind"] == "vi":
            # Exclude origin/current; retain complete mode and scale state.
            modes.add(tuple(v for i, v in enumerate(event["registers"]) if i not in (1, 4)))
    if last_task is not None and (not tasks or tasks[-1]["task"] != last_task["task"]):
        tasks.append(last_task)
    for event in tasks:
        words = event["descriptor"]
        if len(words) != 16 or words[0] != 1 or event["ucode_sha1"] != UCODE_SHA1:
            raise ValueError("Unexpected OSTask/microcode")
        ram = reconstruct(directory, event, verified)
        ucode = words[4] & 0x1fffffff
        if hashlib.sha1(ram[ucode:ucode + words[5]]).hexdigest() != UCODE_SHA1:
            raise ValueError("Captured microcode bytes differ")
        root, size = words[12] & 0x1fffffff, words[13]
        dl = (directory / f"task-{event['task']}.dl.bin").read_bytes()
        if dl != ram[root:root + size] or hashlib.sha256(dl).hexdigest() != event["dl_sha256"]:
            raise ValueError("Submitted list differs from RAM or digest")
        parsed = traverse_gbi(ram, root)
        for obj in parsed["objects"]:
            # BG image dimensions are 10.2 fixed point; texel size is G_IM_SIZ.
            width, height = obj["image_width_10_2"] // 4, obj["image_height_10_2"] // 4
            byte_count = (width * height * (4 << obj["size"]) + 7) // 8
            start = obj["image"]
            if start + byte_count > len(ram):
                raise ValueError("Background source image exceeds RDRAM")
            obj["image_sha256"] = hashlib.sha256(ram[start:start + byte_count]).hexdigest()
        lists.append(dict(task=event["task"], field=event["field"], **parsed))
    wavs = []
    for path in sorted(directory.glob("audio*.wav")):
        with wave.open(str(path), "rb") as audio:
            payload = audio.readframes(audio.getnframes())
            wavs.append(dict(file=path.name, rate=audio.getframerate(), channels=audio.getnchannels(),
                             frames=audio.getnframes(), nonzero_bytes=sum(c != 0 for c in payload),
                             sha256=hashlib.sha256(payload).hexdigest()))
    report_path = directory / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    return dict(schema="sc64-native-inspection-v1", capture=str(directory), complete=report is not None,
                report=report, event_counts=dict(counts), submitted_tasks=submitted,
                completed_sequence_valid=completed == list(range(1, submitted + 1)),
                verified_pages=len(verified), snapshot_stride=stride, lists=lists,
                vi_mode_registers=sorted(modes), audio=wavs,
                limitation="Bounded GBI census and CPU source hashes; no RDP execution or rendered-frame parity claim.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--stride", type=int, default=1)
    args = parser.parse_args()
    if args.stride < 1 or args.output.exists():
        parser.error("Stride must be positive and output must be new")
    result = inspect(args.capture, args.stride)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(json.dumps({k: result[k] for k in ("complete", "submitted_tasks", "completed_sequence_valid", "verified_pages")}))


if __name__ == "__main__":
    main()
