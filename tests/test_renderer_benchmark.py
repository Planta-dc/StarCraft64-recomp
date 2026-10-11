import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools/renderer'
spec = importlib.util.spec_from_file_location('renderer_benchmark', TOOLS / 'benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(TOOLS))
try:
    spec.loader.exec_module(benchmark)
finally:
    sys.path.pop(0)


class RendererBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(schema=1, rectangles=2, textures=1, written_pixels=4,
            opcodes={'10': 2}, batches=1, targets=[{'address': 4096}],
            texture_keys=['18446744073709551615'], interpret_ms=[10, 12, 11])
        self.after = dict(self.before, interpret_ms=[6, 4, 5])

    def test_median_ignores_outlier_and_requires_full_ram_match(self):
        result = benchmark.compare_runs(self.before, self.after, 'abc', 'abc')
        self.assertTrue(result['equivalent'])
        self.assertEqual(result['baseline_median_ms'], 11)
        self.assertEqual(result['candidate_median_ms'], 5)
        self.assertFalse(benchmark.compare_runs(self.before, self.after, 'abc', 'def')['equivalent'])

    def test_pixels_alone_do_not_certify_texture_identity_or_commands(self):
        for key, value in [('texture_keys', ['1']), ('written_pixels', 5), ('opcodes', {'10': 1})]:
            with self.subTest(key=key):
                self.assertFalse(benchmark.compare_runs(self.before, dict(self.after, **{key: value}),
                    'abc', 'abc')['equivalent'])

    def test_rejects_missing_nonfinite_and_unpaired_timings(self):
        missing = dict(self.after); missing.pop('texture_keys')
        for report in (missing, dict(self.after, interpret_ms=[]),
                       dict(self.after, interpret_ms=[float('nan')]),
                       dict(self.after, interpret_ms=[float('inf')]),
                       dict(self.after, interpret_ms=[0, 0, 0]),
                       dict(self.after, interpret_ms=[1])):
            with self.assertRaises(ValueError):
                benchmark.compare_runs(self.before, report, 'abc', 'abc')

    def test_raster_stage_ignores_worker_configuration(self):
        before = dict(self.before, software_ms=[8, 9, 10], raster_helpers=0)
        after = dict(self.after, software_ms=[3, 4, 5], raster_helpers=3)
        result = benchmark.compare_runs(before, after, 'abc', 'abc', 'software_ms')
        self.assertTrue(result['equivalent'])
        self.assertEqual(result['candidate_median_ms'], 4)
        with self.assertRaises(ValueError):
            benchmark.compare_runs(self.before, after, 'abc', 'abc', 'software_ms')
