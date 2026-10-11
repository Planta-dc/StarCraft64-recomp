#!/usr/bin/env python3
"""Verify a private native target recipe; this is not touch/mission acceptance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from check_ui import observations as read_observations

ROOT=Path(__file__).resolve().parents[2]

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    directory=args.run.resolve()
    if not directory.is_relative_to(ROOT/'local'):
        raise SystemExit('Reports must remain under ignored local/')
    receipt=json.loads((directory/'run.json').read_text())
    raw=(directory/'engine.log').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=receipt['log_sha256']:
        raise SystemExit('Log differs from completed receipt')
    source=receipt['inputs']['inputs']
    recipe_bytes=Path(source['path']).read_bytes()
    if hashlib.sha256(recipe_bytes).hexdigest()!=source['sha256']:
        raise SystemExit('Recipe differs from completed receipt')
    targets=[item for item in json.loads(recipe_bytes) if item.get('point') and item.get('buttons')]
    try:
        events=[row for row in read_observations(raw) if row['kind']=='pad']
    except ValueError as error:
        raise SystemExit(str(error)) from error
    observations=[]
    previous=0
    presses=[]
    for event in events:
        if event['buttons'] and event['buttons']!=previous: presses.append(event)
        previous=event['buttons']
    for index,target in enumerate(targets):
        stop=targets[index+1]['field'] if index+1<len(targets) else target['field']+360
        matches=[event for event in presses if target['field']<=event['field']<stop
                 and event['buttons']==target['buttons']]
        good=False
        if len(matches)==1:
            event=matches[0]
            dx=event['cursor_x']-target['point'][0]; dy=event['cursor_y']-target['point'][1]
            good=abs(dx)<=1.5 and abs(dy)<=1.5 and 0<=event['field']-event['cursor_field']<=12
            observations.append({'target':target,'press':event,'error_xy':[dx,dy],'accepted':good})
        else: observations.append({'target':target,'matching_presses':len(matches),'accepted':False})
    accepted=bool(targets) and all(row['accepted'] for row in observations)
    accepted=accepted and receipt['exit_code']==0 and receipt['binary_unchanged'] and receipt['resources_unchanged']
    report={'schema':1,'cursor_arrival_accepted':accepted,'observations':observations,
            'physical_input_accepted':False,'selection_order_semantics_accepted':False,
            'mission_accepted':False,'binary_sha256':receipt['build']['binary_sha256'],
            'scope':'Live native feedback -> original controller buttons; recipe bypasses OS gestures'}
    (directory/'gestures.json').write_text(json.dumps(report,indent=2)+'\n')
    print(directory/'gestures.json')
    if not accepted: raise SystemExit('Native cursor arrival gate failed')

if __name__=='__main__': main()
