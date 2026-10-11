"""Find bounded memory wait loops without confusing pointer walks with waits."""
from __future__ import annotations

import hashlib
import struct


def written_gpr(word: int) -> int | None:
    op = word >> 26
    if word == 0:
        return None
    if op == 0:
        return (word >> 11) & 31 if word & 63 in (0x21, 0x25) else None
    if op in (8, 9, 12, 13, 15, 32, 33, 35, 36, 37):
        return (word >> 16) & 31
    return None


def find_memory_waits(rom: bytes, sections: list[dict], ignored_names: set[str]) -> list[dict]:
    waits = []
    for section in sections:
        for function in section["functions"]:
            if function["name"] in ignored_names:
                continue
            start = section["rom"] + function["vram"] - section["vram"]
            end = start + function["size"]
            for offset in range(start, end - 4, 4):
                branch = struct.unpack_from(">I", rom, offset)[0]
                if branch >> 26 not in (4, 5, 20, 21):
                    continue
                immediate = branch & 0xFFFF
                signed = immediate if immediate < 0x8000 else immediate - 0x10000
                target = offset + 4 + signed * 4
                if not start <= target < offset or offset - target > 24:
                    continue
                body = [struct.unpack_from(">I", rom, item)[0] for item in range(target, offset, 4)]
                loads = [word for word in body if word >> 26 in (32, 33, 35, 36, 37)]
                if len(loads) != 1 or any(word != 0 and word >> 26 not in (32, 33, 35, 36, 37, 12)
                                         and not (word >> 26 == 0 and word & 63 in (0x21, 0x25)) for word in body):
                    continue
                base = (loads[0] >> 21) & 31
                loaded = (loads[0] >> 16) & 31
                delay = struct.unpack_from(">I", rom, offset + 4)[0]
                compared = {(branch >> 21) & 31, (branch >> 16) & 31}
                if loaded not in compared:
                    continue
                # Includes the branch delay slot: strings and linked lists
                # advance their base there and must not become scheduler polls.
                if any(written_gpr(word) == base for word in body + [delay]):
                    continue
                # A wait compares the refreshed value with a stable other
                # operand; arithmetic progression in that operand is not a wait.
                other = compared - {loaded, 0}
                if any(written_gpr(word) in other for word in body + [delay]):
                    continue
                waits.append({"func": function["name"], "section": section["name"],
                              "vram": function["vram"] + target - start, "rom": target,
                              "branch_vram": function["vram"] + offset - start,
                              "base_register": base, "load_displacement": loads[0] & 0xFFFF,
                              "body_sha256": hashlib.sha256(rom[target:offset + 8]).hexdigest(),
                              "reason": "repeated same-address memory load, stable comparison, backward branch; no local progression",
                              "debt": "D-025"})
    return waits
