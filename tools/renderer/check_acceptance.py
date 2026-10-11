#!/usr/bin/env python3
"""Recompute the frozen original-target gate with binary/input freshness and explicit visual evidence."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or
from compare import case_paths, metric, pixels


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def check(comparison: Path, visual: Path, renderer: Path) -> dict:
    report = json.loads(comparison.read_text())
    require(report['schema'] == 1 and report['mode'] == 'gbi' and report['threshold_rgb_psnr_db'] == 40,
            'Unexpected comparison schema/domain/threshold')
    require(report['original_post_task_ground_truth'], 'Controlled oracle replay alone is insufficient')
    require(sha(renderer) == report['renderer_sha256'], 'Renderer binary changed since comparison')
    manifest_file = Path(report['manifest'])
    require(sha(manifest_file) == report['manifest_sha256'], 'Manifest changed since comparison')
    manifest = json.loads(manifest_file.read_text())
    require(len(manifest['cases']) >= 10, 'At least ten original frames are required')
    reviewed = json.loads(visual.read_text())
    require(reviewed['comparison_sha256'] == sha(comparison), 'Visual review belongs to another comparison')
    require(reviewed['case_ids'] == [c['id'] for c in manifest['cases']], 'Every case must be visually reviewed')
    require(all(reviewed['checks'][name] for name in ('no_missing_objects', 'no_palette_errors', 'no_visible_tile_seams')),
            'Visual artifact gate failed')
    require(sha(Path(reviewed['contact_sheet'])) == reviewed['contact_sheet_sha256'], 'Visual contact sheet changed')
    results = []
    scenes, coverage = Counter(), Counter()
    recorded = {row['id']: row for row in report['cases']}
    for case in manifest['cases']:
        require(case['id'] in recorded and recorded[case['id']]['passed'], 'Missing/past-failing recorded case')
        for path_key, digest_key in [('source_ram','ram_sha256'), ('rdp','rdp_sha256'), ('source_post','post_sha256')]:
            require(sha(Path(case[path_key])) == case[digest_key], 'Source capture content changed')
        actual_file = case_paths(comparison.parent, case['id'])[0]/'rendered.ram'
        expected = pixels(Path(case['source_post']).read_bytes(), case['target'])
        actual = pixels(actual_file.read_bytes(), case['target'])
        score = metric(actual, expected)
        require(score['exact'] or score['psnr_db'] >= 40, f'{case["id"]}: original target RGB gate failed')
        require(score == {k: recorded[case['id']][k] for k in score}, 'Recorded metric differs from recomputation')
        results.append(dict(id=case['id'], **score))
        scenes[case['id'].rsplit('-',1)[0]] += 1
        coverage.update({int(k): v for k, v in recorded[case['id']]['replay']['opcodes'].items()})
    require(set(scenes) == {'main-menu-02','menu-01','briefing-01','one-player-02','reference-2p-01'}, 'Scene set differs')
    require(all(n >= 3 for n in scenes.values()), 'Scene sampling is too small')
    required_gbi = {5,9,10,219,222,223,226,227,237,249,250,252,255}
    require(required_gbi <= coverage.keys(), 'Required captured GBI families are missing')
    scores = [row['psnr_db'] for row in results if not row['exact']]
    return dict(schema=1, stage2_accepted=True, scope='Offline S2DEX2 native-target RGB, supplied NTSC-U corpus on macOS arm64',
                threshold_rgb_psnr_db=40.0, frames=len(results), scenes=dict(scenes),
                minimum_psnr_db=min(scores) if scores else None, exact_frames=sum(r['exact'] for r in results),
                renderer_sha256=report['renderer_sha256'], comparison_sha256=sha(comparison),
                visual_review_sha256=sha(visual), cases=results,
                limitation='No bit-exact hidden coverage, VI filtering, shell/Android or campaign-wide feedback claim; D-019/D-029 remain open.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('comparison', type=Path)
    p.add_argument('visual', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--renderer', type=Path, default=Path('local/build/renderer/native/gfx_core/sc64_gfx_replay'))
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = require_local_or(p.error, args.output, new=True, root=root, what='Output')
    result = check(args.comparison, args.visual, args.renderer)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('stage2_accepted','frames','minimum_psnr_db','exact_frames')}))


if __name__ == '__main__':
    main()
