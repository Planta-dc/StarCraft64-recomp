import csv
import importlib.util
import os
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path


def module(name):
    path = Path(__file__).resolve().parents[1] / "tools/recompile" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


symbols = module("splat_to_syms")
recompiler = module("run_recompiler")
polls = module("discover_polls")


class SectionSymbols(unittest.TestCase):
    def write_csv(self, directory, **overrides):
        row = {"vrom": "0x1000", "address": "0x80100000", "name": "func_80100000", "length": "0x20"}
        row.update(overrides)
        path = directory / "funcs.csv"
        with path.open("w", newline="") as output:
            writer = csv.DictWriter(output, list(row))
            writer.writeheader()
            writer.writerow(row)
        return path

    def test_overlay_names_do_not_alias(self):
        sections = []
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_csv(Path(tmp))
            for name in ("menu", "game"):
                section = {"name": name, "rom": 0x1000, "vram": 0x80100000, "size": 0x100}
                section["functions"] = symbols.read_functions(path, section, {})
                sections.append(section)
        result = symbols.render_sections(sections)
        self.assertIn("sc64_menu_80100000", result)
        self.assertIn("sc64_game_80100000", result)
        self.assertEqual(result.count("[[section]]"), 2)

    def test_wrong_overlay_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_csv(Path(tmp))
            section = {"name": "menu", "rom": 0x2000, "vram": 0x80100000, "size": 0x100}
            with self.assertRaisesRegex(ValueError, "mapping"):
                symbols.read_functions(path, section, {})

    def test_unknown_data_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_csv(Path(tmp), name="T_80100000")
            section = {"name": "menu", "rom": 0x1000, "vram": 0x80100000, "size": 0x100}
            with self.assertRaisesRegex(ValueError, "Unclassified"):
                symbols.read_functions(path, section, {})

    def test_function_must_stay_in_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_csv(Path(tmp), length="0x104")
            section = {"name": "menu", "rom": 0x1000, "vram": 0x80100000, "size": 0x100}
            with self.assertRaisesRegex(ValueError, "escapes"):
                symbols.read_functions(path, section, {})

    def test_names_must_be_unique(self):
        sections = [{"name": name, "rom": 0x1000, "vram": 0x80000000, "size": 4,
                     "functions": [{"name": "collision", "vram": 0x80000000, "size": 4}]}
                    for name in ("menu", "game")]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            symbols.render_sections(sections)

    def test_zero_exit_diagnostic_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Unhandled"):
                recompiler.inspect_output(Path(tmp), "Unhandled instruction: cache\n")

    def test_partial_output_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "funcs.h").write_text("header\n")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                recompiler.inspect_output(directory, "Function count: 1\n")

    @unittest.skipIf(os.name == "nt", "Executable helper uses the POSIX shebang")
    def test_late_zero_exit_failure_preserves_previous_output(self):
        root = Path(__file__).resolve().parents[1]
        (root / "local").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root / "local") as tmp:
            directory = Path(tmp)
            output = directory / "published"
            output.mkdir()
            previous = output / "previous.c"
            previous.write_text("previous valid output\n")
            config = directory / "config.toml"
            config.write_text('output_func_path = "ignored"\n')
            fake = directory / "failed-recompiler"
            fake.write_text("#!/usr/bin/env python3\nimport json, pathlib, sys\n"
                            "text = pathlib.Path(sys.argv[1]).read_text()\n"
                            "out = pathlib.Path(json.loads(text.split('=', 1)[1].strip()))\n"
                            "out.mkdir()\n(out / 'funcs_0.c').write_text('partial source')\n"
                            "print('Unhandled instruction: deliberately invalid fixture')\n")
            fake.chmod(0o755)
            result = subprocess.run([sys.executable, str(root / "tools/recompile/run_recompiler.py"),
                                     str(config), "--recompiler", str(fake), "--output", str(output), "--replace"],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unhandled", result.stderr)
            self.assertEqual(previous.read_text(), "previous valid output\n")
            self.assertEqual(list(output.iterdir()), [previous])

    def loop_fixture(self, words):
        rom = struct.pack(">" + "I" * len(words), *words)
        sections = [{"name": "resident", "rom": 0, "vram": 0x80000400, "size": len(rom),
                     "functions": [{"name": "fixture", "vram": 0x80000400, "size": len(rom)}]}]
        return polls.find_memory_waits(rom, sections, set())

    def test_static_memory_wait_requires_poll(self):
        result = self.loop_fixture([0x8EC20000, 0x1082FFFE, 0])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["vram"], 0x80000400)

    def test_linked_list_walk_is_not_memory_wait(self):
        self.assertEqual(self.loop_fixture([0x8C630000, 0x1460FFFE, 0]), [])

    def test_delay_slot_pointer_progress_is_not_memory_wait(self):
        self.assertEqual(self.loop_fixture([0x92020000, 0x1440FFFE, 0x26100001]), [])

    def test_delay_slot_comparison_progress_is_not_memory_wait(self):
        self.assertEqual(self.loop_fixture([0x8EC20000, 0x1082FFFE, 0x24840001]), [])


if __name__ == "__main__":
    unittest.main()
