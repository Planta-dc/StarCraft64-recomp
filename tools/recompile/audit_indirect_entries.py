#!/usr/bin/env python3
"""Report unclassified code pointers and statically materialized thread entries.

Candidates are evidence for targeted investigation, never automatic symbols.
The bounded linear register propagation is conservative at branches/calls;
unknown values do not become guessed callback addresses.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path


def propagate(registers: dict[int, int], word: int) -> None:
    op, rs, rt, rd = word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    immediate = word & 0xFFFF
    value = None
    destination = rt
    if op == 15:
        value = immediate << 16
    elif op in (8, 9) and rs in registers:
        value = (registers[rs] + (immediate if immediate < 0x8000 else immediate - 0x10000)) & 0xFFFFFFFF
    elif op == 13 and rs in registers:
        value = registers[rs] | immediate
    elif op == 0:
        destination = rd
        function = word & 63
        if function in (0x21, 0x25) and rs in registers and rt in registers:
            value = (registers[rs] + registers[rt]) & 0xFFFFFFFF if function == 0x21 else registers[rs] | registers[rt]
        elif function in (8, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x1A, 0x1B):
            return
    elif op in (1, 2, 3, 4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17) or 0x28 <= op <= 0x2F:
        return
    if destination:
        registers.pop(destination, None)
        if value is not None:
            registers[destination] = value
    registers[0] = 0


def audit(rom: bytes, manifest: dict, directory: Path) -> dict:
    sections = manifest["sections"]
    known = {section["name"]: set() for section in sections}
    for section in sections:
        for csv_file in section["function_csvs"]:
            with (directory / csv_file).open(newline="") as source:
                known[section["name"]].update(int(row["address"], 0) for row in csv.DictReader(source))
    references: dict[tuple[str, int], list[dict]] = {}
    threads = []

    def add_reference(value: int, origin: dict) -> None:
        for target in sections:
            offset = target["rom"] + value - target["vram"]
            if value & 3 == 0 and any(start <= offset < end for start, end in target["code"]):
                references.setdefault((target["name"], value), []).append(origin)

    for section in sections:
        for offset in range(section["rom"], section["rom"] + section["size"], 4):
            add_reference(struct.unpack_from(">I", rom, offset)[0],
                          {"section": section["name"], "rom": offset, "kind": "word candidate"})
        for start, end in section["code"]:
            registers = {0: 0}
            offset = start
            while offset < end:
                word = struct.unpack_from(">I", rom, offset)[0]
                pc = section["vram"] + offset - section["rom"]
                op = word >> 26
                if op == 3 and offset + 8 <= end:
                    target = ((pc + 4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2)
                    propagate(registers, struct.unpack_from(">I", rom, offset + 4)[0])
                    if target == 0x800908D0:
                        threads.append({"caller_section": section["name"], "call_vram": pc,
                                        "call_rom": offset, "entry_vram": registers.get(6),
                                        "evidence": "bounded linear constant propagation into a2 at osCreateThread"})
                    registers = {0: 0}
                    offset += 8
                    continue
                propagate(registers, word)
                # Completed address pairs/constant copies count as candidates.
                if op in (8, 9, 13) or (op == 0 and word & 63 in (0x21, 0x25)):
                    destination = (word >> 11) & 31 if op == 0 else (word >> 16) & 31
                    if destination in registers:
                        add_reference(registers[destination], {"section": section["name"], "rom": offset,
                                                              "kind": "materialized address candidate"})
                if op in (1, 2, 4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17) or (op == 0 and word & 63 in (8, 9)):
                    # The delay slot may contain a pointer; then reset because
                    # no branch-path proof is available to this static audit.
                    if offset + 8 <= end:
                        propagate(registers, struct.unpack_from(">I", rom, offset + 4)[0])
                        offset += 4
                    registers = {0: 0}
                offset += 4
    missing = []
    for (name, address), origins in sorted(references.items()):
        if address in known[name]:
            continue
        section = next(item for item in sections if item["name"] == name)
        offset = section["rom"] + address - section["vram"]
        word = struct.unpack_from(">I", rom, offset)[0]
        missing.append({"section": name, "vram": address, "rom": offset,
                        "stack_frame_prologue": word >> 16 == 0x27BD and bool(word & 0x8000),
                        "references": origins, "status": "CANDIDATE; not an adopted function"})
    return {"rom_sha1": hashlib.sha1(rom).hexdigest(), "missing_entry_candidates": missing,
            "thread_call_sites": threads, "limitations": ["No interprocedural or full control-flow propagation",
                "Interior branch/jump-table targets also occur as pointer candidates",
                "A candidate is not proof of a separate function or runtime reachability"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if not args.output.resolve().is_relative_to(root / "local"):
        raise SystemExit("Private audit output must remain under ignored local/")
    rom = args.rom.read_bytes()
    manifest = json.loads(args.manifest.read_text())
    if hashlib.sha1(rom).hexdigest() != manifest["rom_sha1"]:
        raise SystemExit("ROM differs from symbol manifest")
    result = audit(rom, manifest, args.manifest.parent)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(f"{len(result['missing_entry_candidates'])} pointer candidates; {len(result['thread_call_sites'])} thread call sites")


if __name__ == "__main__":
    main()
