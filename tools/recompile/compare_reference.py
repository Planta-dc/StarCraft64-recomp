#!/usr/bin/env python3
"""Match native scene census/static CPU images to original pre-task snapshots."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from inspect_capture import iter_events, traverse_gbi


def image_hashes(ram: bytes, objects: list[dict]) -> list[str]:
    result = []
    for obj in objects:
        size = (obj["image_width_10_2"] // 4) * (obj["image_height_10_2"] // 4) * (4 << obj["size"]) // 8
        start = obj["image"]
        if start + size > len(ram):
            raise ValueError("Reference image exceeds RAM")
        result.append(hashlib.sha256(ram[start:start + size]).hexdigest())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inspection", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be new")
    native = json.loads(args.inspection.read_text())
    refs = []
    for directory in args.reference:
        for event in iter_events(directory):
            if event.get("event") != "sp_start" or "rdram" not in event:
                continue
            ram = (directory / event["rdram"]).read_bytes()
            parsed = traverse_gbi(ram, event["words"][12])
            refs.append(dict(capture=str(directory), snapshot=event["rdram"],
                             histogram=parsed["histogram"], images=image_hashes(ram, parsed["objects"])))
    matches = []
    for row in native["lists"]:
        images = [obj["image_sha256"] for obj in row["objects"]]
        candidates = []
        for reference in refs:
            if reference["histogram"] != row["histogram"]:
                continue
            equal = [i for i, pair in enumerate(zip(images, reference["images"])) if pair[0] == pair[1]]
            if equal:
                candidates.append(dict(native_task=row["task"], native_field=row["field"],
                    reference_capture=reference["capture"], reference_snapshot=reference["snapshot"],
                    object_count=len(images), matching_image_indices=equal))
        if candidates:
            matches.append(max(candidates, key=lambda c: len(c["matching_image_indices"])))
    result = dict(schema="sc64-native-reference-census-v1", inspection_sha256=hashlib.sha256(args.inspection.read_bytes()).hexdigest(),
                  matches=matches, reference_snapshots=len(refs),
                  limitation="Exact GBI census and selected ordered CPU image hashes. Animated backgrounds/positions, TLUT, RDP and rendered pixels are not certified.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(f"Matched {len(matches)} sampled native lists against {len(refs)} original snapshots")


if __name__ == "__main__":
    main()
