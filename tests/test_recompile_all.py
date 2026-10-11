import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sc64_recompile_all', ROOT / 'tools/recompile/recompile_all.py')
pipeline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pipeline
spec.loader.exec_module(pipeline)


class InputCheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.directory))
        self.rom = self.directory / 'rom.z64'
        self.inventory = self.directory / 'inventory.json'

    def test_missing_rom_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, 'ROM not found'):
            pipeline.check_inputs(self.rom, self.inventory)

    def test_wrong_rom_is_rejected_before_anything_else(self):
        self.rom.write_bytes(b'not the game')
        with self.assertRaisesRegex(SystemExit, 'Unsupported ROM'):
            pipeline.check_inputs(self.rom, self.inventory)

    def test_missing_and_foreign_inventory_are_rejected(self):
        self.rom.write_bytes(b'synthetic')
        original = pipeline.ROM_SHA1
        pipeline.ROM_SHA1 = pipeline.sha1_file(self.rom)
        self.addCleanup(setattr, pipeline, 'ROM_SHA1', original)
        with self.assertRaisesRegex(SystemExit, 'inventory is a prepared input'):
            pipeline.check_inputs(self.rom, self.inventory)
        self.inventory.write_text(json.dumps({'rom_sha1': '0' * 40}))
        with self.assertRaisesRegex(SystemExit, 'different ROM'):
            pipeline.check_inputs(self.rom, self.inventory)

    def test_output_outside_local_is_rejected(self):
        sys.argv = ['recompile_all.py', str(self.rom), '--output', str(self.directory / 'game')]
        with self.assertRaisesRegex(SystemExit, 'ignored local/'):
            pipeline.main()


if __name__ == '__main__':
    unittest.main()
