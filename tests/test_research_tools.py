"""Synthetic malformed-input and fragmented-command regressions; no ROM data."""
import struct
import unittest

from tools.research.bolt_audit import AuditError, audit, decode
from tools.research.summarize_capture import RdpStream, traverse_gbi


class BoltTests(unittest.TestCase):
    def test_overlapping_copy(self):
        self.assertEqual(decode(b'\x80A\x10', 0, 3, 4), (b'AAAA', 3))

    def test_literal_extension(self):
        data = b'\xa1\x80' + b'abcdefghijklmnopq'
        self.assertEqual(decode(data, 0, len(data), 17), (data[2:], len(data)))

    def test_truncation_and_invalid_history(self):
        for data, size in [(b'\x82a', 3), (b'\x00', 2), (b'\xc1', 8), (b'\x80A\x1f', 4)]:
            with self.subTest(data=data), self.assertRaises(AuditError):
                decode(data, 0, len(data), size)

    def test_output_overrun(self):
        with self.assertRaises(AuditError):
            decode(b'\x82abc', 0, 4, 2)

    def test_raw_archive_and_directory_bounds(self):
        header = b'BOLT' + bytes(7) + b'\x01' + bytes(4)
        entry = struct.pack('>4B3I', 8, 0, 0, 2, 3, 32, 1)
        result = audit(header + entry + b'abc', 0)
        self.assertEqual(result['leaf_count'], 1)
        self.assertEqual(result['decoded_bytes'], 3)
        with self.assertRaises(AuditError):
            audit(header + entry + b'ab', 0)

    def test_directory_cycle(self):
        header = b'BOLT' + bytes(7) + b'\x01' + bytes(4)
        entry = struct.pack('>4B3I', 0, 0, 0, 1, 16, 16, 0)
        with self.assertRaises(AuditError):
            audit(header + entry, 0)


class CommandTests(unittest.TestCase):
    def test_texrect_split_does_not_consume_following_sync(self):
        stream = RdpStream()
        self.assertEqual(stream.feed(['e400000000000000']), [])
        commands = stream.feed(['ff00000000000000', 'e900000000000000'])
        self.assertEqual([opcode for opcode, _ in commands], [0x24, 0x29])
        self.assertEqual(len(commands[0][1]), 2)
        self.assertEqual(stream.pending, [])

    def test_triangle_fragment_payload_is_not_a_command(self):
        stream = RdpStream()
        words = [0x0F00000000000000] + [0xFF00000000000000] * 21
        commands = []
        for word in words + [0x2900000000000000]:
            commands.extend(stream.feed([word]))
        self.assertEqual([opcode for opcode, _ in commands], [0x0F, 0x29])

    def test_gbi_push_and_branch(self):
        ram = bytearray(40)
        struct.pack_into('>II', ram, 0, 0xDE000000, 0x80000010)
        struct.pack_into('>II', ram, 8, 0xDF000000, 0)
        struct.pack_into('>II', ram, 16, 0xDE010000, 0x80000020)
        struct.pack_into('>II', ram, 32, 0xDF000000, 0)
        self.assertEqual(traverse_gbi(bytes(ram), 0)['commands'], 4)

    def test_gbi_cycle_and_out_of_range_are_rejected(self):
        for low in [0x80000000, 0x807FFFF8]:
            ram = struct.pack('>II', 0xDE010000, low)
            with self.subTest(low=low), self.assertRaises(ValueError):
                traverse_gbi(ram, 0)


if __name__ == '__main__':
    unittest.main()
