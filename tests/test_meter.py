import importlib.util
import math
import pathlib
import base64
import struct
import sys
import unittest

PLUGIN = pathlib.Path(__file__).resolve().parents[1] / 'plugin/org.codex.vuengine.sdPlugin'
sys.path.insert(0, str(PLUGIN))
spec = importlib.util.spec_from_file_location("vu_meter", PLUGIN / "meter.py")
meter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meter)


def decode_svg(encoded):
    return base64.b64decode(encoded, validate=True).decode()


class AudioMeterTests(unittest.TestCase):
    def test_stereo_rms_averages_channels_without_boost(self):
        left = struct.pack("<ff", .4, 0.0)
        right = struct.pack("<ff", 0.0, .4)
        both = struct.pack("<ff", .4, .4)
        self.assertEqual(meter.measure_stereo(left)[2], 1)
        self.assertAlmostEqual(meter.measure_stereo(left)[0], .08, places=6)
        self.assertAlmostEqual(meter.measure_stereo(left)[1], .4, places=6)
        self.assertAlmostEqual(meter.measure_stereo(right)[0], .08, places=6)
        self.assertAlmostEqual(meter.measure_stereo(right)[1], .4, places=6)
        self.assertAlmostEqual(meter.measure_stereo(both)[0], .16, places=6)
        self.assertAlmostEqual(meter.measure_stereo(both)[1], .4, places=6)
        self.assertEqual(meter.measure_stereo(both)[2], 1)
        self.assertAlmostEqual(math.sqrt(.08), .4 / math.sqrt(2))

    def test_mono_silence_partial_and_nonfinite_samples(self):
        mono = struct.pack("<ff", .25, .25)
        self.assertEqual(meter.measure_stereo(mono)[2], 1)
        self.assertAlmostEqual(meter.measure_stereo(mono)[0], .0625, places=6)
        self.assertAlmostEqual(meter.measure_stereo(mono)[1], .25, places=6)
        self.assertEqual(meter.measure_stereo(b"\x00\x00"), (0.0, 0.0, 0))
        raw = struct.pack("<ff", float("nan"), float("inf"))
        self.assertEqual(meter.measure_stereo(raw), (0.0, 0.0, 1))

    def test_attack_peak_hold_decay_and_silence_return(self):
        state = meter.MeterState()
        position, peak = state.advance(.5, .75, 1.0, .1)
        self.assertGreater(position, 0)
        self.assertGreaterEqual(peak, position)
        held = peak
        for tick in range(1, 7):
            _, peak = state.advance(0.0, 0.0, 1.0 + tick * .1, .1)
        self.assertGreaterEqual(peak, held)
        for tick in range(7, 60):
            position, peak = state.advance(0.0, 0.0, 1.0 + tick * .1, .1)
        self.assertEqual(position, 0.0)
        self.assertEqual(peak, 0.0)

    def test_label_escaped_and_single_bar_rendered(self):
        svg_uri = meter.render_svg("A<&", "live", .5, .7)
        svg = decode_svg(svg_uri.split(",", 1)[1])
        self.assertIn("A&lt;&amp;", svg)
        self.assertNotIn("STEREO RMS", svg)
        self.assertNotIn(" dB", svg)
        self.assertIn("43%", decode_svg(
            meter.render_svg("TEST", "live", .5, .7, {"available": True, "volume": .43}).split(",", 1)[1]))
        self.assertIn("MUTED", decode_svg(
            meter.render_svg("TEST", "live", .5, .7, {"available": True, "muted": True}).split(",", 1)[1]))


if __name__ == "__main__":
    unittest.main()
