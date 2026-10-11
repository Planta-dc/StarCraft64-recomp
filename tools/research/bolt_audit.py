#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded BOLT metadata audit, using Heinermann's N64 codec semantics.

Codec provenance: https://github.com/heinermann/BOLTextract (GPL-3.0).
No extracted payloads are written. Labels from an optional earlier extraction
are not interpreted as format or executable-code evidence.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path


class AuditError(ValueError):
    pass


def decode(data: bytes, start: int, end: int, size: int) -> tuple[bytes, int]:
    if not 0 <= start < end <= len(data) or not 0 < size <= 64 * 1024 * 1024:
        raise AuditError('invalid compressed bounds or output size')
    out = bytearray()
    pos, operations, offset, length = start, 0, 0, 0
    while len(out) < size:
        if pos >= end:
            raise AuditError('truncated compressed opcode')
        code = data[pos]
        pos += 1
        operations += 1
        if operations > 16 or offset > size or length > size:
            raise AuditError('unbounded extension sequence')
        if code & 0x80:
            if code & 0x40:
                offset = (offset << 6) | (code & 63)
                continue
            if code & 0x20:
                length = (length << 5) | (code & 31)
                continue
            if code & 0x10:
                length = (length << 2) | (code & 3)
                offset = (offset << 2) | ((code >> 2) & 3)
                continue
            run = (length << 4 | (code & 15)) + 1
            if run > size - len(out) or run > end - pos:
                raise AuditError('literal exceeds input or output bounds')
            out.extend(data[pos:pos + run])
            pos += run
        else:
            distance = (offset << 4 | (code & 15)) + 1
            run = (length << 3 | (code >> 4)) + operations + 1
            if distance > len(out) or run > size - len(out):
                raise AuditError('backreference exceeds history or output bounds')
            for _ in range(run):
                out.append(out[-distance])
        operations = offset = length = 0
    return bytes(out), pos


def audit(rom: bytes, base: int, extracted: Path | None = None) -> dict:
    if rom[base:base + 4] != b'BOLT' or base + 16 > len(rom):
        raise AuditError('BOLT header absent or truncated')
    leaves, directories, visited = [], [], set()

    def walk(table: int, count: int, parent: str, depth: int):
        if depth > 16 or table in visited:
            raise AuditError('directory cycle or excessive nesting')
        if table < base or table + count * 16 > len(rom):
            raise AuditError('directory table exceeds ROM')
        visited.add(table)
        for index in range(count):
            entry = table + index * 16
            flags, u1, u2, kind, size, relative, key = struct.unpack_from('>4B3I', rom, entry)
            position = base + relative
            if position < base or position >= len(rom):
                raise AuditError('payload offset exceeds ROM')
            path = f'{parent}/{index:03X}'.strip('/')
            row = dict(path=path, entry_rom=entry, flags=flags, unknown_bytes=[u1, u2],
                       type_byte=kind, decoded_size=size, rom_offset=position, key=f'{key:08X}')
            if key == 0:
                directories.append(row)
                walk(position, kind or 256, path, depth + 1)
            else:
                leaves.append(row)
        visited.remove(table)

    walk(base + 16, rom[base + 11] or 256, '', 0)
    starts = sorted({r['rom_offset'] for r in leaves} | {len(rom)})
    next_start = dict(zip(starts, starts[1:]))
    manifest = {}
    if extracted:
        for row in json.loads((extracted / '_manifest.json').read_text()):
            if 'file' in row:
                manifest[(row['offset'] + base, f"{row['hash']:08X}")] = row['file']
    for row in leaves:
        start, size = row['rom_offset'], row['decoded_size']
        end = next_start[start]
        if row['flags'] & 8:
            if size > end - start:
                raise AuditError('raw payload overlaps the next payload')
            payload, consumed = rom[start:start + size], size
        else:
            payload, stop = decode(rom, start, end, size)
            consumed = stop - start
        row['stored_bytes_consumed'] = consumed
        row['sha256'] = hashlib.sha256(payload).hexdigest()
        row['first_16_hex'] = payload[:16].hex()
        if extracted:
            file = manifest.get((start, row['key']))
            if file is None or (extracted / file).read_bytes() != payload:
                raise AuditError('independent extraction comparison failed')
            row['reference_equal'] = True
    return dict(schema=1, rom_sha1=hashlib.sha1(rom).hexdigest(), bolt_rom_offset=base,
                header_last_word_uninterpreted=struct.unpack_from('>I', rom, base + 12)[0],
                directory_count=len(directories), leaf_count=len(leaves),
                decoded_bytes=sum(r['decoded_size'] for r in leaves),
                directories=directories, leaves=leaves)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('--base', type=lambda x: int(x, 0), default=0x12CA10)
    p.add_argument('--compare-extracted', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    try:
        result = audit(args.rom.read_bytes(), args.base, args.compare_extracted)
        with args.output.open('x') as out:
            json.dump(result, out, indent=2)
            out.write('\n')
    except (AuditError, OSError) as error:
        p.error(str(error))
    print(f"Audited {result['leaf_count']} leaves, {result['decoded_bytes']} decoded bytes")


if __name__ == '__main__':
    main()
