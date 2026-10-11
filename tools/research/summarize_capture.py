#!/usr/bin/env python3
"""Summarize local Stage 0 traces; never treat an incomplete trace as a pass."""
import argparse
from collections import Counter
import hashlib
import json
import statistics
import struct
from collections.abc import Iterator
from pathlib import Path

RDP_NAMES = {
    0x00: 'NOOP', 0x24: 'TEXRECT', 0x25: 'TEXRECTFLIP', 0x26: 'LOADSYNC',
    0x27: 'PIPESYNC', 0x28: 'TILESYNC', 0x29: 'FULLSYNC', 0x2A: 'SETKEYGB',
    0x2B: 'SETKEYR', 0x2C: 'SETCONVERT', 0x2D: 'SETSCISSOR', 0x2E: 'SETPRIMDEPTH',
    0x2F: 'SETOTHERMODE', 0x30: 'LOADTLUT', 0x32: 'SETTILESIZE',
    0x33: 'LOADBLOCK', 0x34: 'LOADTILE', 0x35: 'SETTILE', 0x36: 'FILLRECT',
    0x37: 'SETFILLCOLOR', 0x38: 'SETFOGCOLOR', 0x39: 'SETBLENDCOLOR',
    0x3A: 'SETPRIMCOLOR', 0x3B: 'SETENVCOLOR', 0x3C: 'SETCOMBINE',
    0x3D: 'SETTIMG', 0x3E: 'SETZIMG', 0x3F: 'SETCIMG',
}
for opcode in range(8, 16):
    RDP_NAMES[opcode] = f'TRI_{opcode:02X}'
# u64 lengths, from pinned upstream Angrylion rdp.c rdp_commands[].
RDP_LENGTHS = {**dict(zip(range(8, 16), [4, 6, 12, 14, 12, 14, 20, 22])),
               0x24: 2, 0x25: 2}
GBI_NAMES = {
    0x01: 'OBJ_RECTANGLE', 0x02: 'OBJ_SPRITE', 0x04: 'SELECT_DL',
    0x05: 'OBJ_LOADTXTR', 0x06: 'OBJ_LDTX_SPRITE', 0x07: 'OBJ_LDTX_RECT',
    0x08: 'OBJ_LDTX_RECT_R', 0x09: 'BG_1CYC', 0x0A: 'BG_COPY',
    0x0B: 'OBJ_RENDERMODE', 0xDA: 'OBJ_RECTANGLE_R', 0xDB: 'MOVEWORD',
    0xDC: 'OBJ_MOVEMEM', 0xDD: 'LOAD_UCODE', 0xDE: 'DL', 0xDF: 'ENDDL',
    0xE1: 'RDPHALF_1', 0xE2: 'SETOTHERMODE_L', 0xE3: 'SETOTHERMODE_H',
    0xE4: 'TEXRECT_OR_SELECT_HALF0', 0xE5: 'TEXRECTFLIP', 0xF1: 'RDPHALF_2',
}


class RdpStream:
    """Carry a fragmented command across flushes, including all its payload."""
    def __init__(self):
        self.pending = []

    def feed(self, words):
        self.pending.extend(int(w, 16) if isinstance(w, str) else w for w in words)
        result = []
        while self.pending:
            opcode = self.pending[0] >> 56 & 63
            length = RDP_LENGTHS.get(opcode, 1)
            if len(self.pending) < length:
                break
            result.append((opcode, self.pending[:length]))
            del self.pending[:length]
        return result


def traverse_gbi(ram: bytes, root: int) -> dict:
    """Bounded S2DEX2 control-flow census, not an object renderer/disassembler."""
    histogram, segments, stack, seen, objects = Counter(), [0] * 16, [], set(), []
    pc, steps = root & 0x1FFFFFFF, 0

    def resolve(pointer):
        if pointer & 0x80000000:
            return pointer & 0x1FFFFFFF
        segment = pointer >> 24
        if segment >= 16:
            raise ValueError('invalid segmented pointer')
        return (segments[segment] + (pointer & 0xFFFFFF)) & 0x1FFFFFFF

    while steps < 100000:
        if pc + 8 > len(ram) or pc & 7:
            raise ValueError('display list outside RAM or unaligned')
        key = (pc, tuple(stack), tuple(segments))
        if key in seen:
            raise ValueError('display-list control-flow cycle')
        seen.add(key)
        high, low = struct.unpack_from('>II', ram, pc)
        opcode = high >> 24
        name = GBI_NAMES.get(opcode, RDP_NAMES.get(opcode & 63, f'UNKNOWN_{opcode:02X}'))
        histogram[name] += 1
        pc += 8
        steps += 1
        if opcode == 0xDB and (high >> 16 & 255) == 6:
            index = (high & 0xFFFF) // 4
            if index >= 16:
                raise ValueError('segment index exceeds table')
            segments[index] = low
        elif opcode == 0xDE:
            if (high >> 16 & 255) == 0:
                stack.append(pc)
                if len(stack) > 32:
                    raise ValueError('display-list nesting exceeds budget')
            pc = resolve(low)
        elif opcode == 0xDF:
            if not stack:
                return dict(commands=steps, histogram=dict(sorted(histogram.items())), objects=objects)
            pc = stack.pop()
        elif opcode in (0x04, 0xDD):
            raise ValueError('conditional list or microcode switch needs explicit decoding')
        elif opcode in (0x09, 0x0A):
            address = resolve(low)
            if address + 40 > len(ram):
                raise ValueError('background object outside RAM')
            ix, iw, fx, fw, iy, ih, fy, fh, pointer, load, fmt, size, palette, flip = struct.unpack_from('>HHhHHHhHIHBBHH', ram, address)
            row = dict(opcode=name, address=address, image=resolve(pointer),
                       image_x_10_5=ix, image_y_10_5=iy, image_width_10_2=iw,
                       image_height_10_2=ih, frame_x_10_2=fx, frame_y_10_2=fy,
                       frame_width_10_2=fw, frame_height_10_2=fh,
                       load=load, format=fmt, size=size, palette=palette, flip=flip)
            if opcode == 0x09:
                row['scale_w_5_10'], row['scale_h_5_10'] = struct.unpack_from('>HH', ram, address + 28)
            objects.append(row)
    raise ValueError('display-list instruction budget exceeded')


def iter_events(directory: Path) -> Iterator[dict]:
    """Yield a capture's events.jsonl records; the file closes when iteration ends."""
    with (directory / 'events.jsonl').open() as stream:
        for line in stream:
            yield json.loads(line)


def summarize(directory: Path, rom: bytes | None = None) -> dict:
    events = list(iter_events(directory))
    counts, stream = Counter(), RdpStream()
    colors, textures, scissors, modes, combiners, vis = set(), set(), set(), set(), set(), set()
    tasks, dl, clock_deltas, cpu, writes, execution = [], [], [], Counter(), Counter(), []
    previous = None
    for event in events:
        kind = event['event']
        if kind == 'dp':
            for opcode, words in stream.feed(event['words']):
                counts[RDP_NAMES.get(opcode, f'INVALID_{opcode:02X}')] += 1
                high, low = words[0] >> 32, words[0] & 0xFFFFFFFF
                if opcode in (0x3D, 0x3F):
                    image = (low & 0xFFFFFF, (high & 0x3FF) + 1, high >> 21 & 7, high >> 19 & 3)
                    (colors if opcode == 0x3F else textures).add(image)
                elif opcode == 0x2D:
                    scissors.add((high >> 12 & 4095, high & 4095, low >> 12 & 4095, low & 4095))
                elif opcode == 0x2F:
                    modes.add(words[0])
                elif opcode == 0x3C:
                    combiners.add(words[0])
        elif kind == 'vi':
            vis.add(tuple((k, event[k]) for k in ['origin', 'depth', 'width', 'serrate',
                                                'hstart', 'hend', 'vstart', 'vend',
                                                'xscale', 'yscale', 'v_sync', 'h_sync']))
            if previous is not None and event['clock'] > previous:
                clock_deltas.append(event['clock'] - previous)
            previous = event['clock']
        elif kind == 'sp_start':
            row = dict(field=event['field'], task=event['task'], type=event['words'][0],
                       words=event['words'])
            for key in ['ucode', 'ucode_data']:
                if key in event:
                    data = (directory / event[key]).read_bytes()
                    row[key + '_sha1'] = hashlib.sha1(data).hexdigest()
                    if rom is not None:
                        row[key + '_rom_offset'] = rom.find(data)
            tasks.append(row)
            if 'rdram' in event and row['type'] == 1:
                try:
                    parsed = traverse_gbi((directory / event['rdram']).read_bytes(), row['words'][12])
                    dl.append(dict(task=row['task'], field=row['field'], **parsed))
                except ValueError as error:
                    dl.append(dict(task=row['task'], error=str(error)))
        elif kind == 'cpu_access':
            cpu['write_bytes' if event['write'] else 'read_bytes'] += event['bytes']
        elif kind == 'rdp_write':
            writes['bytes'] += event['bytes']
        elif kind == 'execute_page':
            data = (directory / event['data']).read_bytes()
            execution.append(dict(page=event['page'], pc=event['pc'], field=event['field'],
                                  sha256=hashlib.sha256(data).hexdigest(),
                                  rom_offset=rom.find(data) if rom else None))
    return dict(schema=1, capture=str(directory), rom_sha1=hashlib.sha1(rom).hexdigest() if rom else None,
                event_counts=dict(Counter(e['event'] for e in events)), rdp_histogram=dict(sorted(counts.items())),
                rdp_incomplete_u64_words=len(stream.pending), color_images=sorted(colors),
                texture_images=sorted(textures), scissors_10_2=sorted(scissors),
                othermodes=[f'{m:016x}' for m in sorted(modes)],
                cycle_types=sorted({m >> 52 & 3 for m in modes}),
                combiners=[f'{m:016x}' for m in sorted(combiners)],
                vi_modes=[dict(v) for v in sorted(vis)],
                median_cpu_count_ticks_per_field=statistics.median(clock_deltas) if clock_deltas else None,
                sp_tasks=tasks, gbi_lists=dl, execution_pages=execution,
                window_cpu_access_bytes=dict(cpu), window_rdp_write_bytes=dict(writes),
                attribution_limit='CPU accesses are complete only during interpreter windows; JIT execution pages are block-entry samples. Address overlap requires scene analysis.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    p.add_argument('--rom', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = summarize(args.capture, args.rom.read_bytes() if args.rom else None)
    with args.output.open('x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps({k: result[k] for k in ['event_counts', 'rdp_histogram', 'rdp_incomplete_u64_words', 'cycle_types']}, indent=2))


if __name__ == '__main__':
    main()
