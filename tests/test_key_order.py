import pathlib
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'plugin/org.codex.vuengine.sdPlugin'))
import meter


class KeyOrderTests(unittest.TestCase):
    def test_shared_target_preserves_key_order_and_discards_hidden_work(self):
        target = "pwctl.source.psou-example-personal"
        first, release = threading.Event(), threading.Event()
        ordered = []

        def apply(name, action, settings):
            self.assertEqual(name, target)
            ordered.append(action)
            first.set()
            self.assertTrue(release.wait(2))
            return {"available": True, "volume": .5, "muted": False}

        with patch.object(meter, "NodeRegistry"), patch.object(meter, "log"):
            manager = meter.CaptureManager()
            try:
                manager.control = Mock()
                manager.control.apply.side_effect = apply
                manager._redraw_context = Mock()
                for key, action, enabled in [
                    ("up", "volume_up", True), ("minus", "volume_down", True),
                    ("mute", "mute_toggle", False), ("gone", "volume_down", True),
                    ("legacy", "volume_up", False),
                ]:
                    manager.instances[key] = {"control_target": target, "control_action": action,
                                              "unmute_on_volume_change": enabled}
                with patch.object(meter.time, "monotonic", return_value=100):
                    manager.handle_key_down("up")
                    self.assertTrue(first.wait(2))
                    for key in ["up", "minus", "mute", "mute", "gone", "legacy", "legacy"]:
                        manager.handle_key_down(key)
                    manager.remove("gone")
                    with manager.lock:
                        workers = list(manager.control_workers)
                    self.assertEqual(len(workers), 1)
                    release.set()
                    workers[0].join(2)
                self.assertEqual(ordered, ["volume_up", "volume_up", "volume_down", "mute_toggle", "volume_up"])
                self.assertFalse(manager.pending_controls)
                self.assertFalse(manager.control_workers)
            finally:
                release.set()
                manager.close()
