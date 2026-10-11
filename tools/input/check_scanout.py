#!/usr/bin/env python3
"""Check bounded live VI/target association; this is not full VI pixel parity."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or

ROOT=Path(__file__).resolve().parents[2]

def check(rows: list[dict]) -> dict:
    vis={r['revision']:r for r in rows if r['kind']=='vi'}
    presents=[r for r in rows if r['kind']=='present']
    violations=[]
    blank=[]
    visible=[]
    for p in presents:
        v=vis.get(p['revision'])
        if not v:
            violations.append(dict(present=p,error='Missing owned VI snapshot'))
            continue
        if v['blank']:
            blank.append(p)
            if p['visible']: violations.append(dict(present=p,error='Image shown during VI black'))
        if p['visible']:
            visible.append(p)
            regs=v['regs']
            stride=regs[2]*(2 if regs[0]&3==2 else 4)
            offset=(regs[1]&0xffffff)-p['address']
            # CPU frames (ADR-068) carry the task their swap followed; they
            # must follow the VI transition floor, not a completed task id.
            generation=(v['minimum_task']<=p['task']+1 if p.get('cpu')
                else v['minimum_task']<=p['task']<=v['task'])
            if p['width']!=regs[2] or not stride or offset<0 or offset>stride*2 \
                or offset%stride or not generation:
                violations.append(dict(present=p,error='Wrong mode, origin or task generation'))
    resumed=bool(blank) and any(p['field']>blank[-1]['field'] and p['width']==640 for p in visible)
    return dict(schema=1,scanout_accepted=bool(presents and blank and resumed and not violations),
        black_presents=len(blank),visible_presents=len(visible),resumed_640=resumed,
        violations=violations,full_vi_parity_accepted=False,victory_accepted=False,
        scope='Live VI blanking, target origin/width and task generation on a mission abort')

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    directory=require_local_or(sys.exit,args.run,root=ROOT,what='Reports')
    receipt=json.loads((directory/'run.json').read_text())
    raw=(directory/'engine.log').read_bytes()
    if receipt.get('schema')!=3 or receipt.get('exit_code')!=0 or not receipt.get('binary_unchanged') \
        or not receipt.get('resources_unchanged') or hashlib.sha256(raw).hexdigest()!=receipt.get('log_sha256'):
        raise SystemExit('Incomplete or changed native run')
    if any(line.startswith('ERROR:') for line in raw.decode().splitlines()): raise SystemExit('Native engine error')
    trace=directory/'frames'
    data=(trace/'frames.jsonl').read_bytes()
    report=check([json.loads(line) for line in data.splitlines()])
    report['binary_sha256']=receipt['build']['binary_sha256']
    report['trace_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(trace.iterdir()) if p.suffix in ('.jsonl','.rgba','.bgra')}
    report['run_sha256']=hashlib.sha256((directory/'run.json').read_bytes()).hexdigest()
    (directory/'scanout.json').write_text(json.dumps(report,indent=2)+'\n')
    print(directory/'scanout.json')
    if not report['scanout_accepted']: raise SystemExit('Live scanout gate failed')

if __name__=='__main__': main()
