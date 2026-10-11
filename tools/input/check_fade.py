#!/usr/bin/env python3
"""Check the captured 1P abort's terminal fade before VI black, not all transitions."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from check_ui import observations

ROOT=Path(__file__).resolve().parents[2]
# Original terminal abort screenshots have RGB <= 1 after VI filtering.
MAX_RGB=1
TERMINAL_FIELDS=6

def check(rows: list[dict], images: dict[str,bytes]) -> dict:
    blacks=[r['field'] for r in rows if r['kind']=='vi' and r['blank'] and r['regs'][2]==320]
    blank=min(blacks) if blacks else None
    samples=[]
    if blank is not None:
        for row in rows:
            if row['kind']!='upload' or row['width']!=320 or row['height']!=240 \
                or not blank-TERMINAL_FIELDS<=row['field']<blank:
                continue
            data=images[row['rgba']]
            if len(data)!=320*240*4: raise ValueError('Incomplete native RGBA image')
            maximum=max(max(data[0::4]),max(data[1::4]),max(data[2::4]))
            samples.append(dict(field=row['field'],task=row['task'],rgba=row['rgba'],
                maximum_rgb=maximum,sha256=hashlib.sha256(data).hexdigest()))
    distinct=len({s['task'] for s in samples})
    return dict(schema=1,terminal_fade_black_accepted=distinct>=3
        and all(s['maximum_rgb']<=MAX_RGB for s in samples),
        first_blank_field=blank,terminal_fields=TERMINAL_FIELDS,maximum_allowed_rgb=MAX_RGB,
        distinct_tasks=distinct,samples=samples,victory_accepted=False,
        full_vi_parity_accepted=False,
        scope='Uploaded 320x240 abort targets in the six fields before VI black; not earlier fade or window pixel parity')

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    directory=parser.parse_args().run.resolve()
    if not directory.is_relative_to(ROOT/'local'): raise SystemExit('Reports must stay under ignored local/')
    receipt=json.loads((directory/'run.json').read_text())
    raw=(directory/'engine.log').read_bytes()
    if receipt.get('schema')!=3 or receipt.get('exit_code')!=0 or not receipt.get('binary_unchanged') \
        or not receipt.get('resources_unchanged') or hashlib.sha256(raw).hexdigest()!=receipt.get('log_sha256'):
        raise SystemExit('Incomplete or changed native run')
    observations(raw) # Reject engine errors and legacy candidate telemetry.
    trace=directory/'frames'
    data=(trace/'frames.jsonl').read_bytes()
    rows=[json.loads(s) for s in data.splitlines()]
    images={}
    for row in rows:
        if row['kind']=='upload':
            path=(trace/row['rgba']).resolve(strict=True)
            if not path.is_relative_to(trace.resolve()): raise SystemExit('Image escapes trace directory')
            images[row['rgba']]=path.read_bytes()
    report=check(rows,images)
    report.update(binary_sha256=receipt['build']['binary_sha256'],
        run_sha256=hashlib.sha256((directory/'run.json').read_bytes()).hexdigest(),
        frames_sha256=hashlib.sha256(data).hexdigest())
    output=directory/'fade.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(output)
    if not report['terminal_fade_black_accepted']: raise SystemExit('Terminal abort fade gate failed')

if __name__=='__main__': main()
