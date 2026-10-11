#!/usr/bin/env python3
"""Verify completed native hint-click/controller evidence, independently of OS input."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or
from check_ui import observations

ROOT=Path(__file__).resolve().parents[2]
# Build-menu Back is a ui_input pulse: held PULSE_FIELDS, then neutral until
# the next press (ADR-067: 4 + 4 fields; previously 6 + 12).
MENU_PRESS_SPACING=8

def check_replay(rows: list[dict], recipe: list[dict]) -> list[dict]:
    result=[]
    for click in (r for r in rows if r['kind']=='click' and r['mode']=='build' and not r.get('right')):
        field=click['at']
        stop=min([r['at'] for r in rows if r['kind']=='click' and r['at']>field]+[field+360])
        pads=[r for r in rows if r['kind']=='pad' and field<=r['at']<stop]
        presses=[r for r in pads if r.get('buttons')]
        accepted=False
        if len(presses)==2:
            back,select=presses
            accepted=(click.get('queued') and 0<=field-click['source_field']<=12
                and back['buttons']==0x4000 and back.get('ui_mode')=='build'
                and back.get('ui_token')==click['token'] and back['x']==0 and back['y']==0
                and 0<=back['at']-back.get('ui_field',-100)<=12
                and select['buttons']==0x8000 and select.get('ui_mode')=='game'
                and select.get('ui_token')==3 and select['at']>=back['at']+MENU_PRESS_SPACING
                and select['x']==0 and select['y']==0
                and back['ui_field']<select.get('ui_field',0)<=select['at']
                and 0<=select['at']-select.get('ui_field',-100)<=12
                and back['ui_field']<select.get('cursor_field',0)<=select['at']
                and 0<=select['at']-select.get('cursor_field',-100)<=12
                and abs(select.get('cursor_x',-100)-click['x'])<=1.5
                and abs(select.get('cursor_y',-100)-click['y'])<=1.5
                and any(back['at']<r['at']<select['at'] and r['buttons']==0 and r.get('ui_mode')=='game' for r in pads)
                and any(r['at']>select['at'] and r['buttons']==0 for r in pads)
                and not any(a.get('point') or (not a.get('ui_click') and a.get('buttons'))
                    for a in recipe if field<=a['field']<stop))
        result.append({'click':click,'presses':presses,'accepted':bool(accepted)})
    return result

def check_queue(rows: list[dict], results: list[dict]) -> list[dict]:
    groups=[]
    for row in results:
        if groups and row['click']['at']-groups[-1][-1]['click']['at']<18:
            groups[-1].append(row)
        else: groups.append([row])
    evidence=[]
    for group in groups:
        if len(group)<2: continue
        presses=[r['press'] for r in group if r['accepted'] and r.get('press')]
        cadence=len(presses)==len(group) and all(b['at']>=a['at']+18 for a,b in zip(presses,presses[1:]))
        moves=[r for r in rows if r['kind']=='hover' and not r.get('hud')
            and group[-1]['click']['at']<=r['at']<(presses[-1]['at']+18 if presses else 0)]
        resumes=[]
        for move in moves:
            stop=min([r['at'] for r in rows if r['kind']=='hover' and r['at']>move['at']]+[move['at']+180])
            output=[r for r in rows if r['kind']=='pad' and move['at']<r['at']<stop]
            moving=[r for r in output if r['x']!=0 or r['y']!=0]
            accepted=bool(cadence and moving and presses[-1]['at']+18<=moving[0]['at']<=presses[-1]['at']+22)
            if moving:
                first=moving[0]
                dx=move['x']-first.get('cursor_x',-100)
                dy=move['y']-first.get('cursor_y',-100)
                approaching=any(0<=r['at']-r.get('cursor_field',-100)<=12
                    and math.hypot(r.get('cursor_x',-100)-move['x'],r.get('cursor_y',-100)-move['y'])
                        <math.hypot(dx,dy)-.5 for r in output if r['at']>first['at'])
                accepted=accepted and all(r['buttons']==0 for r in moving) \
                    and 0<=first['at']-first.get('cursor_field',-100)<=12 \
                    and dx*first['x']-dy*first['y']>0 and approaching
            resumes.append(dict(move=move,accepted=bool(accepted)))
        evidence.append(dict(click_fields=[r['click']['at'] for r in group],
            press_fields=[r['at'] for r in presses],cadence_accepted=bool(cadence),hover_resumes=resumes))
    return evidence

def check(rows: list[dict], recipe: list[dict]) -> dict:
    clicks=[r for r in rows if r['kind']=='click' and r['mode']=='game']
    result=[]
    last_press=-1
    for index,click in enumerate(clicks):
        field=click['at']
        pads=[r for r in rows if r['kind']=='pad' and field<=r['at']<=field+144]
        presses=[r for r in pads if r.get('buttons') and r['at']>last_press]
        hint=None
        accepted=False
        if presses:
            press=presses[0]
            last_press=press['at']
            hints=[item for item in press.get('ui_items',[]) if item.get('group')==4
                and item['x0']<=click['x']<item['x1'] and item['y0']<=click['y']<item['y1']]
            release=next((r for r in pads if r['at']>press['at']),None)
            # FIFO clicks may wait behind earlier six-field pulses and twelve
            # neutral fields. Associate each click with exactly one later edge.
            interval=[r for r in pads if r['at']<=press['at']]
            if len(hints)==1:
                hint=hints[0]
                accepted=(click.get('queued') and 0<=field-click['source_field']<=12
                    and press.get('ui_mode')=='game' and press.get('ui_token')==click['token']
                    and 0<=press['at']-press['ui_field']<=12
                    and press['buttons']==hint['buttons'] and press['x']==0 and press['y']==0
                    and release is not None and release['buttons']==0
                    and all(r['x']==0 and r['y']==0 for r in interval)
                    and not any(not (a.get('ui_click') or a.get('point')) and a.get('buttons')
                        and a['field']<=press['at'] and a['field']+a.get('duration',0)>field for a in recipe))
        result.append({'click':click,'hint':hint,'press':press if presses else None,'accepted':bool(accepted)})
    replay=check_replay(rows,recipe)
    queues=check_queue(rows,result)
    return {'schema':2,'hint_controller_accepted':bool(result) and all(r['accepted'] for r in result),
        'build_replay_accepted':bool(replay) and all(r['accepted'] for r in replay),
        'build_replays':replay,'queues':queues,
        'queue_controller_accepted':bool(queues) and all(q['cadence_accepted']
            and all(r['accepted'] for r in q['hover_resumes']) for q in queues),
        'observations':result,'physical_input_accepted':False,'visual_feedback_accepted':False,
        'construction_accepted':False,'mission_accepted':False,
        'scope':'Native hint hit-testing -> one matching original pad pulse with zero stick; OS events and GUI pixels are separate'}

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    directory=require_local_or(sys.exit,args.run,root=ROOT,what='Reports')
    receipt=json.loads((directory/'run.json').read_text())
    raw=(directory/'engine.log').read_bytes()
    source=receipt['inputs']['inputs']
    recipe_bytes=Path(source['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=receipt.get('log_sha256'):
        raise SystemExit('Log differs from completed receipt')
    if hashlib.sha256(recipe_bytes).hexdigest()!=source['sha256']:
        raise SystemExit('Recipe differs from completed receipt')
    try: result=check(observations(raw),json.loads(recipe_bytes))
    except ValueError as error: raise SystemExit(str(error)) from error
    result['hint_controller_accepted'] &= receipt.get('exit_code')==0 and receipt.get('binary_unchanged',False) and receipt.get('resources_unchanged',False)
    result['build_replay_accepted'] &= receipt.get('exit_code')==0 and receipt.get('binary_unchanged',False) and receipt.get('resources_unchanged',False)
    result['binary_sha256']=receipt['build']['binary_sha256']
    (directory/'hud.json').write_text(json.dumps(result,indent=2)+'\n')
    print(directory/'hud.json')
    if not result['hint_controller_accepted']: raise SystemExit('Native hint controller gate failed')
    if result['queues'] and not result['queue_controller_accepted']: raise SystemExit('Native HUD queue/hover gate failed')
    if result['build_replays'] and not result['build_replay_accepted']: raise SystemExit('Native build close/replay gate failed')

if __name__=='__main__': main()
