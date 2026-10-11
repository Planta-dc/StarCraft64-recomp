#!/usr/bin/env python3
"""Extract paired pre-task RAM / original RSP-emitted RDP inputs privately."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research'))
from summarize_capture import RdpStream, iter_events

# Tasks are recorded original execution, not hand-authored display lists.
CASES = {'reference-cold': [162, 163, 326, 327], 'mission-01': [1, 108],
         'mission-02': [294, 295], 'cold-saved-mission-02': [953, 954],
         'reference-2p-fields': [1, 2, 3, 4]}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract(directory: Path, ids: list[int]) -> list[dict]:
    selected, active = [], None
    def finish():
        if active is None:
            return
        parser = RdpStream()
        decoded = parser.feed(active['words'])
        if parser.pending or sum(op == 0x29 for op, _ in decoded) != 1:
            raise ValueError('Task has no unique complete FULLSYNC')
        colors = [packet[0] for op, packet in decoded if op == 0x3f]
        if len(colors) != 1:
            raise ValueError('Corpus task must have exactly one color target')
        word = colors[0]
        active['target'] = dict(address=word & 0xffffff, width=((word >> 32) & 1023)+1,
                                format=(word >> 53) & 7, size=(word >> 51) & 3)
        width = active['target']['width']
        active['target']['height'] = {320: 240, 512: 384, 640: 480}[width]
        selected.append(active.copy())
    for event in iter_events(directory):
        if event['event'] == 'sp_start':
            finish()
            active = None
            if event['task'] in ids:
                if 'rdram' not in event:
                    raise ValueError('Selected task has no pre-task RAM')
                active = dict(task=event['task'], field=event['field'],
                              source_ram=str((directory / event['rdram']).resolve()),
                              root=event['words'][12] & 0x1fffffff, words=[],
                              ucode=str((directory / event['ucode']).resolve()))
        elif event['event'] == 'stage2_post_task' and active is not None:
            if event['task'] != active['task'] or event['fence'] != 'Angrylion SyncFull after worker join':
                raise ValueError('Post-task fence identity differs')
            active['source_post'] = str((directory/event['rdram']).resolve())
        elif event['event'] == 'dp' and active is not None:
            active['words'].extend(event['words'])
    finish()
    if sorted(row['task'] for row in selected) != sorted(ids):
        raise ValueError('Missing selected tasks')
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--captures', type=Path, default=Path('local/captures/research'))
    parser.add_argument('--fenced-captures', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if not output.is_relative_to(root / 'local') or output.exists():
        parser.error('Use a new ignored local/ output directory')
    prepared = []
    cases = CASES
    capture_root = args.captures
    if args.fenced_captures:
        capture_root = args.fenced_captures
        cases = {}
        for scene in ('main-menu-02', 'menu-01', 'briefing-01', 'one-player-02', 'reference-2p-01'):
            ids = []
            for event in iter_events(capture_root/scene):
                if event['event'] == 'sp_start' and 'rdram' in event:
                    ids.append(event['task'])
            if len(ids) < 3:
                raise ValueError('Each accepted scene requires at least three recorded tasks')
            cases[scene] = ids
    for scene, ids in cases.items():
        for row in extract(capture_root / scene, ids):
            ram = Path(row['source_ram']).read_bytes()
            if len(ram) != 0x800000:
                raise ValueError('RAM must be canonical 8 MiB')
            ucode = Path(row.pop('ucode')).read_bytes()
            if hashlib.sha1(ucode).hexdigest() != '7d0f686719afde0703d377ccc7a492318c01eec0':
                raise ValueError('Unexpected graphics microcode')
            row['id'] = f'{scene}-{row["task"]}'
            if args.fenced_captures:
                if 'source_post' not in row:
                    raise ValueError('Missing exact fenced post-task RAM')
                post = Path(row['source_post']).read_bytes()
                if len(post) != 0x800000:
                    raise ValueError('Invalid original post-task size')
                row['post_sha256'] = digest(post)
            row['rdp_data'] = b''.join(struct.pack('>Q', int(w, 16)) for w in row.pop('words'))
            row['rdp_sha256'] = digest(row['rdp_data'])
            row['ram_sha256'] = digest(ram)
            prepared.append(row)
    output.mkdir(parents=True)
    for row in prepared:
        path = output / (row['id'] + '.rdp.bin')
        path.write_bytes(row.pop('rdp_data'))
        row['rdp'] = str(path)
    manifest = dict(schema=1, threshold_rgb_psnr_db=40.0,
                    domain='Native RGBA16 target RGB before VI; independent recorded-RDP replay',
                    original_post_task_ground_truth=bool(args.fenced_captures), cases=prepared)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Prepared {len(prepared)} paired tasks in {output}')


if __name__ == '__main__':
    main()
