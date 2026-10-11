#!/usr/bin/env python3
"""Inspect an N64 ROM without modifying it; emit metadata, never extracted code.

Python 3.10+, standard library only. All offsets in the report refer to the
normalized big-endian image unless explicitly described as input offsets.
IPL3 fingerprints identify a bootcode family, not a physical CIC measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib


MAGIC_FORMATS = {
    b"\x80\x37\x12\x40": "z64",
    b"\x37\x80\x40\x12": "v64",
    b"\x40\x12\x37\x80": "n64",
}
# CRC-32/ISO-HDLC over normalized ROM[0x40:0x1000]. Reference:
# https://github.com/z64dev/z64decompress/blob/main/src/n64crc.c
CIC_FINGERPRINTS = {
    0x6170A4A1: ("6101", "7102"),
    0x90BB6CB5: ("6102", "7101"),
    0x0B050EE0: ("6103", "7103"),
    0x98BC2C86: ("6105", "7105"),
    0xACC8580A: ("6106", "7106"),
}
# Header country names are also checked against splat's util/n64/rominfo.py.
# Only ordinary country codes get a timing hint; no measured VI rate is implied.
# Reference:
# https://github.com/mupen64plus/mupen64plus-core/blob/master/src/main/rom.c
COUNTRY_CODES = {
    0x00: ("Unknown", None),
    ord("7"): ("Beta", None),
    ord("A"): ("Asia", "NTSC"),
    ord("B"): ("Brazil", None),
    ord("C"): ("China", None),
    ord("D"): ("Germany", "PAL"),
    ord("E"): ("USA", "NTSC"),
    ord("F"): ("France", "PAL"),
    ord("G"): ("Gateway 64 NTSC", None),
    ord("H"): ("Netherlands", None),
    ord("I"): ("Italy", "PAL"),
    ord("J"): ("Japan", "NTSC"),
    ord("K"): ("Korea", None),
    ord("L"): ("Gateway 64 PAL", None),
    ord("N"): ("Canada", None),
    ord("P"): ("Europe", "PAL"),
    ord("S"): ("Spain", "PAL"),
    ord("U"): ("Australia", "PAL"),
    ord("W"): ("Scandinavia", None),
    ord("X"): ("Europe", "PAL"),
    ord("Y"): ("Europe", "PAL"),
}
IDENTIFIER_PATTERN = re.compile(
    rb"RSP[ _-]*(?:Gfx|Graphics|SW[ _-]*Version|Audio|ASP)"
    rb"|(?<![A-Za-z0-9_])(?:F3D(?:EX2?|LP|L?X)?|S2DEX2?|L3DEX2?|ZSort"
    rb"|aspMain|n_audio|MusyX|audio[ _-]*ucode)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
PRINTABLE_RUN = re.compile(rb"[\x20-\x7e]{4,}")
# SHA-1 of the normalized StarCraft 64 NTSC-U image every game tool targets.
NTSC_U_SHA1 = "a36d91b5aac7bb95df0d7de5f9814f5270e25c2b"


class RomError(ValueError):
    """Malformed or unsupported input."""


def normalize_rom(raw: bytes) -> tuple[str, bytes]:
    if len(raw) < 0x40:
        raise RomError("ROM is shorter than the 64-byte N64 header")
    fmt = MAGIC_FORMATS.get(raw[:4])
    if fmt is None:
        raise RomError(f"unrecognized magic {raw[:4].hex()}; copier headers are unsupported")
    if len(raw) % 4:
        raise RomError("ROM length must be a multiple of four; refusing truncated data")
    if fmt == "z64":
        return fmt, raw
    data = bytearray(len(raw))
    if fmt == "v64":
        data[0::2], data[1::2] = raw[1::2], raw[0::2]
    else:
        for lane in range(4):
            data[lane::4] = raw[3 - lane::4]
    return fmt, bytes(data)


def load_ntsc_u(path: Path, *, require_z64: bool = False) -> tuple[str, bytes]:
    """Read ``path``, normalize byte order and require the researched NTSC-U SHA-1.

    Returns the input format and the normalized big-endian image. Tools that hand
    the file itself to an external runner pass ``require_z64`` so a byte-swapped
    dump gets an actionable error instead of being loaded unnormalized.
    """
    fmt, data = normalize_rom(path.read_bytes())
    if hashlib.sha1(data).hexdigest() != NTSC_U_SHA1:
        raise RomError(f"normalized SHA-1 differs from the researched NTSC-U revision: {path}")
    if require_z64 and fmt != "z64":
        raise RomError(f"{path} is a {fmt} dump; this runner loads the file directly. Write a "
                       "normalized copy with tools/rom_info.py --normalized-out local/<name>.z64")
    return fmt, data


def identify_cic(data: bytes, video_hint: str | None = None) -> dict:
    if len(data) < 0x1000:
        return {"status": "unknown", "family": None, "reason": "incomplete IPL3"}
    bootcode = data[0x40:0x1000]
    crc = zlib.crc32(bootcode) & 0xFFFFFFFF
    names = CIC_FINGERPRINTS.get(crc)
    family = None
    if names:
        family = names[0] if video_hint == "NTSC" else names[1] if video_hint == "PAL" else "/".join(names)
    return {
        "status": "fingerprint_match" if names else "unknown",
        "family": family,
        "ntsc_name": names[0] if names else None,
        "pal_name": names[1] if names else None,
        "method": "CRC-32/ISO-HDLC of normalized bytes [0x40, 0x1000)",
        "ipl3_crc32": f"{crc:08x}",
        "ipl3_sha1": hashlib.sha1(bootcode).hexdigest(),
        "scope": "standard retail IPL3 families; physical chip naming uses the header timing hint",
        "physical_chip_verified": False,
    }


def find_microcode_identifiers(data: bytes, limit: int = 128) -> dict:
    if limit < 1:
        raise ValueError("identifier limit must be positive")
    identifiers = []
    total = 0
    for run in PRINTABLE_RUN.finditer(data):
        # A long printable data run can contain multiple identifiers. Keep bounded
        # context per match instead of dumping a potentially large game asset.
        printable = run.group()
        for match in IDENTIFIER_PATTERN.finditer(printable):
            total += 1
            if len(identifiers) >= limit:
                continue
            start = max(0, match.start() - 24)
            end = min(len(printable), match.end() + 96)
            offset = run.start() + match.start()
            identifiers.append({
                "offset": offset,
                "offset_hex": f"0x{offset:08x}",
                "string_offset": run.start() + start,
                "matched_token": match.group().decode("ascii"),
                "text": printable[start:end].decode("ascii"),
                "status": "candidate_string_only",
            })
    return {
        "method": "case-insensitive identifier tokens within printable ASCII runs",
        "candidates": identifiers,
        "match_count": total,
        "truncated": total > limit,
        "active_gbi": None,
        "active_audio_microcode": None,
        "limitation": "strings do not prove execution; compressed or stripped microcode may be missed",
    }


def analyze_rom(raw: bytes, identifier_limit: int = 128) -> tuple[dict, bytes]:
    fmt, data = normalize_rom(raw)
    country = data[0x3E]
    region, video = COUNTRY_CODES.get(country, ("Unknown", None))
    word = lambda offset: f"0x{struct.unpack_from('>I', data, offset)[0]:08x}"
    warnings = [
        "Header CRC1/CRC2 are reported, not recomputed or validated.",
        "Header entrypoint is a raw value, not proof of the executable ROM-to-RAM mapping.",
        "Save hardware and peripheral use cannot be inferred from this header.",
    ]
    if len(data) < 0x1000:
        warnings.append("ROM lacks a complete IPL3 region.")
    report = {
        "schema_version": 1,
        "input": {"format": fmt, "size_bytes": len(raw), "sha1": hashlib.sha1(raw).hexdigest()},
        "normalized": {
            "format": "z64", "size_bytes": len(data),
            "sha1": hashlib.sha1(data).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        "header": {
            "magic": data[:4].hex(),
            "pi_dom1_lat": data[0], "pi_dom1_pwd": data[1],
            "pi_dom1_pgs": data[2], "pi_dom1_rls": data[3],
            "clock_rate_raw": word(0x04), "entrypoint_raw": word(0x08),
            "release_raw": word(0x0C), "crc1": word(0x10), "crc2": word(0x14),
            "name": data[0x20:0x34].rstrip(b" \0").decode("ascii", "replace"),
            "name_bytes_hex": data[0x20:0x34].hex(),
            "manufacturer_raw": word(0x38),
            "cartridge_id": data[0x3C:0x3E].decode("ascii", "replace"),
            "cartridge_id_hex": data[0x3C:0x3E].hex(),
            "country_code": country,
            "country_code_hex": f"0x{country:02x}",
            "country_code_character": chr(country) if 32 <= country <= 126 else None,
            "region": region, "video_standard_hint": video,
            "revision_byte": data[0x3F],
        },
        "cic": identify_cic(data, video),
        "microcode": find_microcode_identifiers(data, identifier_limit),
        "unresolved": {
            "save_type": None, "rumble": None, "controller_pak": None,
            "code_compression": None, "overlays": None,
            "rendering_path": None, "fmv_decoder": None,
        },
        "warnings": warnings,
    }
    return report, data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="user-supplied ROM; format is detected by magic")
    parser.add_argument("--output", type=Path, help="new JSON file; otherwise print to stdout")
    parser.add_argument("--normalized-out", type=Path, help="write a new normalized z64 copy")
    parser.add_argument("--expect-sha1", help="require this SHA-1 of the normalized image")
    parser.add_argument("--max-identifiers", type=int, default=128)
    args = parser.parse_args(argv)
    try:
        if args.max_identifiers < 1:
            raise RomError("--max-identifiers must be positive")
        if args.expect_sha1 and not re.fullmatch(r"[0-9a-fA-F]{40}", args.expect_sha1):
            raise RomError("--expect-sha1 must contain exactly 40 hexadecimal digits")
        outputs = [p for p in (args.output, args.normalized_out) if p is not None]
        if len({p.resolve() for p in outputs}) != len(outputs):
            raise RomError("JSON and normalized ROM outputs must use different paths")
        for path in outputs:
            if path.resolve() == args.rom.resolve() or path.exists() or path.is_symlink():
                raise RomError(f"refusing to overwrite existing file or input: {path}")
        report, normalized = analyze_rom(args.rom.read_bytes(), args.max_identifiers)
        if args.expect_sha1 and report["normalized"]["sha1"] != args.expect_sha1.lower():
            raise RomError("normalized SHA-1 mismatch; no output written")
        payload = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
        if args.normalized_out:
            with args.normalized_out.open("xb") as file:
                file.write(normalized)
        if args.output:
            with args.output.open("x", encoding="utf-8") as file:
                file.write(payload)
        else:
            sys.stdout.write(payload)
        return 0
    except (OSError, RomError) as error:
        print(f"rom_info: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
