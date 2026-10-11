#!/usr/bin/env python3
"""Capture original execution at the fenced post-task boundary using existing private checkpoints."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from private_paths import PrivatePathError, require_local
from rom_info import RomError, load_ntsc_u

SCENES = {
    'main-menu': ('reference-cold/end.state', [dict(window='main-menu', fields=6)]),
    'menu': ('reference-menu-02/end.state', [dict(window='menu', fields=6)]),
    'briefing': ('mission-01/end.state', [dict(fields=360), dict(hold='A', fields=6),
                                         dict(fields=120), dict(window='briefing', fields=6)]),
    'one-player': ('cold-saved-mission-02/end.state', [dict(window='one-player', fields=12, screens=True)]),
    'two-player': ('game-2p-01/end.state', [dict(window='two-player', fields=24, screens=True)]),
}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('scene', choices=sorted(SCENES))
    p.add_argument('output', type=Path)
    p.add_argument('--cold', action='store_true', help='Cold-boot the original UI save for the one-player scene')
    p.add_argument('--rom', type=Path, default=ROOT/'StarCraft 64 (USA).z64',
                   help='Your NTSC-U z64 dump (default: the ignored repository-root dump)')
    args = p.parse_args(argv)
    try:
        output = require_local(args.output, new=True, root=ROOT)
    except PrivatePathError as error:
        p.error(str(error))
    state, actions = SCENES[args.scene]
    if args.cold:
        if args.scene != 'one-player':
            p.error('--cold is only supported for the one-player recipe')
        recipe = json.loads((ROOT/'tools/research/recipes.json').read_text())['recipes']['cold-saved-mission-02']
        actions = recipe['actions']
    checkpoint = ROOT/'local/captures/research'/state
    if not checkpoint.is_file():
        p.error(f'Missing original-execution checkpoint: {checkpoint}')
    rom = args.rom.resolve()
    try:
        # The ares runner loads this file directly, so it must already be z64.
        load_ntsc_u(rom, require_z64=True)
    except (OSError, RomError) as error:
        p.error(f'Research execution requires the reviewed NTSC-U ROM: {error}')
    runner = ROOT/'local/toolchains/ares-build/test-runner/ares-test'
    command = [str(runner), str(ROOT/'tools/research/run_scene.js'), str(rom),
               'out='+str(output), 'state='+('none' if args.cold else str(checkpoint)), json.dumps(actions), 'default', '--timeout', '300']
    if args.cold:
        command.insert(-2, 'flash='+str(ROOT/'local/captures/research'/recipe['flash']))
    env = dict(os.environ, SC64_RESEARCH_FIRMWARE=str(runner.parent), SC64_STAGE2_POST_TASK='1')
    subprocess.run(command, env=env, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
