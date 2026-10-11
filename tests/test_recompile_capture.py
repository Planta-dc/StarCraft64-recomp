"""Synthetic snapshot integrity tests; these do not establish game behavior."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json

SOURCE = Path(__file__).resolve().parents[1] / "tools/recompile/inspect_capture.py"
SPEC = importlib.util.spec_from_file_location("inspect_capture", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pages").mkdir()
        page = bytes(4096)
        self.key = hashlib.sha256(page).hexdigest()
        (self.root / "pages" / (self.key + ".bin")).write_bytes(page)
        self.event = dict(rdram_size=0x800000, page_size=4096, pages=[self.key] * 2048,
                          rdram_sha256=hashlib.sha256(bytes(0x800000)).hexdigest())

    def test_complete_snapshot(self):
        verified = set()
        self.assertEqual(len(MODULE.reconstruct(self.root, self.event, verified)), 0x800000)
        self.assertEqual(verified, {self.key})

    def test_corruption_fails_before_decoding(self):
        (self.root / "pages" / (self.key + ".bin")).write_bytes(b"x" * 4096)
        with self.assertRaisesRegex(ValueError, "content"):
            MODULE.reconstruct(self.root, self.event, set())

    def test_reordered_snapshot_digest(self):
        page = b"x" * 4096
        key = hashlib.sha256(page).hexdigest()
        (self.root / "pages" / (key + ".bin")).write_bytes(page)
        self.event["pages"][1] = key
        with self.assertRaisesRegex(ValueError, "Complete RAM"):
            MODULE.reconstruct(self.root, self.event, set())

    def test_path_traversal_rejected(self):
        self.event["pages"][0] = "../" + "a" * 61
        with self.assertRaisesRegex(ValueError, "digest"):
            MODULE.reconstruct(self.root, self.event, set())

    def test_sampled_run_keeps_final_packet_and_total_sequence(self):
        events = []
        data = bytes(8)
        words = [0] * 16
        words[0], words[5], words[13] = 1, 4096, 8
        ucode = hashlib.sha1(bytes(4096)).hexdigest()
        for number in range(1, 11):
            (self.root / f"task-{number}.dl.bin").write_bytes(data)
            events.append(dict(kind="sp_task", task=number, field=number, descriptor=words,
                               ucode_sha1=ucode, dl_sha256=hashlib.sha256(data).hexdigest()))
            events.append(dict(kind="task_completed", sequence=number))
        (self.root / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
        with patch.object(MODULE, "reconstruct", return_value=bytes(8192)) as snapshots, \
             patch.object(MODULE, "traverse_gbi", return_value=dict(commands=1, histogram={}, objects=[])), \
             patch.object(MODULE, "UCODE_SHA1", ucode):
            result = MODULE.inspect(self.root, stride=4)
        self.assertEqual([row["task"] for row in result["lists"]], [1, 5, 9, 10])
        self.assertEqual(snapshots.call_count, 4)
        self.assertEqual(result["submitted_tasks"], 10)
        self.assertTrue(result["completed_sequence_valid"])


if __name__ == "__main__":
    unittest.main()
