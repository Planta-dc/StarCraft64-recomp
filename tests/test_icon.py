import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('sc64_icon', ROOT / 'tools/desktop/icon.py')
icon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = icon
spec.loader.exec_module(icon)

DIRECTORY, IMAGE, PALETTE = 1, 0x11223344, 0x55667788
WIDTH, HEIGHT = 640, 480

def entry(file_type, size, offset, hash_, flags=0x08):
    return struct.pack('>BBBBIII', flags, 0, 0, file_type, size, offset, hash_)

def palette_payload():
    # Index 0 is red, 1 is green, 2 is blue, 3 is white (RGBA16, alpha bit set).
    colors = [0xF801, 0x07C1, 0x003F, 0xFFFF] + [0] * 252
    return b'\x01\x02\x03\x04\x05\x06' + struct.pack('>256H', *colors)

def image_payload(indices):
    return struct.pack('>HHIHHI', 0, 8, 0, WIDTH, HEIGHT, 0) + indices

def synthetic_rom(image=None, palette=None, directory=DIRECTORY):
    """Uncompressed BOLT archive: top-level files before `directory`, then a directory
    holding the title image and palette. Offsets are relative to the BOLT header."""
    indices = bytes((x // 160) % 4 for _ in range(HEIGHT) for x in range(WIDTH))
    image = image_payload(indices) if image is None else image
    palette = palette_payload() if palette is None else palette
    bolt = 0x100
    table = 16 + 16 * (directory + 1)
    files = table + 32
    body = bytearray(bolt + files) + image + palette
    body[bolt:bolt + 4] = b'BOLT'
    body[bolt + 11] = directory + 1
    top = [entry(0, 0, 0, 1)] * directory + [entry(2, 0, table, 0, flags=0)]
    for index, item in enumerate(top):
        body[bolt + 16 + index * 16:bolt + 32 + index * 16] = item
    body[bolt + table:bolt + table + 16] = entry(18, len(image), files, IMAGE)
    body[bolt + table + 16:bolt + table + 32] = entry(28, len(palette), files + len(image), PALETTE)
    return bytes(body)

OVERRIDES = {'directory': DIRECTORY, 'image': IMAGE, 'palette': PALETTE}

class TitleDecodeTests(unittest.TestCase):
    def test_resources_split_header_and_palette(self):
        indices, colors, size = icon.title_resources(synthetic_rom(), **OVERRIDES)
        self.assertEqual(size, (WIDTH, HEIGHT))
        self.assertEqual(len(indices), WIDTH * HEIGHT)
        self.assertEqual(len(colors), 512)
        self.assertEqual(colors[:2], b'\xf8\x01')

    def test_decode_expands_five_bit_channels_and_drops_alpha(self):
        picture = icon.decode_title(synthetic_rom(), **OVERRIDES)
        self.assertEqual([picture.getpixel((x, 0)) for x in (0, 160, 320, 480)],
                         [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)])

    def test_missing_entry_and_bad_shapes_fail_explicitly(self):
        with self.assertRaisesRegex(icon.BoltError, 'not found'):
            icon.title_resources(synthetic_rom(), directory=DIRECTORY, image=0xDEAD, palette=PALETTE)
        with self.assertRaisesRegex(icon.BoltError, 'archive not found'):
            icon.title_resources(bytes(1024), **OVERRIDES)
        with self.assertRaisesRegex(icon.BoltError, 'not a directory'):
            icon.title_resources(synthetic_rom(), directory=0, image=IMAGE, palette=PALETTE)
        with self.assertRaisesRegex(icon.BoltError, 'indices'):
            icon.title_resources(synthetic_rom(image=image_payload(b'\x00')), **OVERRIDES)
        with self.assertRaisesRegex(icon.BoltError, 'palette'):
            icon.title_resources(synthetic_rom(palette=b'\x00' * 100), **OVERRIDES)

class OutputTests(unittest.TestCase):
    def test_plate_rounds_corners_and_keeps_margin(self):
        art = Image.new('RGBA', (icon.MASTER_SIZE,) * 2, (10, 20, 30, 255))
        rounded = icon.plate(art, 256)
        self.assertEqual(rounded.getpixel((0, 0))[3], 0)
        self.assertEqual(rounded.getpixel((128, 128)), (10, 20, 30, 255))
        self.assertEqual(icon.plate(art, 256, rounded=False).getpixel((0, 0)), (10, 20, 30, 255))
        inset = icon.plate(art, 256, inset=icon.MACOS_INSET)
        self.assertEqual(inset.getpixel((8, 128))[3], 0)
        self.assertEqual(inset.getpixel((128, 128))[3], 255)

    def test_build_icons_writes_every_format_and_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'icons'
            receipt = icon.build_icons(synthetic_rom(), output, **OVERRIDES)
            sizes = {}
            for name in ('icon-1024.png', 'icon-android.png', 'StarCraft64.png'):
                with Image.open(output / name) as image:
                    sizes[name] = image.size
            self.assertEqual(sizes, {'icon-1024.png': (1024, 1024), 'icon-android.png': (192, 192),
                                     'StarCraft64.png': (256, 256)})
            with Image.open(output / 'StarCraft64.ico') as ico:
                self.assertEqual(sorted(ico.info['sizes']), [(s, s) for s in icon.ICO_SIZES])
            self.assertEqual((output / 'StarCraft64.rc').read_text(), '1 ICON "StarCraft64.ico"\n')
            self.assertTrue(set(icon.FILES) <= set(receipt['files_sha256']))
            self.assertEqual(receipt['image_hash'], f'{icon.TITLE_IMAGE:08X}')
            json.dumps(receipt)

    def test_build_icons_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileExistsError):
                icon.build_icons(synthetic_rom(), Path(temporary), **OVERRIDES)

    def test_installed_falls_back_when_absent(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(icon.installed('StarCraft64.png', Path(temporary)))
            (Path(temporary) / 'StarCraft64.png').write_bytes(b'x')
            self.assertEqual(icon.installed('StarCraft64.png', Path(temporary)), Path(temporary) / 'StarCraft64.png')

if __name__ == '__main__':
    unittest.main()
