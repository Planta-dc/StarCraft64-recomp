#!/usr/bin/env python3
"""Convert the original title artwork into application icons, locally.

The title image is one BOLT resource (640x480, 8-bit indices) with a 256-entry
RGBA16 palette. The icon is a square crop of the Terran marine. The output is
game-derived: it stays under ignored local/icons/ and is only embedded into
personal builds (ADR-076). Builds without it fall back to the authored icon.

Usage: python3 tools/desktop/icon.py "/path/to/StarCraft 64 (USA).z64"
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from bolt_extract import BoltError, Entry, decompress_n64, FLAG_UNCOMPRESSED, u16be
from private_paths import require_local
from rom_info import load_ntsc_u

ICON_DIR = ROOT / 'local/icons'
# Verified by exact pixel match with the original title framebuffer (docs/research.md).
TITLE_DIRECTORY = 2
TITLE_IMAGE = 0x2770A221
TITLE_PALETTE = 0x6F527E67
TITLE_SIZE = (640, 480)
PALETTE_HEADER = 6
CROP_BOX = (250, 10, 480, 240)    # marine helmet and shoulder, no text
MASTER_SIZE = 1024
ICONSET_SIZES = (16, 32, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ANDROID_SIZE = 192
LINUX_SIZE = 256
ROUNDED_RADIUS = 0.2237           # macOS-style corner radius relative to the plate
MACOS_INSET = 100 / 1024          # macOS icon plates leave a transparent margin
FILES = ('icon-1024.png', 'icon-android.png', 'StarCraft64.png', 'StarCraft64.ico', 'StarCraft64.rc')
MACOS_FILES = ('StarCraft64.icns',)

def read_entry(rom: bytes, bolt: int, table: int, count: int, wanted: int) -> bytes:
    for index in range(count):
        entry = Entry(rom, table + index * 16)
        if entry.hash != wanted or entry.is_dir:
            continue
        start = bolt + entry.offset
        if entry.flags & FLAG_UNCOMPRESSED:
            return rom[start:start + entry.size]
        return decompress_n64(rom, start, entry.size)
    raise BoltError(f'BOLT entry {wanted:08X} not found')

def title_resources(rom: bytes, directory: int = TITLE_DIRECTORY, image: int = TITLE_IMAGE,
                    palette: int = TITLE_PALETTE) -> tuple[bytes, bytes, tuple[int, int]]:
    """Return the raw index plane, the RGBA16 palette payload and the image size."""
    bolt = rom.find(b'BOLT')
    if bolt < 0:
        raise BoltError('BOLT archive not found')
    top = rom[bolt + 11] or 256
    entry = Entry(rom, bolt + 16 + directory * 16)
    if not entry.is_dir:
        raise BoltError(f'BOLT entry {directory} is not a directory')
    table, count = bolt + entry.offset, entry.file_type or 256
    picture = read_entry(rom, bolt, table, count, image)
    colors = read_entry(rom, bolt, table, count, palette)
    width, height = u16be(picture, 8), u16be(picture, 10)
    if directory >= top or len(picture) != width * height + 16 or picture[2:4] != b'\x00\x08':
        raise BoltError('Title image is not a 16-byte header plus 8-bit indices')
    if len(colors) != PALETTE_HEADER + 512:
        raise BoltError('Title palette is not a six-byte header plus 256 RGBA16 entries')
    return picture[16:], colors[PALETTE_HEADER:], (width, height)

def decode_title(rom: bytes, **overrides):
    """Decode to an RGB PIL image; the RGBA16 alpha bit is dropped (the title is opaque)."""
    from PIL import Image
    indices, palette, size = title_resources(rom, **overrides)
    colors = []
    for offset in range(0, 512, 2):
        value = int.from_bytes(palette[offset:offset + 2], 'big')
        colors.append(tuple((channel << 3) | (channel >> 2)
                            for channel in ((value >> 11) & 31, (value >> 6) & 31, (value >> 1) & 31)))
    image = Image.new('RGB', size)
    image.putdata([colors[index] for index in indices])
    return image

def master(title, box=CROP_BOX):
    from PIL import Image
    return title.crop(box).resize((MASTER_SIZE, MASTER_SIZE), Image.LANCZOS).convert('RGBA')

def plate(art, size: int, *, inset: float = 0.0, rounded: bool = True):
    """Scale the master to ``size``; optionally round its corners and leave a margin."""
    from PIL import Image, ImageDraw
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    side = round(size * (1 - 2 * inset))
    # Draw the mask at 4x for smooth edges.
    scale = 4
    mask = Image.new('L', (side * scale, side * scale), 0)
    radius = round(side * scale * ROUNDED_RADIUS) if rounded else 0
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, side * scale - 1, side * scale - 1), radius=radius, fill=255)
    mask = mask.resize((side, side), Image.LANCZOS)
    face = art.resize((side, side), Image.LANCZOS)
    margin = (size - side) // 2
    canvas.paste(face, (margin, margin), mask)
    return canvas

def write_iconset(art, destination: Path) -> None:
    for size in ICONSET_SIZES:
        for factor, suffix in ((1, ''), (2, '@2x')):
            plate(art, size * factor, inset=MACOS_INSET).save(destination / f'icon_{size}x{size}{suffix}.png')

def write_icns(art, target: Path) -> bool:
    """Build the macOS icon with iconutil; other hosts skip it."""
    if platform.system() != 'Darwin':
        return False
    with tempfile.TemporaryDirectory(prefix='.sc64-iconset-') as temporary:
        iconset = Path(temporary) / 'StarCraft64.iconset'
        iconset.mkdir()
        write_iconset(art, iconset)
        subprocess.run(['iconutil', '--convert', 'icns', '--output', str(target), str(iconset)], check=True)
    return True

def build_icons(rom: bytes, output: Path, **overrides) -> dict:
    """Write every icon format into the new directory ``output`` and return a receipt."""
    art = master(decode_title(rom, **overrides))
    output.mkdir(parents=True)
    art.save(output / 'icon-1024.png')
    plate(art, ANDROID_SIZE).save(output / 'icon-android.png')
    plate(art, LINUX_SIZE).save(output / 'StarCraft64.png')
    plate(art, 256, rounded=False).save(output / 'StarCraft64.ico', sizes=[(size, size) for size in ICO_SIZES])
    # The Windows resource script is compiled with the build directory as its include path.
    (output / 'StarCraft64.rc').write_text('1 ICON "StarCraft64.ico"\n')
    made_icns = write_icns(art, output / 'StarCraft64.icns')
    names = FILES + (MACOS_FILES if made_icns else ())
    return {'schema': 1, 'source_rom_sha1': hashlib.sha1(rom).hexdigest(), 'bolt_directory': TITLE_DIRECTORY,
            'image_hash': f'{TITLE_IMAGE:08X}', 'palette_hash': f'{TITLE_PALETTE:08X}', 'crop_box': list(CROP_BOX),
            'files_sha256': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in names}}

def installed(name: str, directory: Path = ICON_DIR) -> Path | None:
    """Path of a generated icon, or None so callers fall back to the authored icon."""
    path = directory / name
    return path if path.is_file() else None

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path, help='your StarCraft 64 NTSC-U dump (z64/v64/n64)')
    parser.add_argument('--output', type=Path, default=ICON_DIR,
                        help='icon directory under local/ (default: local/icons); replaced when it exists')
    args = parser.parse_args()
    output = require_local(args.output, what='Icon output')
    _, rom = load_ntsc_u(args.rom)
    # Build beside the target and swap, so a failure never leaves a half-written icon set.
    with tempfile.TemporaryDirectory(prefix='.sc64-icons-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'icons'
        receipt = build_icons(rom, staged)
        (staged / 'icon.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if output.exists():
            shutil.rmtree(output)
        staged.replace(output)
    print(output)
    return 0

if __name__ == '__main__':
    sys.exit(main())
