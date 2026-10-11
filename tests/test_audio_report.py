import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audio_report', ROOT / 'tools/android/audio_report.py')
audio_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio_report)


class AudioReportTests(unittest.TestCase):
    def setUp(self):
        self.a = dict(host_seconds=10, fields=600, running=True, paused=False,
            ui_mode='menu', audio_source_hz=11025, audio_backend='AAudio',
            audio_source_frames=1000, audio_source_nonzero_frames=900,
            audio_played_frames=10000, audio_nonzero_frames=9000,
            audio_underruns=1, audio_dropped_frames=0, audio_device_xruns=2)
        self.b = dict(self.a, host_seconds=15, fields=900,
            audio_source_frames=56125, audio_source_nonzero_frames=56025,
            audio_played_frames=250000, audio_nonzero_frames=249000,
            audio_device_xruns=3, audio_source_gap_ms=90, audio_callback_gap_ms=11,
            audio_callback_work_ms=.5)

    def test_source_and_output_rates_use_distinct_frame_units(self):
        w = audio_report.analyze([self.a, self.b])['windows'][0]
        self.assertEqual(w['source_frames_per_second'], 11025)
        self.assertEqual(w['output_played_frames_per_second'], 48000)
        self.assertEqual(w['source_silence_fraction'], 0)
        self.assertEqual(w['played_output_silence_fraction'], 0)
        self.assertEqual(w['starvations'], 0)
        self.assertEqual(w['hardware_xruns'], 1)
        self.assertEqual(w['source_gap_ms'], 90)

    def test_unsupported_and_legacy_counters_remain_unknown(self):
        a, b = dict(self.a, audio_device_xruns=-1), dict(self.b, audio_device_xruns=-1)
        a.pop('audio_source_frames'); b.pop('audio_source_frames')
        w = audio_report.analyze([a, b])['windows'][0]
        self.assertIsNone(w['hardware_xruns'])
        self.assertIsNone(w['source_frames_per_second'])

    def test_paused_and_frozen_capture_is_not_accepted(self):
        for b in (self.a, dict(self.b, paused=True), dict(self.b, running=False)):
            with self.assertRaises(ValueError): audio_report.analyze([self.a, b])

    def test_mode_and_rate_changes_are_marked(self):
        w = audio_report.analyze([self.a, dict(self.b, ui_mode='game', audio_source_hz=22050)])['windows'][0]
        self.assertFalse(w['same_mode']); self.assertFalse(w['same_rate'])
        self.assertIsNone(w['source_frames_per_second'])

    def test_reset_counter_is_not_a_negative_event(self):
        w = audio_report.analyze([self.a, dict(self.b, audio_underruns=0)])['windows'][0]
        self.assertIsNone(w['starvations'])

    def test_android_prefix_and_truncation(self):
        log = 'noise\n10-08 00:00:00  123  456 I SC64    : SC64 ' + json.dumps(self.a) + '\n'
        self.assertEqual(audio_report.samples(log), [self.a])
        with self.assertRaises(ValueError): audio_report.samples('SC64 {"truncated"')


if __name__ == '__main__': unittest.main()
