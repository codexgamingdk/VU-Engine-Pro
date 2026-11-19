import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(next((Path(__file__).resolve().parents[1] / "plugin").glob("*.sdPlugin"))))
from control import command, identity, ControlError, PipeWireControl
from meter import NodeRegistry
import json


class Permissions(unittest.TestCase):
    def setUp(self):
        self.node = dict(node_name="example.channel", media_class="Audio/Sink", eligible=True,
                         cookie=42, id=8, serial=937, display_state={"volume": .5})
        self.reg = Mock()
        self.reg.refresh.return_value = {"example.channel": self.node}
        self.reg.find.return_value = self.node
        self.ctrl = PipeWireControl(self.reg)
        temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temp.cleanup)
        self.ctrl.directory = Path(temp.name)/"state"
        self.ctrl._call = Mock()
        self.settings = {"_local_context": "key", "approved": True}
        self.ctrl.bind("key", self.settings)
        self.name = self.node["node_name"]

    def approve(self):
        self.ctrl.approve("key", self.name, identity(self.node))
        self.ctrl._call.reset_mock()

    def write(self):
        self.ctrl.apply(self.name, "mute_toggle", self.settings)

    def denied(self):
        with self.assertRaises(ControlError):
            self.write()
        self.ctrl._call.assert_not_called()

    def test_import_and_revoke(self):
        self.denied()
        self.approve()
        self.write()
        self.ctrl._call.assert_called_once_with(identity(self.node), "mute_toggle", 0, False)
        self.ctrl.revoke("key")
        self.ctrl._call.reset_mock()
        self.denied()

    def test_reused_id_and_changed_server(self):
        for key in ("id", "serial", "cookie"):
            self.approve()
            self.node[key] += 1
            self.denied()

    def test_missing_and_wrong_context(self):
        self.approve()
        self.settings["_local_context"] = "other"
        self.denied()
        self.settings["_local_context"] = "key"
        self.reg.refresh.return_value = {}
        self.denied()

    def test_changed_since_dialog(self):
        old = identity(self.node)
        self.node["serial"] += 1
        with self.assertRaises(ControlError):
            self.ctrl.approve("key", self.name, old)
        self.ctrl._call.assert_not_called()

    def test_restart_binding_and_corruption(self):
        config = {"control_target":self.name, "control_action":"mute_toggle"}
        self.ctrl.bind("key", config)
        self.approve()
        other = PipeWireControl(self.reg)
        other.directory = self.ctrl.directory
        other.bind("key", dict(config, label="New label"))
        self.assertTrue(other.approved("key", self.node))
        other.bind("key", dict(config, control_action="reset_volume"))
        self.assertFalse(other.approved("key", self.node))
        other.bind("imported", config)
        self.assertFalse(other.approved("imported", self.node))
        file = other.directory/"approvals.json"
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        file.write_text("{")
        other.bind("key", config)
        self.assertFalse(other.approved("key", self.node))

    def test_runtime(self):
        self.assertEqual(command(lambda s:s, False), ["wpexec"])
        self.assertEqual(command(lambda s:s, True), ["flatpak-spawn","--host","wpexec"])
        self.assertEqual(command(lambda s:None, True), [])

    def test_discovery(self):
        props = {"node.name":self.name, "media.class":"Audio/Sink", "node.virtual":True,
                 "object.serial":17, "vuengine.control.role":"channel"}
        node = {"id":8, "type":"PipeWire:Interface:Node", "info":{"props":props,
                "params":{"Props":[{"channelVolumes":[.1,.1], "mute":False}]}}}
        objects = [{"type":"PipeWire:Interface:Core", "info":{"cookie":42}}, node]
        def scan():
            with patch("meter.subprocess.run", return_value=Mock(stdout=json.dumps(objects))):
                return NodeRegistry._scan(None)
        self.assertTrue(scan()[self.name]["eligible"])
        props.pop("vuengine.control.role")
        self.assertFalse(scan()[self.name]["eligible"])
        objects.append(node)
        self.assertEqual(scan(), {})
