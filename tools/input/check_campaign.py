#!/usr/bin/env python3
"""Check campaign gesture, selection and warning evidence in a completed native run."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or
from check_ui import observations

ROOT = Path(__file__).resolve().parents[2]


def inside(bounds: dict | None, x: float, y: float) -> bool:
    return bool(bounds and bounds['x0'] <= x <= bounds['x1']
                and bounds['y0'] <= y <= bounds['y1'])


def check(rows: list[dict], recipe: list[dict]) -> dict:
    actions = [r for r in rows if r['kind'] in ('click', 'swipe')]
    gates = dict(swipe_left=False, swipe_right=False, side_select=False, selected_entry=False,
                 warning_cancel=False, warning_continue=False,
                 wrap_first_to_last=False, wrap_last_to_first=False)
    results = []
    for action in actions:
        mode, token, field = action['mode'], action['token'], action['at']
        if not ((mode == 'menu' and token == 256) or mode == 'campaign_warning'):
            continue
        stop = min([r['at'] for r in actions if r['at'] > field] + [field + 1080])
        pads = [r for r in rows if r['kind'] == 'pad' and field <= r['at'] < stop]
        presses = [r for r in pads if r['buttons']]
        states = [r for r in rows if field < r['at'] <= stop]
        accepted = bool(action['queued'] and 0 <= field-action['source_field'] <= 12
            and presses and not any(not (a.get('ui_click') or a.get('ui_swipe'))
                and (a.get('point') or a.get('buttons') or a.get('x') or a.get('y'))
                for a in recipe if field <= a['field'] < stop))
        accepted = accepted and all(r['x'] == r['y'] == 0
            and r['source'].get('gesture') and not any(r['source'].get(k)
                for k in ('controller', 'touch', 'recipe'))
            and 0 <= r['at']-r['ui_field'] <= 12 for r in presses)
        label, transition = 'unrecognized', None
        press = presses[-1] if presses else None
        if mode == 'menu' and action['kind'] == 'swipe':
            dx = action['to'][0]-action['from'][0]
            dy = action['to'][1]-action['from'][1]
            label = 'swipe_left' if dx < 0 else 'swipe_right'
            bits = 0x200 if dx < 0 else 0x100
            carousel = action.get('carousel')
            before = None if not carousel else carousel['selected']
            transition = next((r for r in states
                if (r.get('ui_carousel') or r.get('carousel') or {}).get('ready')
                and (r.get('ui_carousel') or r.get('carousel'))['selected'] != before
                and r.get('ui_mode', r.get('mode')) == 'menu'
                and r.get('ui_token', r.get('token')) == 256), None)
            accepted = bool(accepted and carousel and carousel['ready']
                and inside(carousel, *action['from']) and abs(dx) >= 24 and abs(dx) > abs(dy)*1.25
                and len(presses) == 1 and press['buttons'] == bits
                and press['ui_mode'] == mode and press['ui_token'] == token and transition)
        elif mode == 'menu' and action['kind'] == 'click':
            first_items = [] if not presses else presses[0].get('ui_items', [])
            clicked = next((i for i in first_items if i['group'] == 5
                and inside(i, action['x'], action['y'])), None)
            if clicked and not clicked['selected']:
                label = 'side_select'
                before = (action.get('carousel') or {}).get('selected')
                delta = 0 if before is None else (clicked['id']-before) % 6
                distance = min(delta, 6-delta)
                transition = next((r for r in states if r['at'] > press['at']
                    and r.get('ui_mode') == 'menu' and r.get('ui_token') == 256
                    and (r.get('ui_carousel') or {}).get('ready')
                    and r['ui_carousel']['selected'] == clicked['id']), None)
                accepted = bool(accepted and (action.get('carousel') or {}).get('ready')
                    and transition and distance > 0 and len(presses) == distance
                    and all(r['ui_mode'] == mode and r['ui_token'] == token
                        and (r.get('ui_carousel') or {}).get('ready')
                        and r['buttons'] == (0x200 if delta <= 3 else 0x100)
                        and r['ui_carousel']['selected'] == (before + (1 if delta <= 3 else -1)*step) % 6
                        for step, r in enumerate(presses))
                    and all(b['at'] >= a['at']+18 for a,b in zip(presses, presses[1:]))
                    and all(any(r['at'] < z['at'] <= r['at']+18 and z['buttons'] == z['x'] == z['y'] == 0
                        for z in pads) for r in presses))
            else:
                label = 'selected_entry'
                items = [] if not press else press.get('ui_items', [])
                transition = next((r for r in states if r.get('ui_mode') == 'campaign_warning'
                    and (r['ui_token'] >> 16) & 0xffff == 0x217), None)
                accepted = bool(accepted and press['buttons'] == 0x8000
                    and press['ui_token'] == token and press['ui_mode'] == mode
                    and all(r['buttons'] in (0x400, 0x800) for r in presses[:-1])
                    and any(i['group'] == 1 and i['id'] == 0 and i['selected'] for i in items)
                    and any(i['group'] == 5 and i['selected'] and inside(i, action['x'], action['y'])
                        for i in items) and transition)
        elif mode == 'campaign_warning' and action['kind'] == 'click':
            bounds = action.get('bounds')
            confirm = inside(bounds, action['x'], action['y'])
            label = 'warning_continue' if confirm else 'warning_cancel'
            bits = 0x1000 if confirm else 0x4000
            target = 262 if confirm else 256
            transition = next((r for r in states if r.get('ui_mode') == 'menu'
                and r.get('ui_token') == target and (any(i['group'] == 2
                    for i in r.get('ui_items', [])) and any(i['group'] == 3
                    for i in r.get('ui_items', [])) if confirm else
                    bounds and (r.get('ui_carousel') or {}).get('selected') == bounds.get('context'))), None)
            accepted = bool(accepted and bounds and len(presses) == 1
                and press['buttons'] == bits and press['ui_mode'] == mode
                and press['ui_token'] == token and not press.get('ui_items')
                and not press.get('ui_carousel') and transition)
        # A real submission must be followed by release before the next action;
        # a mode change may cancel the pulse earlier than the six-field maximum.
        release = None if not press else next((r for r in pads if press['at'] < r['at'] <= press['at']+18
            and r['buttons'] == r['x'] == r['y'] == 0), None)
        accepted = bool(accepted and release)
        if label in gates:
            gates[label] |= accepted
        if label == 'side_select' and accepted:
            if before == 0 and clicked['id'] == 5: gates['wrap_first_to_last'] = True
            if before == 5 and clicked['id'] == 0: gates['wrap_last_to_first'] = True
        results.append(dict(action=action, check=label, accepted=accepted,
                            press=press, release=release, transition=transition))
    return dict(gates=gates, observations=results,
        campaign_recipe_accepted=all(gates.values()) and all(r['accepted'] for r in results),
        physical_input_accepted=False, android_accepted=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    directory = require_local_or(sys.exit, args.run, root=ROOT, what='Reports')
    receipt = json.loads((directory / 'run.json').read_text())
    raw = (directory / 'engine.log').read_bytes()
    source = receipt['inputs']['inputs']
    recipe = Path(source['path']).read_bytes()
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if receipt.get('schema')!=3 or receipt.get('exit_code') != 0 or not receipt.get('binary_unchanged') \
        or not receipt.get('resources_unchanged') or digest(raw) != receipt.get('log_sha256') \
        or digest(recipe) != source['sha256']:
        raise SystemExit('Incomplete or changed native evidence')
    try:
        report = check(observations(raw), json.loads(recipe))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    report.update(schema=1, binary_sha256=receipt['build']['binary_sha256'],
        log_sha256=digest(raw), recipe_sha256=digest(recipe),
        scope='Read-only rendered campaign feedback and submitted original pad events; recipe bypasses OS input')
    (directory / 'campaign.json').write_text(json.dumps(report, indent=2)+'\n')
    print(directory / 'campaign.json')
    if not report['campaign_recipe_accepted']:
        raise SystemExit('Native campaign recipe gate failed')


if __name__ == '__main__':
    main()
