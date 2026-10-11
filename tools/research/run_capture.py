#!/usr/bin/env python3
"""Replay authored research inputs into a new private capture directory."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local
from rom_info import RomError, load_ntsc_u


def main():
    root = Path(__file__).resolve().parents[2]
    recipes = json.loads(Path(__file__).with_name('recipes.json').read_text())['recipes']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recipe', choices=sorted(recipes))
    parser.add_argument('--rom', type=Path, default=root / 'StarCraft 64 (USA).z64')
    parser.add_argument('--captures', type=Path, default=root / 'local/captures/research')
    parser.add_argument('--runner', type=Path,
                        default=root / 'local/toolchains/ares-build/test-runner/ares-test')
    args = parser.parse_args()
    try:
        captures = require_local(args.captures, root=root, what='Captures')
        # The ares runner loads the file directly; validate it before startup.
        load_ntsc_u(args.rom, require_z64=True)
        recipe = recipes[args.recipe]
        output = captures / args.recipe
        if output.exists():
            raise ValueError('capture exists; choose a fresh --captures root and replay dependencies')
        state = 'none' if recipe['state'] == 'none' else str(captures / recipe['state'])
        if state != 'none' and not Path(state).is_file():
            raise ValueError(f'replay the parent recipe first: {state}')
        command = [str(args.runner.resolve()), str(root / 'tools/research/run_scene.js'),
                   str(args.rom.resolve()), 'out=' + str(output), 'state=' + state,
                   json.dumps(recipe['actions']), recipe['mode']]
        if 'flash' in recipe:
            flash = captures / recipe['flash']
            if not flash.is_file():
                raise ValueError(f'create the original UI save first: {flash}')
            command.append('flash=' + str(flash))
        command += ['--timeout', '300']
        captures.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, SC64_RESEARCH_FIRMWARE=str(args.runner.resolve().parent))
        return subprocess.run(command, cwd=root, env=env).returncode
    except (OSError, ValueError, RomError) as error:
        print(f'Capture rejected: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
