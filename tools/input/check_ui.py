#!/usr/bin/env python3
"""Check completed native UI recipe evidence; OS pointer delivery is separate."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def observations(raw: bytes) -> list[dict]:
    result = []
    for line in raw.decode().splitlines():
        if line.startswith('ERROR:'):
            raise ValueError('Engine error in native run')
        if 'SC64 gesture {' in line:
            raise ValueError('Legacy candidate telemetry cannot certify submitted controller input')
        for marker, kind in (('SC64 ui_click ', 'click'), ('SC64 ui_swipe ', 'swipe'), ('SC64 hover ', 'hover'),
                             ('SC64 pad ', 'pad'), ('SC64 ', 'info')):
            if marker + '{' in line:
                row = json.loads(line.split(marker, 1)[1])
                if kind == 'pad':
                    if row.get('stage') != 'submitted' or not isinstance(row.get('source'), dict) \
                        or row.get('player') not in (1, 2):
                        raise ValueError('Incomplete submitted controller telemetry')
                    if row['player'] != 1:
                        break
                row['kind'] = kind
                row['at'] = row.get('field', row.get('fields'))
                result.append(row)
                break
    return result


def check(rows: list[dict], recipe: list[dict]) -> dict:
    clicks = [row for row in rows if row['kind'] == 'click']
    pads = [row for row in rows if row['kind'] == 'pad']
    states = [row for row in rows if row['kind'] != 'click']
    evidence = []
    gates = dict(main=False, tabs=False, mission=False, briefing=False, message=False, resume=False)
    build = False
    closed_messages = set()
    for click in clicks:
        field = click['at']
        stop = min([row['at'] for row in clicks if row['at'] > field] + [field + 360])
        emitted = [row for row in pads if field <= row['at'] < stop]
        later = [row for row in states if field < row['at'] <= field + 360]
        accepted = False
        label = 'other'
        mode = click['mode']
        if not click['queued'] or not 0 <= field - click['source_field'] <= 12:
            label = 'stale_or_unqueued'
        elif mode == 'menu' and click['token'] == 256:
            label = 'main'
            accepted = any(row['buttons'] == 0x8000 for row in emitted) and any(
                row.get('ui_token') == 262 for row in later)
        elif mode == 'menu' and click['token'] == 262:
            pressed = [row for row in emitted if row['buttons']]
            if pressed and pressed[0]['buttons'] in (0x100, 0x200):
                label = 'tabs'
                before = pressed[0]
                selected = [item['id'] for item in before['ui_items'] if item['group'] == 2 and item['selected']]
                accepted = bool(selected) and any(any(item['group'] == 2 and item['selected']
                    and item['id'] != selected[0] for item in row.get('ui_items', [])) for row in later)
            else:
                label = 'mission'
                accepted = any(row['buttons'] == 0x8000 and any(item['group'] == 3
                    and item['selected'] and item['x0'] <= click['x'] <= item['x1']
                    and item['y0'] <= click['y'] <= item['y1'] for item in row['ui_items']) for row in emitted)
        elif mode == 'briefing':
            label = 'briefing'
            # The route must reach the map before any later raw Start recipe.
            # The location card ends on Start; the text briefing pages with A.
            starts = [row for row in emitted if row['buttons'] in (0x1000, 0x8000) and row['ui_mode'] == 'briefing']
            stop_start = min([item['field'] for item in recipe if not item.get('ui_click')
                and not item.get('point') and item.get('buttons', 0) & 0x1000
                and item['field'] > field] + [field + 3600])
            accepted = bool(starts) and any(row.get('ui_mode') in ('game', 'message')
                for row in states if field < row['at'] < stop_start)
        elif mode == 'message' and not click.get('right'):
            label = 'message'
            presses = [row for row in emitted if row['buttons'] == 0x8000
                and row['ui_mode'] == 'message' and row['ui_token'] == click['token']]
            accepted = bool(presses) and any(row.get('ui_mode') in ('game', 'build', 'modal')
                for row in later if row['at'] > presses[0]['at'])
        elif mode in ('modal', 'build') and not click.get('right'):
            label = 'resume' if mode == 'modal' else 'build'
            presses = [row for row in emitted if row['buttons'] == 0x8000 and row['ui_mode'] == mode
                and row['ui_token'] == click['token'] and any(item['selected']
                    and item['x0'] <= click['x'] <= item['x1'] and item['y0'] <= click['y'] <= item['y1']
                    for item in row['ui_items'])]
            # A build request may legitimately keep the grid open (for example
            # insufficient resources). Certify selection-before-A, not success
            # of the game's command. Resume must actually return to the map.
            accepted = bool(presses) and (mode == 'build' or any(row.get('ui_mode') == 'game'
                for row in later if row['at'] > presses[0]['at']))
        if label in gates:
            gates[label] |= accepted
        if label == 'build':
            build |= accepted
        if label == 'message' and accepted:
            closed_messages.add(click['token'])
        evidence.append(dict(click=click,check=label,accepted=accepted))
    return dict(gates=gates,build_selection_accepted=build,messages_closed=len(closed_messages),observations=evidence,
        ui_recipe_accepted=all(gates.values()),physical_input_accepted=False,mission_accepted=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    directory = args.run.resolve()
    if not directory.is_relative_to(ROOT / 'local'):
        raise SystemExit('Reports must remain under ignored local/')
    receipt = json.loads((directory / 'run.json').read_text())
    raw = (directory / 'engine.log').read_bytes()
    source = receipt['inputs']['inputs']
    recipe = Path(source['path']).read_bytes()
    if receipt.get('schema')!=3 or receipt.get('exit_code') != 0 or not receipt.get('binary_unchanged') \
        or not receipt.get('resources_unchanged') or digest(raw) != receipt.get('log_sha256') \
        or digest(recipe) != source['sha256']:
        raise SystemExit('Incomplete or changed native evidence')
    try:
        report = check(observations(raw), json.loads(recipe))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    report.update(schema=1,binary_sha256=receipt['build']['binary_sha256'],
        log_sha256=digest(raw),recipe_sha256=digest(recipe),
        scope='Read-only native UI feedback and original pad events; private recipe bypasses OS input')
    (directory / 'ui.json').write_text(json.dumps(report, indent=2) + '\n')
    print(directory / 'ui.json')
    if not report['ui_recipe_accepted']:
        raise SystemExit('Native UI recipe gate failed')


if __name__ == '__main__':
    main()
