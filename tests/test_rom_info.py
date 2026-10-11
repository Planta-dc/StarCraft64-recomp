"""Synthetic fixtures only: no ROM, bootcode or game-derived code in tests."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.rom_info import RomError, analyze_rom, find_microcode_identifiers, main, normalize_rom


def synthetic_rom(size=0x1100):
    data = bytearray(size)
    data[:4] = bytes.fromhex("80371240")
    struct.pack_into(">I", data, 8, 0x80000400)
    data[0x20:0x34] = b"SYNTHETIC FIXTURE".ljust(20, b" ")
    data[0x3C:0x40] = b"TSE\x02"
    data[0x1000:0x1008] = bytes.fromhex("0123456789abcdef")
    return bytes(data)


def reorder(data, width):
    # Deliberately simple reference independent of the tool's lane slicing.
    return b"".join(data[i:i + width][::-1] for i in range(0, len(data), width))


class RomInfoTests(unittest.TestCase):
    def test_normalize_all_three_formats_and_hashes(self):
        original = synthetic_rom()
        for fmt, raw in (("z64", original), ("v64", reorder(original, 2)), ("n64", reorder(original, 4))):
            with self.subTest(fmt=fmt):
                report, data = analyze_rom(raw)
                self.assertEqual(data, original)
                self.assertEqual(report["input"]["format"], fmt)
                self.assertEqual(report["input"]["sha1"], hashlib.sha1(raw).hexdigest())
                self.assertEqual(report["normalized"]["sha1"], hashlib.sha1(original).hexdigest())
                self.assertEqual(report["header"]["entrypoint_raw"], "0x80000400")
                self.assertEqual(report["header"]["revision_byte"], 2)
                self.assertEqual(report["header"]["cartridge_id"], "TS")
                self.assertEqual(report["header"]["region"], "USA")

    def test_malformed_inputs_are_rejected(self):
        for data in (b"", b"x" * 63, b"x" * 4096, synthetic_rom()[:-1], b"x" * 512 + synthetic_rom()):
            with self.subTest(length=len(data)):
                with self.assertRaises(RomError):
                    normalize_rom(data)

    def test_incomplete_and_unknown_ipl3_remain_unknown(self):
        for raw in (synthetic_rom()[:0x40], synthetic_rom()):
            report, _ = analyze_rom(raw)
            self.assertEqual(report["cic"]["status"], "unknown")
            self.assertIsNone(report["cic"]["family"])
            self.assertIsNone(report["unresolved"]["save_type"])

    def test_unknown_region_and_non_ascii_title(self):
        raw = bytearray(synthetic_rom())
        raw[0x3E] = 0xFF
        raw[0x20] = 0xFF
        report, _ = analyze_rom(bytes(raw))
        self.assertEqual(report["header"]["region"], "Unknown")
        self.assertIsNone(report["header"]["video_standard_hint"])
        json.dumps(report)

    def test_identifier_offsets_are_normalized(self):
        raw = bytearray(synthetic_rom())
        banner = b"RSP Gfx ucode S2DEX xbus 2.08\0"
        raw[0x1040:0x1040 + len(banner)] = banner
        for width in (2, 4):
            report, _ = analyze_rom(reorder(bytes(raw), width))
            candidates = report["microcode"]["candidates"]
            self.assertEqual(candidates[0]["offset"], 0x1040)
            self.assertIsNone(report["microcode"]["active_gbi"])
            self.assertTrue(all(c["status"] == "candidate_string_only" for c in candidates))

    def test_identifier_bounds_limit_and_false_positive_boundaries(self):
        result = find_microcode_identifiers(b"RSP Gfx " + b"x" * 10000 + b"\0S2DEX\0F3DEX2\0", 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["match_count"], 3)
        self.assertLessEqual(len(result["candidates"][0]["text"]), 160)
        self.assertEqual(find_microcode_identifiers(b"AF3DD\0f3d3\0")['match_count'], 0)

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(a) for a in args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_writes_valid_json_and_new_normalized_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output, normalized = (Path(tmp) / n for n in ("wrong.z64", "report.json", "canonical.z64"))
            raw = reorder(synthetic_rom(), 2)
            source.write_bytes(raw)
            code, out, err = self.invoke([source, "--output", output, "--normalized-out", normalized])
            self.assertEqual((code, out, err), (0, "", ""))
            self.assertEqual(json.loads(output.read_text())["input"]["format"], "v64")
            self.assertEqual(normalized.read_bytes(), synthetic_rom())
            self.assertEqual(source.read_bytes(), raw)

    def test_cli_refuses_overwriting_input_and_existing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "fixture.z64", Path(tmp) / "report.json"
            source.write_bytes(synthetic_rom())
            output.write_bytes(b"keep me")
            for args in ([source, "--output", source], [source, "--normalized-out", source], [source, "--output", output]):
                self.assertEqual(self.invoke(args)[0], 2)
            self.assertEqual(output.read_bytes(), b"keep me")
            self.assertEqual(source.read_bytes(), synthetic_rom())

    def test_cli_rejects_same_output_path_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output, alias = (Path(tmp) / n for n in ("fixture.z64", "output", "alias"))
            source.write_bytes(synthetic_rom())
            self.assertEqual(self.invoke([source, "--output", output, "--normalized-out", output])[0], 2)
            self.assertFalse(output.exists())
            alias.symlink_to(source)
            self.assertEqual(self.invoke([source, "--normalized-out", alias])[0], 2)
            self.assertEqual(source.read_bytes(), synthetic_rom())

    def test_cli_hash_validation_is_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "fixture.z64", Path(tmp) / "output.json"
            source.write_bytes(synthetic_rom())
            self.assertEqual(self.invoke([source, "--expect-sha1", "0" * 40, "--output", output])[0], 2)
            self.assertFalse(output.exists())
            digest = hashlib.sha1(synthetic_rom()).hexdigest().upper()
            code, out, err = self.invoke([source, "--expect-sha1", digest])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["normalized"]["sha1"], digest.lower())

    def test_cli_missing_input_bad_hash_and_bad_limit(self):
        for args in (["/no/such/sc64-fixture"], ["unused", "--expect-sha1", "bad"], ["unused", "--max-identifiers", 0]):
            code, out, err = self.invoke(args)
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertTrue(err.startswith("rom_info: "))


if __name__ == "__main__":
    unittest.main()
