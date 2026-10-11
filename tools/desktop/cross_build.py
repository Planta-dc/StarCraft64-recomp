#!/usr/bin/env python3
"""Cross-build the personal Windows or Linux x86_64 SDL3 shell on the macOS host.

Windows uses Homebrew mingw-w64; Linux uses a local Docker image (no registry
push, no remote build). Generated game code never leaves this machine.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/desktop'))
import bootstrap
import patch_shell_runtime
from icon import installed as installed_icon
from game_validation import validate_ui_hooks
from private_paths import PACKAGE_FORBIDDEN_SUFFIXES
from rom_info import MAGIC_FORMATS

RUNTIME = ROOT / 'local/deps/N64ModernRuntime-shell'
DOCKERFILE = ROOT / 'tools/desktop/linux-cross.Dockerfile'
TARGETS = {
    'windows': {'binary': 'StarCraft64.exe', 'strip': 'x86_64-w64-mingw32-strip',
                'toolchain': 'cmake/toolchains/mingw-w64-x86_64.cmake', 'profile': 'x86_64-windows'},
    'linux': {'binary': 'StarCraft64', 'strip': 'x86_64-linux-gnu-strip',
              'toolchain': 'cmake/toolchains/linux-x86_64.cmake', 'profile': 'x86_64-linux'},
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args: list[str | Path], **kwargs) -> None:
    subprocess.run([str(item) for item in args], check=True, **kwargs)

def docker_image() -> str:
    """Build (or reuse) the local cross image, tagged by its Dockerfile hash."""
    tag = 'sc64-linux-cross:' + sha256(DOCKERFILE)[:16]
    present = subprocess.run(['docker', 'image', 'inspect', tag], capture_output=True).returncode == 0
    if not present:
        run(['docker', 'build', '--platform', 'linux/arm64', '-t', tag, '-f', DOCKERFILE, DOCKERFILE.parent])
    return tag

def in_container(image: str, command: list[str]) -> list[str]:
    # Same absolute path inside the container, so CMake caches stay valid.
    return ['docker', 'run', '--rm', '--platform', 'linux/arm64', '--user', f'{os.getuid()}:{os.getgid()}',
            '-v', f'{ROOT}:{ROOT}', '-w', str(ROOT), image, *command]

def audit(files: list[Path]) -> dict[str, str]:
    """Package members are authored resources and the binary: no private inputs."""
    result = {}
    for path in files:
        data = path.read_bytes()
        if path.suffix.lower() in PACKAGE_FORBIDDEN_SUFFIXES or data[:4] in frozenset(MAGIC_FORMATS):
            raise ValueError(f'Forbidden private input in package: {path.name}')
        result[path.name] = hashlib.sha256(data).hexdigest()
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=tuple(TARGETS))
    parser.add_argument('--configure-only', action='store_true')
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--build-type', choices=bootstrap.BUILD_TYPES, default=bootstrap.DEFAULT_BUILD_TYPE,
                        help='CMake build type (default: %(default)s)')
    args = parser.parse_args()
    target = TARGETS[args.target]
    validate_ui_hooks(ROOT / 'local/generated/game')
    bootstrap.main()
    patch_shell_runtime.prepare(ROOT / 'local/deps/N64ModernRuntime', RUNTIME)
    build = ROOT / f'local/build/{args.target}'
    configure = ['cmake', '-S', str(ROOT), '-B', str(build), '-G', 'Ninja',
                 f'-DCMAKE_TOOLCHAIN_FILE={ROOT / target["toolchain"]}', '-DSC64_BUILD_SHELL=ON',
                 f'-DSC64_RUNTIME_DIR={RUNTIME}', f'-DCMAKE_BUILD_TYPE={args.build_type}',
                 # Empty when no icon was generated, which also clears a stale CMake cache entry.
                 f'-DSC64_ICON_RC={installed_icon("StarCraft64.rc") or ""}']
    compile_ = ['cmake', '--build', str(build), '--target', 'sc64_app', '-j', str(args.jobs)]
    strip = [target['strip'], '--strip-debug']
    wrap = (lambda command: in_container(docker_image(), command)) if args.target == 'linux' else (lambda c: c)
    run(wrap(configure))
    if args.configure_only:
        return
    run(wrap(compile_))
    dist = ROOT / 'local/dist'
    dist.mkdir(parents=True, exist_ok=True)
    package = dist / f'StarCraft64-{args.target}'
    with tempfile.TemporaryDirectory(prefix='.sc64-cross-', dir=dist) as temporary:
        staged = Path(temporary) / package.name
        staged.mkdir()
        binary = staged / target['binary']
        shutil.copy2(build / target['binary'], binary)
        run(wrap([*strip, str(binary)]))
        shutil.copy2(bootstrap.FONT, staged / bootstrap.FONT.name)
        shutil.copy2(bootstrap.FONT_LICENSE, staged / 'LICENSE-DejaVu.txt')
        # A Linux executable cannot embed an icon; ship the PNG for launchers and desktop entries.
        if args.target == 'linux' and (icon := installed_icon('StarCraft64.png')):
            shutil.copy2(icon, staged / icon.name)
        members = sorted(staged.iterdir())
        receipt = {'schema': 1, 'profile': target['profile'], 'build_type': args.build_type, 'cloud_upload': False,
                   'binary_sha256': sha256(binary), 'sdl3_version': bootstrap.SDL_VERSION,
                   'sdl3_sha256': sha256(bootstrap.SDL_ARCHIVE), 'files_sha256': audit(members),
                   'toolchain': subprocess.run(wrap([target['strip'].replace('strip', 'g++'), '--version']),
                                               check=True, capture_output=True, text=True).stdout.splitlines()[0],
                   'user_acceptance': False}
        archive = Path(temporary) / (package.name + ('.zip' if args.target == 'windows' else '.tar.gz'))
        if args.target == 'windows':
            with ZipFile(archive, 'w', ZIP_DEFLATED) as output:
                for member in members: output.write(member, f'{package.name}/{member.name}')
        else:
            with tarfile.open(archive, 'w:gz') as output:
                for member in members: output.add(member, f'{package.name}/{member.name}')
        receipt['archive_sha256'] = sha256(archive)
        # Publish the directory and archive only once both are complete.
        if package.exists(): shutil.rmtree(package)
        os.replace(staged, package)
        os.replace(archive, dist / archive.name)
    report = ROOT / f'local/reports/{args.target}/build.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(receipt, indent=2) + '\n')
    print(report)
    print(dist / archive.name)

if __name__ == '__main__':
    main()
