#!/usr/bin/env python3
"""Capture original UI mode, widget and cursor observations with provenance."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_paths import require_local_or
import struct
import subprocess
from probe_cursor import ROOT, ROM_SHA1, digest, require_runner_rom

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--flash', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--route', choices=['mission','saved','hud','campaign'], default='mission')
    args = parser.parse_args()
    output = require_local_or(sys.exit, args.output, new=True, root=ROOT, what='Private output')
    rom, flash = args.rom.resolve(strict=True), args.flash.resolve(strict=True)
    require_runner_rom(rom, 'UI')
    if flash.stat().st_size != 131072:
        raise SystemExit('Expected a complete 128 KiB Flash fixture')
    runner = ROOT/'local/toolchains/ares-build/test-runner/ares-test'
    script = Path(__file__).with_name('ui_probe.js')
    output.parent.mkdir(parents=True,exist_ok=True)
    log = output.parent/(output.name+'.log')
    runner_hash, script_hash = digest(runner), digest(script)
    with log.open('x') as stream:
        run = subprocess.run([str(runner),str(script),str(rom),str(output),str(flash),args.route,
            '--timeout','300'],env=dict(os.environ,SC64_RESEARCH_FIRMWARE=str(runner.parent)),
            stdout=stream,stderr=subprocess.STDOUT,timeout=330)
    output.mkdir(exist_ok=True)
    observations=[]
    for path in sorted(output.glob('*.cpu-visible.bin')):
        ram=path.read_bytes()
        if len(ram)!=0x800000:
            raise SystemExit('Incomplete canonical RDRAM snapshot')
        word=lambda a: struct.unpack_from('>I',ram,a)[0]
        root=word(0xa4ab0)
        valid=0x80000000<=root<=0x807fffb8
        observations.append({'label':path.name.removesuffix('.cpu-visible.bin'),
            'sha256':digest(path),'mode':struct.unpack_from('>h',ram,0xa5ab4)[0],
            'menu_state':word(0xd1170),'main_selected':ram[0xd13b8],
            'cursor_locked':struct.unpack_from('>h',ram,0xf0c20)[0],
            'root':root,'callback':word((root&0x7fffff)+0x2c) if valid else None,
            'selected_child':word((root&0x7fffff)+0x40) if valid else None,
            'message_id':word(0xb03d8),
            'build_active':ram[0xc6a64], 'build_selected':word(0xafe0c)})
    report={'schema':1,'rom_sha1':ROM_SHA1,'flash_sha256':digest(flash),
        'runner_sha256':runner_hash,'script_sha256':script_hash,'log_sha256':digest(log),
        'route':args.route,'exit_code':run.returncode,'observations':observations,
        'scope':'Original controller actions and canonical snapshots; inspect paired PNG/code separately'}
    (output/'ui-observations.json').write_text(json.dumps(report,indent=2)+'\n')
    if run.returncode or not observations:
        raise SystemExit('Original UI probe did not complete')
    print(output/'ui-observations.json')

if __name__=='__main__':
    main()
