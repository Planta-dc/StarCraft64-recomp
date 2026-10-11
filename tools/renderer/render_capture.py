#!/usr/bin/env python3
"""Render one verified native Stage1 pre-task capture privately through gfx_core."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'recompile'))
from inspect_capture import find_task, reconstruct, UCODE_SHA1
from compare import pixels


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    p.add_argument('task', type=int)
    p.add_argument('output', type=Path)
    p.add_argument('--renderer', type=Path, default=Path('local/build/renderer/native/gfx_core/sc64_gfx_replay'))
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if not output.is_relative_to(root/'local') or output.exists():
        p.error('Use a new ignored local/ output directory')
    event = find_task(args.capture, args.task)
    if event is None or event['ucode_sha1'] != UCODE_SHA1:
        raise ValueError('Missing task or unexpected microcode')
    ram = reconstruct(args.capture, event, set())
    words = event['descriptor']
    if words[0] != 1 or hashlib.sha1(ram[words[4]&0x1fffffff:(words[4]&0x1fffffff)+words[5]]).hexdigest() != UCODE_SHA1:
        raise ValueError('Invalid graphics task descriptor')
    address, size = words[12]&0x1fffffff, words[13]
    data = (args.capture/f'task-{args.task}.dl.bin').read_bytes()
    if data != ram[address:address+size] or hashlib.sha256(data).hexdigest() != event['dl_sha256']:
        raise ValueError('Captured root list differs')
    output.mkdir(parents=True)
    source = output/'source.rdram.bin'
    source.write_bytes(ram)
    subprocess.run([str(args.renderer), 'gbi', str(source), str(address), str(output/'replay')], check=True)
    report = json.loads((output/'replay/report.json').read_text())
    rendered = (output/'replay/rendered.ram').read_bytes()
    for index, target in enumerate(report['targets']):
        target['height'] = {320:240, 512:384, 640:480}[target['width']]
        Image.frombytes('RGB', (target['width'], target['height']), pixels(rendered, target)).save(output/f'target-{index}.png')
    report.update(task=args.task, field=event['field'], source_ram_sha256=event['rdram_sha256'],
                  limitation='Native pre-task HLE output; no paired original execution or VI scanout claim.')
    (output/'native-render.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
