import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    path = ROOT/'tools/renderer'/f'{name}.py'
    spec = importlib.util.spec_from_file_location(f'renderer_{name}', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class MetricsTests(unittest.TestCase):
    def test_frozen_full_rgb_metric(self):
        compare = module('compare')
        self.assertTrue(compare.metric(b'\x00\x80\xff', b'\x00\x80\xff')['exact'])
        result = compare.metric(bytes([0]*3), bytes([255]*3))
        self.assertEqual(result['psnr_db'], 0)
        self.assertEqual(result['max_error'], 255)
        self.assertFalse(result['exact'])
        with self.assertRaises(ValueError):
            compare.metric(b'12', b'1')

    def test_guest_rgba5551_channel_expansion(self):
        compare = module('compare')
        target = dict(address=2, width=2, height=1, format=0, size=2)
        actual = compare.pixels(bytes.fromhex('0000 f801 07c1'), target)
        self.assertEqual(actual, bytes([255,0,0,0,255,0]))
        target['height'] = 2
        with self.assertRaises(ValueError):
            compare.pixels(bytes.fromhex('0000 f801 07c1'), target)


class OutputBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'local').mkdir(exist_ok=True)

    def test_manifest_rejected_before_any_process_or_output(self):
        compare = module('compare')
        with tempfile.TemporaryDirectory(dir=ROOT/'local') as directory:
            base = Path(directory)
            manifest = base/'manifest.json'
            for case_id in ('../escape', '/private/tmp/escape', r'C:\escape',
                            'a/b', r'a\b', '.', '..', '', None, 42):
                with self.subTest(case_id=case_id):
                    manifest.write_text(json.dumps(dict(schema=1, threshold_rgb_psnr_db=40,
                        cases=[dict(id='valid-first-case'), dict(id=case_id)])))
                    output = base/'result'
                    with patch.object(sys, 'argv', ['compare.py', str(manifest), str(output)]), \
                         patch.object(compare.subprocess, 'run') as run:
                        with self.assertRaisesRegex(ValueError, 'Case ID'):
                            compare.main()
                        run.assert_not_called()
                    self.assertFalse(output.exists())

    def test_duplicate_ids_rejected_before_any_process(self):
        compare = module('compare')
        with tempfile.TemporaryDirectory(dir=ROOT/'local') as directory:
            base = Path(directory)
            manifest = base/'manifest.json'
            manifest.write_text(json.dumps(dict(schema=1, threshold_rgb_psnr_db=40,
                cases=[dict(id='same'), dict(id='same')])))
            with patch.object(sys, 'argv', ['compare.py', str(manifest), str(base/'result')]), \
                 patch.object(compare.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Duplicate'):
                    compare.main()
                run.assert_not_called()
            self.assertFalse((base/'result').exists())

    def test_symlink_destinations_cannot_escape(self):
        compare = module('compare')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base/'result'
            output.mkdir()
            outside = base/'outside'
            outside.mkdir()
            for name in ('scene-1', 'scene-1.oracle.ram'):
                with self.subTest(name=name):
                    link = output/name
                    link.symlink_to(outside)
                    with self.assertRaisesRegex(ValueError, 'escapes'):
                        compare.case_paths(output, 'scene-1')
                    link.unlink()


if __name__ == '__main__':
    unittest.main()
