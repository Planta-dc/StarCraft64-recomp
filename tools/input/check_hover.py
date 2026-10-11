#!/usr/bin/env python3
"""Check sampled native hover motion and HUD interception in a completed recipe."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from check_ui import observations

ROOT=Path(__file__).resolve().parents[2]
# ADR-066 mouse hover servo: 8 px/field cap, horizon 3 + snapshot age. Sampled
# speed divides by whole-field gaps between owned snapshots, so allow a small
# quantization margin above the cap.
HOVER_STEP_CAP=8.0
HOVER_HORIZON_FIELDS=3
SNAPSHOT_AGE_FIELDS=3 # Android logs show age mostly 2 (ADR-066); one field of slack
RATE_TOLERANCE=.5
ARRIVAL_PIXELS=1.5
# The servo may release the stick while it predicts the remaining distance
# (coasting, at most horizon + snapshot age fields) or issue a short opposing
# correction; neither is a stall. A longer far plateau is. The host logs a pad row
# only when the submitted stick changes, so a plateau is the time to the next row.
FAR_PIXELS=8
MAX_FAR_ZERO_FIELDS=HOVER_HORIZON_FIELDS+SNAPSHOT_AGE_FIELDS
# One field of overshoot at the full step cap before the correction lands.
MAX_RETREAT_PIXELS=HOVER_STEP_CAP

def far_zero_plateau(pads: list[dict], move: dict, stop: int) -> int:
    """Longest span in fields of a zero stick held farther than FAR_PIXELS from the target."""
    longest=0
    for i,r in enumerate(pads):
        if r['x']==0 and r['y']==0 and math.hypot(r['cursor_x']-move['x'],r['cursor_y']-move['y'])>FAR_PIXELS:
            until=pads[i+1]['at'] if i+1<len(pads) else stop
            longest=max(longest,until-r['at'])
    return longest

def retreat(positions: list[dict], move: dict) -> float:
    """Largest sampled distance gained over the closest approach so far (overshoot or drift away)."""
    closest=math.inf; worst=0.0
    for r in positions:
        d=math.hypot(r['cursor_x']-move['x'],r['cursor_y']-move['y'])
        closest=min(closest,d); worst=max(worst,d-closest)
    return worst

def check(rows: list[dict]) -> dict:
    moves=[r for r in rows if r['kind']=='hover']
    groups=[]
    for move in moves:
        if move.get('hud') and groups and groups[-1][-1].get('hud'): groups[-1].append(move)
        else: groups.append([move])
    results=[]
    for i,group in enumerate(groups):
        move=group[0]
        start=move['at']
        stop=groups[i+1][0]['at'] if i+1<len(groups) else group[-1]['at']+120
        pads=[r for r in rows if r['kind']=='pad' and start<r['at']<stop]
        sampled=[r for r in rows if r['kind'] in ('pad','info') and start<r['at']<stop]
        prior=[r for r in rows if r['kind']=='pad' and r['at']<=start]
        if move.get('hud'):
            # Unchanged zero input is not logged again. Carry its last recorded
            # state and bracket the plateau with an owned entry/exit snapshot.
            entry=[r for r in rows if r['kind'] in ('pad','info') and start-12<=r['at']<=start]
            boundary=[r for r in rows if r['kind'] in ('pad','info') and r['at']>=stop
                and start<=r.get('cursor_field',-1)<=stop]
            sampled=(entry[-1:] if entry else [])+sampled+boundary[:1]
        positions=[]
        for r in sampled:
            if 0<=r['at']-r.get('cursor_field',-100)<=12 and r.get('ui_mode')=='game':
                if not positions or r['cursor_field']>positions[-1]['cursor_field']: positions.append(r)
        rates=[math.hypot(b['cursor_x']-a['cursor_x'],b['cursor_y']-a['cursor_y'])/
            (b['cursor_field']-a['cursor_field']) for a,b in zip(positions,positions[1:])]
        # Require multiple owned snapshots. Controller telemetry cannot prove
        # unrecorded frames or the actual OS pointer/physical input experience.
        fresh=all(m.get('mode')=='game' and 0<=m['at']-m.get('source_field',-100)<=12 for m in group)
        if move.get('hud'):
            neutral=(prior[-1:] if prior else [])+pads
            still=(len(positions)>=2 and bool(neutral)
                and all(r['buttons']==0 and r['x']==0 and r['y']==0 for r in neutral)
                and max(rates,default=0)<=.05)
            accepted=fresh and still
        else:
            arrived=any(abs(r['cursor_x']-move['x'])<=ARRIVAL_PIXELS and abs(r['cursor_y']-move['y'])<=ARRIVAL_PIXELS
                for r in positions)
            accepted=(fresh and len(positions)>=3 and arrived
                and far_zero_plateau(pads,move,stop)<=MAX_FAR_ZERO_FIELDS
                and retreat(positions,move)<=MAX_RETREAT_PIXELS
                and max(rates,default=0)<=HOVER_STEP_CAP+RATE_TOLERANCE and all(r['buttons']==0 for r in pads))
        results.append({'moves':group,'samples':len(positions),'max_sampled_pixels_per_field':max(rates,default=0),
                        'accepted':bool(accepted)})
    return {'schema':3,'hover_controller_accepted':bool(results) and all(r['accepted'] for r in results),
        'observations':results,'physical_input_accepted':False,'os_pointer_appearance_accepted':False,
        'hover_step_cap':HOVER_STEP_CAP,
        'scope':'Sampled owned native cursor motion, ADR-066 bounded step rate, arrival, no sustained zero-stick plateau, bounded retreat and HUD zero-stick interception'}

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    directory=args.run.resolve()
    if not directory.is_relative_to(ROOT/'local'): raise SystemExit('Reports must stay under ignored local/')
    receipt=json.loads((directory/'run.json').read_text())
    raw=(directory/'engine.log').read_bytes()
    source=receipt['inputs']['inputs']
    if hashlib.sha256(raw).hexdigest()!=receipt.get('log_sha256'): raise SystemExit('Log differs from receipt')
    if hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()!=source['sha256']:
        raise SystemExit('Recipe differs from receipt')
    try: result=check(observations(raw))
    except ValueError as error: raise SystemExit(str(error)) from error
    result['hover_controller_accepted'] &= (receipt.get('exit_code')==0
        and receipt.get('binary_unchanged',False) and receipt.get('resources_unchanged',False))
    result['binary_sha256']=receipt['build']['binary_sha256']
    (directory/'hover.json').write_text(json.dumps(result,indent=2)+'\n')
    print(directory/'hover.json')
    if not result['hover_controller_accepted']: raise SystemExit('Native hover gate failed')

if __name__=='__main__': main()
