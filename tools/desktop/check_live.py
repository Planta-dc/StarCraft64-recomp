#!/usr/bin/env python3
"""Check bounded VI cadence, real pause and shutdown in a private shell run."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ('fields', 'tasks', 'samples', 'audio_played_frames', 'audio_nonzero_frames')

def analyze(log: str) -> dict:
    if any(line.startswith('ERROR:') for line in log.splitlines()):
        raise ValueError('Engine log contains an error')
    samples = []
    boundary = 0
    for line in log.splitlines():
        if 'SC64 lifecycle event ' in line:
            boundary += 1
        if 'SC64 {' in line:
            sample = json.loads(line[line.index('SC64 {') + 5:])
            if sample['error'] or not sample['running']:
                raise ValueError('Guest is not running normally')
            samples.append((boundary, sample))
    if len(samples) < 4:
        raise ValueError('Insufficient live telemetry')
    cadence, frozen, transitions, resumed_cadence = [], [], [], []
    resumed = False
    for (before_boundary, before), (after_boundary, after) in zip(samples, samples[1:]):
        dt = after['host_seconds'] - before['host_seconds']
        if dt <= 0: raise ValueError('Host timeline is not increasing')
        if before['paused'] and not after['paused']:
            resumed = True
        if before_boundary != after_boundary or before['paused'] != after['paused']:
            transitions.append({'from': before['host_seconds'], 'to': after['host_seconds'],
                                'reason': 'recorded lifecycle or pause boundary'})
            continue
        if before['paused']:
            delta = {name: after[name] - before[name] for name in FROZEN}
            frozen.append({'seconds': dt, 'delta': delta, 'quiescent': all(v == 0 for v in delta.values())})
        else:
            rate = (after['fields'] - before['fields']) / dt
            row = {'seconds': dt, 'fields_per_second': rate, 'nominal_60': 59 <= rate <= 61}
            cadence.append(row)
            if resumed: resumed_cadence.append(row)
    return {'samples': len(samples), 'cadence': cadence, 'paused_intervals': frozen,
            'background_input_probe': any(s.get('background_input_probe', False) for _, s in samples),
            'transition_intervals': transitions,
            'cadence_accepted': bool(cadence) and all(row['nominal_60'] for row in cadence),
            'pause_accepted': bool(frozen) and all(row['quiescent'] for row in frozen),
            'resumed_cadence': resumed_cadence,
            'resume_accepted': bool(resumed_cadence) and all(row['nominal_60'] for row in resumed_cadence),
            'zero_source_drops': all(s['audio_dropped_frames'] == 0 for _, s in samples),
            'nonzero_output_frames': samples[-1][1]['audio_nonzero_frames'],
            'final_paused': samples[-1][1]['paused'], 'final_fields': samples[-1][1]['fields']}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--require-paused-shutdown', action='store_true')
    parser.add_argument('--require-resume', action='store_true',
                        help='Require measured nominal cadence after an observed pause/resume')
    args = parser.parse_args()
    directory = require_local_or(sys.exit, args.run, root=ROOT, what='Private live reports')
    receipt = json.loads((directory / 'run.json').read_text())
    if receipt.get('schema') != 3:
        raise ValueError('Run receipt predates the SDL3 shell; rerun with the current launcher')
    log = (directory / 'engine.log').read_bytes()
    if hashlib.sha256(log).hexdigest() != receipt['log_sha256']:
        raise ValueError('Engine log differs from the completed run receipt')
    report = analyze(log.decode('utf-8'))
    require_resume = args.require_resume or receipt.get('resume_requested', False)
    report.update({'schema': 3, 'scope': f"{receipt['build']['profile']} desktop lifecycle/cadence only",
                   'exit_code': receipt['exit_code'], 'binary_sha256': receipt['build']['binary_sha256'],
                   'run_sha256': hashlib.sha256((directory / 'run.json').read_bytes()).hexdigest(),
                   'binary_unchanged': receipt['binary_unchanged'],
                   'resources_unchanged': receipt.get('resources_unchanged', False),
                   'require_resume': require_resume,
                   'keyboard_accepted': False, 'mission_identity_accepted': False})
    report['lifecycle_accepted'] = (receipt['exit_code'] == 0 and receipt['binary_unchanged']
        and not receipt.get('background_input_probe', False) and not report['background_input_probe']
        and report['resources_unchanged']
        and report['cadence_accepted'] and report['pause_accepted'] and report['zero_source_drops']
        and (not require_resume or report['resume_accepted'])
        and (not args.require_paused_shutdown or report['final_paused']))
    # Neither a recipe filename nor this timing check certifies original mission
    # identity, physical keyboard input or perceptual audio quality.
    (directory / 'lifecycle.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not report['lifecycle_accepted']: raise SystemExit(1)

if __name__ == '__main__': main()
