#!/usr/bin/env python3
"""Build the personal arm64 macOS SDL3 application locally, without any upload."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from game_validation import validate_ui_hooks
from icon import installed as installed_icon

ROOT = Path(__file__).resolve().parents[2]
TOOLCHAINS = ROOT / 'local/toolchains'
SDL_VERSION = '3.4.18'
SDL_ARCHIVE = TOOLCHAINS / f'sdl3/SDL3-{SDL_VERSION}.tar.gz'
FONT = TOOLCHAINS / 'dejavu/DejaVuSansMono-Bold.ttf'
FONT_LICENSE = TOOLCHAINS / 'dejavu/LICENSE'
RUNTIME = ROOT / 'local/deps/N64ModernRuntime-shell'

BACKUP_PREFIX = '.sc64-build-'
PREVIOUS_SUFFIX = '-previous.app'

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def resource_hashes(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): sha256(path)
            for path in sorted(directory.rglob('*')) if path.is_file()}

def publish_bundle(staged: Path, app: Path, previous: Path) -> None:
    """Replace app with staged; keep the old bundle only until publication succeeds."""
    if app.exists(): os.replace(app, previous)
    try: os.replace(staged, app)
    except BaseException:
        if previous.exists(): os.replace(previous, app)
        raise
    # The new bundle is in place, so rollback copies are no longer needed.
    # Also sweep copies retained by earlier builds of this tool.
    for stale in app.parent.glob(BACKUP_PREFIX + '*' + PREVIOUS_SUFFIX):
        if stale.is_dir() and not stale.is_symlink(): shutil.rmtree(stale)

def stage_resources(resources: Path) -> None:
    """Shell resources: the overlay font, its license and, when generated, the app icon."""
    resources.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FONT, resources / FONT.name)
    shutil.copy2(FONT_LICENSE, resources / 'LICENSE-DejaVu.txt')
    if icon := installed_icon('StarCraft64.icns'):
        shutil.copy2(icon, resources / icon.name)

def run(args: list[str], **kwargs) -> None:
    subprocess.run(args, check=True, **kwargs)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure-only', action='store_true')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('This tool builds the macOS arm64 profile; see tools/windows and tools/linux')
    validate_ui_hooks(ROOT / 'local/generated/game')
    run(['python3', str(ROOT / 'tools/desktop/patch_runtime.py'), '--output', str(RUNTIME)])
    build = ROOT / 'local/build/desktop'
    run(['cmake', '-S', str(ROOT), '-B', str(build), '-G', 'Ninja',
         '-DSC64_BUILD_SHELL=ON', '-DSC64_RUNTIME_DIR=' + str(RUNTIME),
         '-DCMAKE_CXX_COMPILER=/opt/homebrew/opt/llvm/bin/clang++',
         '-DCMAKE_C_COMPILER=/opt/homebrew/opt/llvm/bin/clang',
         '-DCMAKE_OSX_DEPLOYMENT_TARGET=13.0', '-DCMAKE_BUILD_TYPE=RelWithDebInfo'])
    if args.configure_only:
        return
    run(['cmake', '--build', str(build), '--target', 'sc64_app', '-j', str(args.jobs)])
    app = ROOT / 'local/dist/StarCraft64.app'
    app.parent.mkdir(parents=True, exist_ok=True)
    receipt = ROOT / 'local/reports/desktop/build.json'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # Publish a complete new bundle instead of truncating a running executable
    # or leaving stale resources from a prior build.
    with tempfile.TemporaryDirectory(prefix=BACKUP_PREFIX, dir=app.parent) as temporary:
        staged = Path(temporary) / 'StarCraft64.app'
        (staged / 'Contents/MacOS').mkdir(parents=True)
        shutil.copy2(build / 'sc64_app', staged / 'Contents/MacOS/SC64')
        stage_resources(staged / 'Contents/Resources')
        plist = {
            'CFBundleExecutable': 'SC64', 'CFBundleIdentifier': 'com.nomadic.sc64.personal',
            'CFBundleName': 'StarCraft64', 'CFBundleDisplayName': 'StarCraft 64',
            'CFBundlePackageType': 'APPL', 'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '13.0', 'NSPrincipalClass': 'NSApplication'}
        if (staged / 'Contents/Resources/StarCraft64.icns').exists():
            plist['CFBundleIconFile'] = 'StarCraft64'
        (staged / 'Contents/Info.plist').write_bytes(plistlib.dumps(plist))
        build_receipt = {'schema': 2, 'profile': 'arm64-macos', 'cloud_upload': False,
            'binary_sha256': sha256(staged / 'Contents/MacOS/SC64'),
            'sdl3_version': SDL_VERSION, 'sdl3_sha256': sha256(SDL_ARCHIVE),
            'miniaudio_version': '0.11.23', 'miniaudio_sha256': sha256(TOOLCHAINS / 'miniaudio.h'),
            'stb_truetype_sha256': sha256(TOOLCHAINS / 'stb/stb_truetype.h'),
            'resources_sha256': resource_hashes(staged / 'Contents/Resources')}
        publish_bundle(staged, app, app.parent / (Path(temporary).name + PREVIOUS_SUFFIX))
    receipt.write_text(json.dumps(build_receipt, indent=2) + '\n')
    print(receipt)
    print(app)

if __name__ == '__main__':
    main()
