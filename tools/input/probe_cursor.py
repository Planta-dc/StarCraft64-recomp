#!/usr/bin/env python3
"""Capture original cursor observations; keep all retail-derived files private."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from rom_info import NTSC_U_SHA1 as ROM_SHA1, RomError, load_ntsc_u

def require_runner_rom(rom: Path, profile: str) -> None:
    try:
        load_ntsc_u(rom, require_z64=True)
    except RomError as error:
        raise SystemExit(f'This {profile} profile requires the exact NTSC-U z64 dump: {error}') from error

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--flash', type=Path, required=True, help='Original menu/save fixture')
    parser.add_argument('--output', type=Path, required=True, help='New directory under local/')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'local') or output.exists():
        raise SystemExit('Choose a new private output under ignored local/')
    rom, flash = args.rom.resolve(strict=True), args.flash.resolve(strict=True)
    require_runner_rom(rom, 'address')
    if flash.stat().st_size != 131072:
        raise SystemExit('Expected a complete 128 KiB Flash fixture')
    runner = ROOT / 'local/toolchains/ares-build/test-runner/ares-test'
    script = Path(__file__).with_name('cursor_probe.js')
    runner_hash, script_hash = digest(runner), digest(script)
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.parent / (output.name + '.log')
    with log.open('x') as stream:
        environment = dict(os.environ, SC64_RESEARCH_FIRMWARE=str(runner.parent))
        result = subprocess.run([str(runner), str(script), str(rom), str(output), 'none',
                                 str(flash), '--timeout', '300'], env=environment,
                                stdout=stream, stderr=subprocess.STDOUT, timeout=330)
    output.mkdir(exist_ok=True)
    observations = []
    for snapshot in sorted(output.glob('*.cpu-visible.bin')):
        ram = snapshot.read_bytes()
        if len(ram) != 8 * 1024 * 1024:
            raise SystemExit('Incomplete canonical RDRAM snapshot')
        observations.append({'label': snapshot.name.removesuffix('.cpu-visible.bin'),
            'float_xy': [struct.unpack_from('>f', ram, a)[0] for a in (0xafdbc, 0xafdc4)],
            'integer_xy': list(struct.unpack_from('>hh', ram, 0xafdcc)),
            'sha256': digest(snapshot)})
    report = {'schema': 1, 'rom_sha1': ROM_SHA1, 'flash_sha256': digest(flash),
        'runner_sha256': runner_hash, 'script_sha256': script_hash,
        'exit_code': result.returncode, 'log_sha256': digest(log),
        'input_unit': 'normalized [-1,1]; positive ares Y is screen-down in this runner',
        'observations': observations,
        'evidence_scope': 'Snapshot coordinates; compare PNG cursor locations and code separately'}
    (output / 'cursor-observations.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    if result.returncode or not observations:
        raise SystemExit('Original-emulator probe did not complete')
    print(output / 'cursor-observations.json')

if __name__ == '__main__':
    main()
