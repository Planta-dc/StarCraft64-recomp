#!/usr/bin/env python3
"""Run independent native-target regressions; never equate oracle replay with live original proof."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or
import re
import subprocess
from PIL import Image, ImageChops


def case_paths(output: Path, case_id: str) -> tuple[Path, Path]:
    # IDs are filenames, never paths. The oracle runs before the guarded HLE
    # executable, so it must receive an independently checked destination.
    if not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', case_id):
        raise ValueError('Case ID must be a simple ASCII filename')
    root = output.resolve()
    case = (root / case_id).resolve()
    oracle = (root / (case_id + '.oracle.ram')).resolve()
    if not case.is_relative_to(root) or not oracle.is_relative_to(root):
        raise ValueError('Case output escapes its private directory')
    return case, oracle


def pixels(data: bytes, target: dict) -> bytes:
    width, height, start = target['width'], target['height'], target['address']
    if target['format'] != 0 or target['size'] != 2 or start+width*height*2 > len(data):
        raise ValueError('Invalid RGBA16 target')
    output = bytearray()
    for offset in range(start, start+width*height*2, 2):
        v = int.from_bytes(data[offset:offset+2], 'big')
        for c in (v >> 11, (v >> 6) & 31, (v >> 1) & 31):
            output.append((c << 3) | (c >> 2))
    return bytes(output)


def metric(actual: bytes, expected: bytes) -> dict:
    if len(actual) != len(expected) or not actual:
        raise ValueError('Pixel length mismatch')
    squared = sum((a-b)**2 for a, b in zip(actual, expected))
    mse = squared / len(actual)
    return dict(psnr_db=None if mse == 0 else 10*math.log10(255**2/mse), exact=mse == 0,
                mse=mse, max_error=max(abs(a-b) for a, b in zip(actual, expected)),
                different_channels=sum(a != b for a, b in zip(actual, expected)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--build', type=Path, default=Path('local/build/renderer/native/gfx_core'))
    p.add_argument('--mode', choices=('gbi', 'rdp'), default='gbi')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = require_local_or(p.error, args.output, new=True, root=root, what='Output')
    manifest = json.loads(args.manifest.read_text())
    if manifest['schema'] != 1 or manifest['threshold_rgb_psnr_db'] != 40:
        raise ValueError('Unrecognized schema or changed frozen threshold')
    ids = [row['id'] for row in manifest['cases']]
    for case_id in ids:
        case_paths(output, case_id)
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate case ID')
    output.mkdir(parents=True)
    results = []
    for row in manifest['cases']:
        result = dict(id=row['id'], passed=False)
        try:
            for field, path in [('ram_sha256', row['source_ram']), ('rdp_sha256', row['rdp'])]:
                if hashlib.sha256(Path(path).read_bytes()).hexdigest() != row[field]:
                    raise ValueError('Input digest mismatch')
            case, oracle = case_paths(output, row['id'])
            command = [str(args.build/'sc64_rdp_oracle'), row['source_ram'], row['rdp'], str(oracle)]
            subprocess.run(command, check=True, capture_output=True)
            if manifest['original_post_task_ground_truth']:
                post = Path(row['source_post']).read_bytes()
                if hashlib.sha256(post).hexdigest() != row['post_sha256']:
                    raise ValueError('Original post-task digest differs')
                expected_ram = post
                result['ground_truth'] = 'Fenced original-execution post-task framebuffer'
            else:
                expected_ram = oracle.read_bytes()
                result['ground_truth'] = 'Controlled recorded-RDP oracle replay'
            command = [str(args.build/'sc64_gfx_replay'), args.mode, row['source_ram'],
                       str(row['root']) if args.mode == 'gbi' else row['rdp'], str(case)]
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode:
                raise ValueError(completed.stderr.strip())
            actual = pixels((case/'rendered.ram').read_bytes(), row['target'])
            expected = pixels(expected_ram, row['target'])
            oracle_pixels = pixels(oracle.read_bytes(), row['target'])
            result['oracle_vs_ground_truth'] = metric(oracle_pixels, expected)
            score = metric(actual, expected)
            result.update(score)
            result['passed'] = score['exact'] or score['psnr_db'] >= 40
            size = (row['target']['width'], row['target']['height'])
            a, b = Image.frombytes('RGB', size, actual), Image.frombytes('RGB', size, expected)
            a.save(case/'actual.png'); b.save(case/'oracle.png')
            ImageChops.difference(a, b).point(lambda v: min(v*8, 255)).save(case/'difference-x8.png')
            result['replay'] = json.loads((case/'report.json').read_text())
        except (ValueError, subprocess.CalledProcessError) as error:
            result['error'] = str(error)
        results.append(result)
        print(json.dumps(result, separators=(',', ':')), flush=True)
    report = dict(schema=1, renderer_sha256=hashlib.sha256((args.build/'sc64_gfx_replay').read_bytes()).hexdigest(),
                  manifest=str(args.manifest.resolve()), manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                  original_post_task_ground_truth=manifest['original_post_task_ground_truth'], mode=args.mode, threshold_rgb_psnr_db=40.0,
                  oracle_replay_passed=len(results) >= 10 and all(r['passed'] for r in results),
                  original_pixels_passed=manifest['original_post_task_ground_truth'] and len(results) >= 10 and all(r['passed'] for r in results),
                  stage2_accepted=False,
                  limitation='Oracle replay does not include inherited hidden coverage/TMEM; original post-task pairing and visual review are required for stage acceptance.',
                  cases=results)
    (output/'comparison.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['oracle_replay_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
