"""Acceptance rejects interrupted or inactive runs even with plausible duration."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/recompile"))
SPEC = importlib.util.spec_from_file_location("native_acceptance", ROOT / "tools/recompile/check_acceptance.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.result = dict(report=dict(clean_shutdown=True, rom_sha1=MODULE.ROM_SHA1,
            elapsed_seconds=600.03, fields=36000, tasks=30000, completed_tasks=30000,
            audio_samples=13230000), completed_sequence_valid=True,
            audio=[dict(rate=11025, nonzero_bytes=123)], event_counts={})

    def test_interrupted_run_cannot_use_duration_alone(self):
        self.result["report"] = None
        with self.assertRaisesRegex(ValueError, "join"):
            MODULE.check_stability(self.result)

    def test_short_smoke_run_is_not_stability(self):
        self.result["report"]["elapsed_seconds"] = 60
        with self.assertRaisesRegex(ValueError, "600"):
            MODULE.check_stability(self.result)

    def test_dropped_last_task_is_rejected(self):
        self.result["completed_sequence_valid"] = False
        with self.assertRaisesRegex(ValueError, "sequence"):
            MODULE.check_stability(self.result)

    def test_no_game_or_audio_progress_is_rejected(self):
        self.result["report"]["audio_samples"] = 8
        with self.assertRaisesRegex(ValueError, "insufficient"):
            MODULE.check_stability(self.result)

    def test_nonzero_pcm_required(self):
        self.result["audio"][0]["nonzero_bytes"] = 0
        with self.assertRaisesRegex(ValueError, "PCM"):
            MODULE.check_stability(self.result)


if __name__ == "__main__":
    unittest.main()
