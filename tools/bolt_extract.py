#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""BOLT archive extractor for StarCraft 64 (Mass Media's engine).

Python port of heinermann/BOLTextract (GPL-3.0) logic:
  - archive header + entry layout per BOLT/bolt-extract/bolt.h
  - N64 LZSS decompression per BOLT/bolt-extract/n64.cpp
  - file type detection per BOLT/bolt-extract/guess_type.cpp

Usage: python3 tools/bolt_extract.py "StarCraft 64 (USA).z64" [local/extracted/sc64-usa]

The ROM is byte-order normalized and must match the researched NTSC-U SHA-1.
Extracted assets are game-derived: the output must be a new directory under the
ignored local/ tree.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from private_paths import ROOT, PrivatePathError, require_local
from rom_info import RomError, load_ntsc_u

DEFAULT_OUTPUT = ROOT / "local/extracted/sc64-usa"

FLAG_UNCOMPRESSED = 0x08

log = logging.getLogger("bolt_extract")


class BoltError(Exception):
    pass


def decompress_n64(rom, start, expected_size):
    """N64/GBA LZSS variant (guessed by heinermann, verified on real ROMs)."""
    result = bytearray()
    pos = start
    op_count = 0
    ext_offset = 0
    ext_run = 0
    while len(result) < expected_size:
        b = rom[pos]
        pos += 1
        op_count += 1
        if b & 0x80:
            if b & 0x40:      # extension in offset
                ext_offset = (ext_offset << 6) | (b & 0x3F)
            elif b & 0x20:    # extension in run length
                ext_run = (ext_run << 5) | (b & 0x1F)
            elif b & 0x10:    # extension in both
                ext_run = (ext_run << 2) | (b & 0x03)
                ext_offset = (ext_offset << 2) | ((b & 0x0C) >> 2)
            else:             # literal run
                run = ((ext_run << 4) | (b & 0x0F)) + 1
                result += rom[pos:pos + run]
                pos += run
                op_count = ext_offset = ext_run = 0
        else:                 # back-reference lookup
            if not result:
                raise BoltError("lookup on first byte at %#x" % pos)
            rel_offset = ((ext_offset << 4) | (b & 0x0F)) + 1
            run_length = ((ext_run << 3) | (b >> 4)) + op_count + 1
            if len(result) < rel_offset:
                raise BoltError("lookbehind too far at %#x" % pos)
            src = len(result) - rel_offset
            for i in range(run_length):
                result.append(result[src + i])
            op_count = ext_offset = ext_run = 0
    if len(result) != expected_size:
        raise BoltError("size mismatch: got %d, expected %d" % (len(result), expected_size))
    return bytes(result)


# ---- file type detection (port of guess_type.cpp, big-endian where noted) ----

def u16be(d, o):
    return struct.unpack_from(">H", d, o)[0]


def u32be(d, o):
    return struct.unpack_from(">I", d, o)[0]


def u16le(d, o):
    return struct.unpack_from("<H", d, o)[0]


def u32le(d, o):
    return struct.unpack_from("<I", d, o)[0]


def has_magic(d, s):
    return len(d) > 32 and d[:4] == s


def is_wav(d):
    return has_magic(d, b"RIFF")


def is_txt(d):
    return all(32 <= c <= 126 or c in (9, 10, 13) for c in d) if d else False


def is_img(d):
    # img_header_t: u16 type, u16 bpp(=8), u32 zero, u16 w, u16 h, u32 zero (BE)
    # 16-byte header, then 8bpp palette indices
    if len(d) <= 16:
        return False
    w, h = u16be(d, 8), u16be(d, 10)
    return (len(d) == w * h + 16
            and d[1] == 0 and d[0] < 5
            and u16be(d, 2) == 8
            and u32be(d, 4) == 0
            and u32be(d, 12) == 0)


def is_video(d):
    # Mass Media "video"/slideshow stream: magic 0x02102b11, u32 size, u32 zero
    return (len(d) > 32 and u32be(d, 0) == 0x02102B11
            and u32be(d, 4) == len(d) - 12 and u32be(d, 8) == 0)


def is_pal(d):
    # u32 zero, u16 entries==255 (BE), then 255*2 bytes => 518 total
    return (len(d) == 518 and u32be(d, 0) == 0 and u16be(d, 4) == 255)


def is_fnt(d):
    return has_magic(d, b"FONT")


def is_chk(d):
    return (has_magic(d, b"TYPE") or has_magic(d, b"VER ")
            or has_magic(d, b"IVER") or has_magic(d, b"IVE2")
            or has_magic(d, b"VCOD"))


def is_tbl(d):
    # TBL strings are little-endian
    if len(d) <= 4:
        return False
    n = u16le(d, 0)
    if n <= 1:
        return False
    data_start = n * 2 + 2
    if data_start >= len(d):
        return False
    if u16le(d, 2) != data_start:
        return False
    for i in range(n):
        off = u16le(d, 2 + i * 2)
        if off < data_start or off >= len(d):
            return False
        if i > 0 and d[off - 1] != 0:
            return False
        if i > 0 and off <= u16le(d, 2 + (i - 1) * 2):
            return False
    return d[-1] == 0


def is_grp(d):
    # PC StarCraft GRP: 6-byte LE header (frames, width, height), then one
    # 8-byte LE frame record (x, y, w, h, u32 data offset) per frame.
    if len(d) <= 16:
        return False
    frames = u16le(d, 0)
    w, h = u16le(d, 2), u16le(d, 4)
    if not frames or not w or not h:
        return False
    data_start = 6 + frames * 8
    if data_start + 1 >= len(d):
        return False
    if u32le(d, 6 + 4) != data_start:
        return False
    for i in range(frames):
        fx, fy, fw, fh = d[6 + i * 8:10 + i * 8]
        if not fw or not fh:
            return False
        if fx + fw > w or fy + fh > h:
            return False
        off = u32le(d, 6 + i * 8 + 4)
        if off < data_start or off >= len(d):
            return False
    return True


def is_audio(d):
    # u8 channels, u8 bits, u16 rate BE, u32 size BE, u32 size2 BE
    if len(d) <= 12:
        return False
    channels, bits = d[0], d[1]
    if channels > 2:
        return False
    if bits not in (4, 8, 16, 24, 32):
        return False
    size = u32be(d, 4)
    size2 = u32be(d, 8)
    if size != 0 and size2 != 0:
        return False
    if size2 != 0:
        size = size2
    rate = u16be(d, 2)
    if size + 12 != len(d):
        return False
    if not (8000 <= rate <= 44100):
        return False
    return True


def is_vag(d):
    return has_magic(d, b"VAGp")


def is_elf(d):
    return has_magic(d, b"\x7fELF")


def guess_type(d):
    if not d:
        return "unk"
    if is_wav(d):
        return "wav"
    if is_fnt(d):
        return "fnt"
    if is_chk(d):
        return "chk"
    if is_img(d):
        return "unkimg"
    if is_pal(d):
        return "unkpal"
    if is_audio(d):
        return "unkpcm"
    if is_tbl(d):
        return "tbl"
    if is_grp(d):
        return "grp"
    if is_txt(d):
        return "txt"
    if is_vag(d):
        return "vag"
    if is_elf(d):
        return "elf"
    return "unk"


class Entry:
    __slots__ = ("flags", "unk1", "unk2", "file_type", "size", "offset", "hash")

    def __init__(self, rom, base):
        self.flags = rom[base]
        self.unk1 = rom[base + 1]
        self.unk2 = rom[base + 2]
        self.file_type = rom[base + 3]
        self.size = u32be(rom, base + 4)
        self.offset = u32be(rom, base + 8)
        self.hash = u32be(rom, base + 12)

    @property
    def is_dir(self):
        return self.hash == 0


def extract(rom, bolt_begin, entries_base, count, out_dir, rel_path, manifest, stats):
    for i in range(count):
        e = Entry(rom, entries_base + i * 16)
        if e.is_dir:
            n = e.file_type
            if n == 0:
                n = 256
            sub = rel_path + [("%03X" % i)]
            manifest.append({"dir": "/".join(sub), "index": i, "file_type": e.file_type,
                             "size": e.size, "offset": e.offset, "hash": e.hash})
            extract(rom, bolt_begin, bolt_begin + e.offset, n, out_dir, sub, manifest, stats)
        else:
            if e.flags & FLAG_UNCOMPRESSED:
                data = rom[bolt_begin + e.offset:bolt_begin + e.offset + e.size]
            else:
                try:
                    data = decompress_n64(rom, bolt_begin + e.offset, e.size)
                except BoltError as ex:
                    log.warning("decompress failed %s/%08X: %s", "/".join(rel_path), e.hash, ex)
                    data = b""
            ext = guess_type(data)
            name = "%08X.%s" % (e.hash, ext)
            d = os.path.join(out_dir, *rel_path)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "wb") as f:
                f.write(data)
            stats[ext] = stats.get(ext, 0) + 1
            stats["bytes_" + ext] = stats.get("bytes_" + ext, 0) + len(data)
            manifest.append({"file": "/".join(rel_path + [name]), "index": i,
                             "file_type": e.file_type, "flags": e.flags,
                             "size": e.size, "offset": e.offset, "hash": e.hash})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom", type=Path, help="your StarCraft 64 NTSC-U dump (z64/v64/n64)")
    parser.add_argument("output", type=Path, nargs="?", default=DEFAULT_OUTPUT,
                        help="new directory under local/ (default: local/extracted/sc64-usa)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        out_path = require_local(args.output, new=True, root=ROOT, what="Extracted asset output")
        _, rom = load_ntsc_u(args.rom)
    except (OSError, PrivatePathError, RomError) as error:
        print("bolt_extract: %s" % error, file=sys.stderr)
        return 2
    rom_path, out_dir = str(args.rom), str(out_path)
    bolt_begin = rom.find(b"BOLT")
    if bolt_begin < 0:
        bolt_begin = rom.find(b"bolt")
    if bolt_begin < 0:
        print("BOLT archive not found")
        return 1
    num_entries = rom[bolt_begin + 11]
    end_offset = u32be(rom, bolt_begin + 12)
    print("ROM: %s (%d bytes)" % (rom_path, len(rom)))
    print("BOLT archive at file offset %#x, end_offset=%#x, top-level entries=%d"
          % (bolt_begin, end_offset, num_entries or 256))
    print("Build date: %04d-%02d-%02d %02d:%02d:%02d.%02d"
          % (rom[bolt_begin + 10] + 1900, rom[bolt_begin + 8], rom[bolt_begin + 9],
             rom[bolt_begin + 4], rom[bolt_begin + 5], rom[bolt_begin + 6], rom[bolt_begin + 7]))
    os.makedirs(out_dir, exist_ok=True)
    manifest, stats = [], {}
    extract(rom, bolt_begin, bolt_begin + 16, num_entries or 256, out_dir, [], manifest, stats)
    with open(os.path.join(out_dir, "_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    total = sum(v for k, v in stats.items() if k.startswith("bytes_"))
    print("\n== Extraction summary ==")
    for ext in sorted(k for k in stats if not k.startswith("bytes_")):
        print("  %-8s %5d files, %10d bytes" % (ext, stats[ext], stats.get("bytes_" + ext, 0)))
    print("  TOTAL    %5d files, %10d bytes (%.1f MiB uncompressed)"
          % (sum(v for k, v in stats.items() if not k.startswith("bytes_")), total, total / 1048576))
    print("\nManifest: %s" % os.path.join(out_dir, "_manifest.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
