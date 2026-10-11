"""Private-data boundary and ROM validation of authored tools.

Synthetic fixtures only: ROM images are zero-filled headers whose expected
SHA-1 is patched per test; no retail bytes are read or written.
"""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


private_paths = load('private_paths_under_test', 'tools/private_paths.py')
bolt = load('bolt_extract_under_test', 'tools/bolt_extract.py')
probe = load('sc64_probe_under_test', 'tools/sc64_probe.py')
capture = load('capture_reference_under_test', 'tools/renderer/capture_reference.py')
bootstrap = load('bootstrap_under_test', 'tools/desktop/bootstrap.py')


def synthetic_bolt_rom():
    """Header + a one-file uncompressed BOLT archive; no game data."""
    data = bytearray(0x1100)
    data[:4] = bytes.fromhex('80371240')
    base = 0x1000
    data[base:base + 4] = b'BOLT'
    data[base + 8:base + 11] = bytes((1, 2, 99))
    data[base + 11] = 1
    struct.pack_into('>I', data, base + 12, 0x40)
    # Entry: flags=uncompressed, size=4, offset=0x20 from BOLT, nonzero hash = file.
    data[base + 16] = bolt.FLAG_UNCOMPRESSED
    struct.pack_into('>III', data, base + 20, 4, 0x20, 0x12345678)
    data[base + 0x20:base + 0x24] = b'\x01\x02\x03\x04'
    return bytes(data)


def byteswap16(data):
    return b''.join(data[i:i + 2][::-1] for i in range(0, len(data), 2))


def expect_rom(module, normalized):
    """Scope the expected SHA-1 to the fixture inside the module's rom_info copy."""
    return patch.dict(module.load_ntsc_u.__globals__, NTSC_U_SHA1=hashlib.sha1(normalized).hexdigest())


class RequireLocalTests(unittest.TestCase):
    def test_accepts_new_local_path_and_rejects_escape_or_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / 'local/existing').mkdir(parents=True)
            self.assertEqual(private_paths.require_local(root / 'local/new', new=True, root=root), root / 'local/new')
            for path, kwargs in ((root / 'outside', {}), (root / 'local/../outside', {}),
                                 (root / 'local/existing', {'new': True})):
                with self.subTest(path=path), self.assertRaises(private_paths.PrivatePathError):
                    private_paths.require_local(path, root=root, **kwargs)
            private_paths.require_local(root / 'local/existing', root=root)


class BoltExtractTests(unittest.TestCase):
    def run_main(self, root, *argv):
        stderr = io.StringIO()
        with patch.object(bolt, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(stderr):
            return bolt.main([str(arg) for arg in argv]), stderr.getvalue()

    def test_rejects_output_outside_local_before_reading_rom(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            code, error = self.run_main(root, root / 'missing.z64', root / 'extracted')
            self.assertEqual(code, 2)
            self.assertIn('local/', error)
            self.assertFalse((root / 'extracted').exists())

    def test_rejects_unexpected_rom_identity_without_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            rom = root / 'fixture.z64'
            rom.write_bytes(synthetic_bolt_rom())
            code, error = self.run_main(root, rom, root / 'local/extracted')
            self.assertEqual(code, 2)
            self.assertIn('SHA-1', error)
            self.assertFalse((root / 'local/extracted').exists())

    def test_normalizes_byte_swapped_dump_and_refuses_reuse(self):
        normalized = synthetic_bolt_rom()
        with tempfile.TemporaryDirectory() as temporary, expect_rom(bolt, normalized):
            root = Path(temporary).resolve()
            rom = root / 'fixture.v64'
            rom.write_bytes(byteswap16(normalized))
            output = root / 'local/extracted'
            self.assertEqual(self.run_main(root, rom, output)[0], 0)
            self.assertEqual((output / '12345678.unk').read_bytes(), b'\x01\x02\x03\x04')
            self.assertTrue((output / '_manifest.json').is_file())
            self.assertEqual(self.run_main(root, rom, output)[0], 2)


class ProbeTests(unittest.TestCase):
    def extracted(self, root):
        directory = root / 'local/extracted'
        directory.mkdir(parents=True)
        image = bytearray(16 + 4)
        struct.pack_into('>HH', image, 8, 2, 2)
        (directory / 'a.unkimg').write_bytes(bytes(image))
        (directory / 'a.unkpal').write_bytes(bytes(6 + 512))
        return directory

    def run_main(self, root, *argv):
        stderr = io.StringIO()
        with patch.object(probe, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(stderr):
            return probe.main([str(arg) for arg in argv]), stderr.getvalue()

    def test_png_output_must_stay_under_local(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = self.extracted(root)
            code, error = self.run_main(root, source, '--png', root / 'png')
            self.assertEqual(code, 2)
            self.assertIn('local/', error)
            self.assertFalse((root / 'png').exists())
            self.assertEqual(self.run_main(root, source, '--png', root / 'local/png')[0], 0)
            self.assertTrue((root / 'local/png/sample_image.png').read_bytes().startswith(b'\x89PNG'))

    def test_missing_input_is_an_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(self.run_main(root, root / 'local/none')[0], 2)


class CaptureReferenceTests(unittest.TestCase):
    def prepare(self, root):
        state = root / 'local/captures/research/reference-cold/end.state'
        state.parent.mkdir(parents=True)
        state.write_bytes(b'synthetic checkpoint')

    def run_main(self, root, rom, normalized):
        stderr = io.StringIO()
        with patch.object(capture, 'ROOT', root), expect_rom(capture, normalized), \
             patch.object(capture.subprocess, 'run') as run, contextlib.redirect_stderr(stderr):
            try:
                capture.main(['main-menu', str(root / 'local/out'), '--rom', str(rom)])
            except SystemExit as exit_:
                return exit_.code, stderr.getvalue(), run
            return 0, stderr.getvalue(), run

    def test_validates_normalized_identity_and_requires_runner_z64(self):
        normalized = synthetic_bolt_rom()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.prepare(root)
            z64, v64 = root / 'fixture.z64', root / 'fixture.v64'
            z64.write_bytes(normalized)
            v64.write_bytes(byteswap16(normalized))
            code, error, run = self.run_main(root, v64, normalized)
            self.assertEqual(code, 2)
            self.assertIn('--normalized-out', error)
            run.assert_not_called()
            code, error, run = self.run_main(root, z64, normalized + b'\0\0\0\0')
            self.assertEqual(code, 2)
            self.assertIn('SHA-1', error)
            run.assert_not_called()
            code, _, run = self.run_main(root, z64, normalized)
            self.assertEqual(code, 0)
            self.assertIn(str(z64), run.call_args.args[0])

    def test_output_must_be_new_and_local(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(capture, 'ROOT', root), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    capture.main(['main-menu', str(root / 'out')])


class BootstrapExtractionTests(unittest.TestCase):
    def archive(self, root, extra=None):
        path = root / 'sdl.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, data in (('SDL3-x/include/a.h', b'first'), ('SDL3-x/include/b.h', b'second')):
                info = tarfile.TarInfo(name); info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            if extra: archive.addfile(extra)
        return path

    def test_interrupted_extraction_leaves_no_partial_file_and_resumes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive, output = self.archive(root), root / 'cache/SDL3-x'
            real_replace = bootstrap.os.replace
            def fail_second(source, target):
                if Path(target).name == 'b.h':
                    raise OSError('synthetic interruption')
                real_replace(source, target)
            with patch.object(bootstrap.os, 'replace', side_effect=fail_second):
                with self.assertRaises(OSError):
                    bootstrap.extract_sdl(archive, output)
            include = output / 'include'
            self.assertEqual(sorted(p.name for p in include.iterdir()), ['a.h'])
            bootstrap.extract_sdl(archive, output)
            self.assertEqual((include / 'b.h').read_bytes(), b'second')

    def test_existing_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive, output = self.archive(root), root / 'cache/SDL3-x'
            target = output / 'include/a.h'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'edited')
            with self.assertRaisesRegex(ValueError, 'drift'):
                bootstrap.extract_sdl(archive, output)

    def test_links_and_escaping_members_are_rejected(self):
        link = tarfile.TarInfo('SDL3-x/include/link.h'); link.type = tarfile.SYMTYPE; link.linkname = '/etc/hosts'
        escape = tarfile.TarInfo('SDL3-x/../outside.h'); escape.size = 0
        for member, message in ((link, 'regular file'), (escape, 'escapes')):
            with self.subTest(member=member.name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                with self.assertRaisesRegex(ValueError, message):
                    bootstrap.extract_sdl(self.archive(root, member), root / 'cache/SDL3-x')
                self.assertFalse((root / 'cache/outside.h').exists())

if __name__ == '__main__':
    unittest.main()
