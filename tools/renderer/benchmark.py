#!/usr/bin/env python3
"""Compare two offline renderers on identical private, fenced original inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or

from compare import case_paths

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


TIMINGS = {'interpret': 'interpret_ms', 'raster': 'software_ms'}
# Timing and execution-configuration fields are not part of the rendered result.
NON_SEMANTIC = {'interpret_ms', 'software_ms', 'raster_helpers'}


def compare_runs(before: dict, after: dict, before_ram: str, after_ram: str,
                 timing: str = 'interpret_ms') -> dict:
    required = {'schema', 'rectangles', 'textures', 'written_pixels', 'opcodes',
                'batches', 'targets', 'texture_keys', timing}
    for report in (before, after):
        if not required.issubset(report) or report['schema'] != 1:
            raise ValueError('Replay report lacks the semantic/timing contract')
        values = report[timing]
        if not values or any(not isinstance(v, (int, float)) or
                             not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError('Expected positive finite interpretation timings')
    if len(before[timing]) != len(after[timing]):
        raise ValueError('Unequal repetition counts')
    old, new = (statistics.median(r[timing]) for r in (before, after))
    semantic = lambda r: {k: v for k, v in r.items() if k not in NON_SEMANTIC}
    return dict(equivalent=before_ram == after_ram and semantic(before) == semantic(after),
                baseline_ram_sha256=before_ram, candidate_ram_sha256=after_ram,
                baseline_median_ms=old, candidate_median_ms=new,
                reduction_percent=(1 - new / old) * 100)


SCOPES = {
    'interpret': 'Offline interpretation after one warm-up, excluding input I/O, packet disposal, rasterization, guest scheduling and GPU/device time. Not phone FPS or stage-wide acceptance.',
    'raster': 'Offline software rasterization of the owned packet after one warm-up, excluding interpretation, guest checkpoints, RDP writeback, upload and device time. Not phone FPS, thermal or audio acceptance.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--repeat', type=int, default=25)
    parser.add_argument('--stage', choices=sorted(TIMINGS), default='interpret',
                        help='Timed stage: GBI interpretation or software rasterization')
    parser.add_argument('--baseline-workers', type=int, help='Raster helper threads for the baseline')
    parser.add_argument('--candidate-workers', type=int, help='Raster helper threads for the candidate')
    args = parser.parse_args()
    timing = TIMINGS[args.stage]
    workers = {'baseline': args.baseline_workers, 'candidate': args.candidate_workers}
    for count in workers.values():
        if count is not None and not 0 <= count <= 15:
            parser.error('workers must be in [0,15]')
    if not 1 <= args.repeat <= 100:
        parser.error('repeat must be in [1,100]')
    output = require_local_or(parser.error, args.output, new=True, root=ROOT, what='Output')
    manifest_bytes = args.manifest.read_bytes()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    rows = manifest['cases']
    if manifest['schema'] != 1 or not manifest.get('original_post_task_ground_truth'):
        raise ValueError('Expected fenced original-execution corpus')
    if not 10 <= len(rows) <= 100:
        raise ValueError('Expected 10..100 bounded cases')
    ids = [r['id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate case ID')
    for case_id in ids:
        case_paths(output / 'baseline', case_id)
        case_paths(output / 'candidate', case_id)
    binaries = {name: path.resolve(strict=True) for name, path in
                (('baseline', args.baseline), ('candidate', args.candidate))}
    hashes = {name: sha256(path) for name, path in binaries.items()}
    # Validate all inputs before producing case output. Hashes are rechecked
    # after execution, so concurrent source/binary changes invalidate the run.
    inputs = {}
    for row in rows:
        path = str(Path(row['source_ram']).resolve(strict=True))
        if path in inputs and inputs[path] != row['ram_sha256']:
            raise ValueError('Conflicting digests for the same input')
        inputs[path] = row['ram_sha256']
    if any(sha256(Path(path)) != digest for path, digest in inputs.items()):
        raise ValueError('Input digest mismatch')
    output.mkdir(parents=True)
    results = []
    for index, row in enumerate(rows):
        reports, rendered = {}, {}
        # Alternate order to reduce a systematic warm/cache/thermal bias.
        for name in (('baseline', 'candidate') if index % 2 == 0 else ('candidate', 'baseline')):
            case, _ = case_paths(output / name, row['id'])
            command = [str(binaries[name]), 'gbi', row['source_ram'],
                str(row['root']), str(case), '--repeat', str(args.repeat)]
            if workers[name] is not None: command += ['--workers', str(workers[name])]
            completed = subprocess.run(command,
                capture_output=True, text=True, timeout=60)
            if completed.returncode:
                raise ValueError(f'{name} {row["id"]}: {completed.stderr.strip()}')
            reports[name] = json.loads((case / 'report.json').read_text())
            if len(reports[name].get(timing, [])) != args.repeat:
                raise ValueError('Replay did not execute the requested repetitions')
            rendered[name] = sha256(case / 'rendered.ram')
        result = dict(id=row['id'], input_sha256=row['ram_sha256'],
                      **compare_runs(reports['baseline'], reports['candidate'],
                                     rendered['baseline'], rendered['candidate'], timing))
        results.append(result)
        print(json.dumps(result), flush=True)
    unchanged = sha256(args.manifest) == manifest_hash and all(sha256(path) == hashes[name] for name, path in binaries.items()) and all(
        sha256(Path(path)) == digest for path, digest in inputs.items())
    menu = [r for r in results if r['id'].startswith('main-menu')]
    reduction = statistics.median(r['reduction_percent'] for r in menu) if menu else None
    overall = statistics.median(r['reduction_percent'] for r in results)
    report = dict(schema=1, platform=platform.platform(), machine=platform.machine(),
        stage=args.stage, workers=workers, overall_median_reduction_percent=overall,
        manifest_sha256=manifest_hash, binaries={name: dict(path=str(path), sha256=hashes[name])
            for name, path in binaries.items()}, repetitions=args.repeat, inputs_unchanged=unchanged,
        all_equivalent=unchanged and all(r['equivalent'] for r in results),
        menu_median_reduction_percent=reduction,
        threshold_passed=unchanged and all(r['equivalent'] for r in results) and
            reduction is not None and reduction >= 20, cases=results,
        scope=SCOPES[args.stage])
    (output / 'benchmark.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['threshold_passed']:
        raise SystemExit(f'Equivalence or 20% menu {args.stage} gate failed')


if __name__ == '__main__':
    main()
