#!/usr/bin/env python3
"""Preview CPU-written RGBA16 RAM bytes; does not execute RDP or VI filtering."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or
import struct
import zlib
from inspect_capture import find_task, reconstruct

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from preview_cpu_surface import chunk


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    integer = lambda value: int(value, 0)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--task", type=int, required=True)
    parser.add_argument("--address", type=integer, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require_local_or(parser.error, args.output, new=True, root=Path(__file__).resolve().parents[2], what="Output")
    if not (0 < args.width <= 2048 and 0 < args.height <= 2048):
        parser.error("Invalid dimensions")
    event = find_task(args.capture, args.task)
    if event is None:
        parser.error("Task not found")
    ram = reconstruct(args.capture, event, set())
    size = args.width * args.height * 2
    if not 0 <= args.address <= len(ram) - size:
        parser.error("Surface exceeds RDRAM")
    source = ram[args.address:args.address + size]
    raw = bytearray()
    for y in range(args.height):
        raw.append(0)
        for x in range(args.width):
            value = struct.unpack_from(">H", source, (y * args.width + x) * 2)[0]
            raw.extend(((value >> 11 & 31) * 255 // 31,
                        (value >> 6 & 31) * 255 // 31, (value >> 1 & 31) * 255 // 31))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", args.width, args.height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(png)
    print(json.dumps(dict(task=args.task, field=event["field"], address=args.address,
                         source_sha256=hashlib.sha256(source).hexdigest(),
                         limitation="CPU buffer only; RDP effects and VI filtering excluded")))


if __name__ == "__main__":
    main()
