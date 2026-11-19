#!/usr/bin/python3
"""OpenDeck PipeWire meters and locally approved channel controls."""
import argparse
import hashlib
import json
import math
import os
import select
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosedOK, WebSocketException
from appearance import monitor_display_state, options, render_svg

from control import ControlError, PipeWireControl, is_safe_target

PLUGIN_UUID = "org.codex.vuengine.sdPlugin"
ACTION_UUID = "org.codex.vuengine.level"
FPS = 10.0
FRAME_SECONDS = 1.0 / FPS
CAPTURE_LATENCY = "20ms"
RECONNECT_MIN = 0.5
RECONNECT_MAX = 8.0
NODE_SCAN_SECONDS = 2.0
PEAK_HOLD_SECONDS = 0.75
PEAK_FALL_PER_SECOND = 0.8
DISPLAY_STEPS = 80
DB_FLOOR = -60.0

_ws = None
_ws_lock = threading.Lock()
_manager = None
_shutdown = threading.Event()


def log(*parts):
    print("[vu-engine]", *parts, file=sys.stderr, flush=True)


def send_event(message):
    with _ws_lock:
        if _ws is not None:
            _ws.send(json.dumps(message, separators=(",", ":")))


def connect_opendeck(port):
    return connect(f"ws://127.0.0.1:{port}/", proxy=None, compression=None,
                   ping_interval=None, max_size=2 * 1024 * 1024, close_timeout=1)


def _level_position(rms):
    if rms <= 1e-9:
        return 0.0
    db = max(DB_FLOOR, min(0.0, 20.0 * math.log10(rms)))
    return (db - DB_FLOOR) / -DB_FLOOR


def _level_db(position):
    if position <= 0.0:
        return "−∞ dB"
    return f"{DB_FLOOR + position * -DB_FLOOR:.0f} dB"


class MeterState:
    """Time-based display smoothing and peak hold, independent of capture."""
    def __init__(self):
        self.position = 0.0
        self.peak = 0.0
        self.peak_at = 0.0

    def advance(self, rms, sample_peak, now, elapsed):
        instant = _level_position(rms)
        instant_peak = _level_position(sample_peak)
        elapsed = max(0.01, min(0.5, elapsed))
        coeff = 0.72 if instant > self.position else 0.22
        self.position += (instant - self.position) * coeff
        if instant_peak >= self.peak:
            self.peak = instant_peak
            self.peak_at = now
        elif now - self.peak_at > PEAK_HOLD_SECONDS:
            self.peak = max(self.position, self.peak - PEAK_FALL_PER_SECOND * elapsed)
        self.position = round(max(0.0, min(1.0, self.position)) * DISPLAY_STEPS) / DISPLAY_STEPS
        # Quantized release otherwise sticks one or two display steps above zero.
        if instant == 0.0 and self.position <= 2.0 / DISPLAY_STEPS:
            self.position = 0.0
        self.peak = round(max(self.position, min(1.0, self.peak)) * DISPLAY_STEPS) / DISPLAY_STEPS
        return self.position, self.peak

    def reset(self):
        self.position = 0.0
        self.peak = 0.0
        self.peak_at = 0.0


def measure_stereo(raw):
    """Return channel-averaged squared sum, maximum sample peak, and frames."""
    usable = len(raw) - len(raw) % 8
    if raw.count(0) == len(raw):
        return 0.0, 0.0, usable // 8
    square_sum = 0.0
    sample_peak = 0.0
    frames = 0
    for left, right in struct.iter_unpack("<ff", raw[:usable]):
        left = left if math.isfinite(left) else 0.0
        right = right if math.isfinite(right) else 0.0
        square_sum += (left * left + right * right) * 0.5
        sample_peak = max(sample_peak, abs(left), abs(right))
        frames += 1
    return square_sum, sample_peak, frames


class NodeRegistry:
    """Small, shared view of stable PipeWire node names and their classes."""
    def __init__(self):
        self._lock = threading.Lock()
        self._nodes = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="pw-node-registry", daemon=True)
        self._thread.start()

    def _scan(self):
        result = subprocess.run(["pw-dump"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=4, check=True)
        objects = json.loads(result.stdout)
        cookies = [obj.get("info", {}).get("cookie") for obj in objects if obj.get("type") == "PipeWire:Interface:Core"]
        cookie = cookies[0] if len(cookies) == 1 else None
        found = {}
        seen = set()
        for obj in objects:
            if obj.get("type") != "PipeWire:Interface:Node":
                continue
            props = obj.get("info", {}).get("props", {})
            name = props.get("node.name")
            media_class = props.get("media.class")
            if (isinstance(name, str) and 0 < len(name) <= 256 and name.isprintable()
                    and not name.isdecimal() and not name.startswith(("@", "-"))
                    and media_class in ("Audio/Sink", "Audio/Source")):
                if name in seen:
                    found.pop(name, None)
                    continue
                seen.add(name)
                params = obj["info"].get("params", {}).get("Props", [])
                gains = [v for v in params if "channelVolumes" in v]
                individual = (name.startswith("pwctl.source.psou-") or props.get("vuengine.control.role") == "channel")
                eligible = (individual and str(props.get("node.virtual")).lower() == "true" and
                            "device.id" not in props and "card.profile.device" not in props and
                            len(gains) == 1 and len(gains[0]["channelVolumes"]) == 2 and
                            isinstance(gains[0].get("mute"), bool))
                found[name] = {"id": obj.get("id"), "eligible": eligible, "serial": props.get("object.serial"), "cookie": cookie,
                               "node_name": name,
                               "description": props.get("node.description") or name,
                               "media_class": media_class,
                               "virtual": str(props.get("node.virtual")).lower() == "true",
                               "display_state": monitor_display_state(obj["info"].get("params", {}).get("Props", []))}
        return found

    def refresh(self):
        nodes = self._scan()
        with self._lock:
            self._nodes = nodes
            return {name: dict(node) for name, node in nodes.items()}

    def _run(self):
        delay = 0.0
        while not self._stop.wait(delay):
            try:
                self.refresh()
                delay = NODE_SCAN_SECONDS
            except Exception as exc:
                log("node scan failed", str(exc)[:180])
                delay = min(4.0, max(1.0, delay * 2))

    def snapshot(self):
        with self._lock:
            return [{k: v for k, v in node.items() if k != "display_state"} for node in sorted(self._nodes.values(), key=lambda x: x["description"].casefold())]

    def find(self, name):
        with self._lock:
            node = self._nodes.get(name)
            return dict(node) if node else None

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)


class Capture:
    """One shared pw-cat monitor reader per selected stable node.name."""
    def __init__(self, manager, node_name):
        self.manager = manager
        self.node_name = node_name
        self.lock = threading.RLock()
        self.contexts = set()
        self.stop_event = threading.Event()
        self.status = "offline"
        self.meter = MeterState()
        self._last_report = 0.0
        self._thread = threading.Thread(target=self._run, name="vu-" + node_name[-18:], daemon=True)
        self._thread.start()

    def add(self, context):
        with self.lock:
            self.contexts.add(context)

    def remove(self, context):
        empty = self.detach(context)
        if empty:
            self._thread.join(timeout=2)

    def detach(self, context):
        with self.lock:
            self.contexts.discard(context)
            empty = not self.contexts
        if empty:
            self.stop_event.set()
        return empty

    def _draw(self, now):
        with self.lock:
            contexts = tuple(self.contexts)
            status = self.status
            level = self.meter.position
            peak = self.meter.peak
        if not contexts:
            return
        node = self.manager.registry.find(self.node_name) or {}
        for context in contexts:
            instance = self.manager.get_instance(context)
            if not instance:
                continue
            label = instance.get("label") or node.get("description") or self.node_name
            control_state = self.manager.control_state(context, instance)
            if control_state is None:
                control_state = node.get("display_state")
            image = render_svg(label, status, level, peak, control_state,
                               instance["control_action"], instance["appearance"])
            self.manager.update_image(context, image)

    def _command(self, node):
        props = "node.dont-reconnect=true,node.dont-fallback=true"
        if node["media_class"] == "Audio/Sink":
            props = "stream.capture.sink=true," + props
        return ["pw-cat", "--record", "--target", self.node_name,
                "--properties", props, "--latency", CAPTURE_LATENCY,
                "--rate", "48000", "--channels", "2", "--format", "f32",
                "--raw", "-"]

    def _run(self):
        retry = RECONNECT_MIN
        proc = None
        next_frame = time.monotonic()
        square_sum = 0.0
        sample_peak = 0.0
        pending = bytearray()
        count = 0
        last_time = time.monotonic()
        try:
            while not self.stop_event.is_set():
                node = self.manager.registry.find(self.node_name)
                if not node:
                    if proc:
                        self._terminate(proc)
                        proc = None
                    with self.lock:
                        self.status = "offline"
                        self.meter.reset()
                    self._draw(time.monotonic())
                    self.stop_event.wait(0.5)
                    continue
                if proc is None:
                    with self.lock:
                        self.status = "waiting"
                    self._draw(time.monotonic())
                    try:
                        proc = subprocess.Popen(self._command(node), stdout=subprocess.PIPE,
                                                stderr=subprocess.DEVNULL, bufsize=0)
                        os.set_blocking(proc.stdout.fileno(), False)
                        pending.clear()
                        log("capture started", self.node_name, "pid", proc.pid)
                        retry = RECONNECT_MIN
                        last_time = time.monotonic()
                    except Exception as exc:
                        log("capture launch failed", self.node_name, str(exc)[:180])
                        self.stop_event.wait(retry)
                        retry = min(RECONNECT_MAX, retry * 2)
                        continue
                ready, _, _ = select.select([proc.stdout], [], [], 0.02)
                if ready:
                    try:
                        raw = os.read(proc.stdout.fileno(), 65536)
                    except BlockingIOError:
                        raw = b""
                    if not raw:
                        code = proc.poll()
                        if code is not None:
                            log("capture ended", self.node_name, "exit", code)
                            self._terminate(proc)
                            proc = None
                            self.stop_event.wait(retry)
                            retry = min(RECONNECT_MAX, retry * 2)
                            continue
                    else:
                        pending.extend(raw)
                        usable = len(pending) - len(pending) % 8
                        if usable:
                            block_squares, block_peak, frames = measure_stereo(pending[:usable])
                            square_sum += block_squares
                            sample_peak = max(sample_peak, block_peak)
                            count += frames
                            del pending[:usable]
                now = time.monotonic()
                if now >= next_frame:
                    elapsed = max(0.01, min(0.5, now - last_time))
                    rms = math.sqrt(square_sum / count) if count else 0.0
                    with self.lock:
                        self.status = "live"
                        # Fast attack, smooth release, with an independent held peak.
                        self.meter.advance(rms, sample_peak, now, elapsed)
                    if now - self._last_report >= 2.0:
                        log("meter", self.node_name, "rms", f"{rms:.4f}",
                            "peak", f"{sample_peak:.4f}")
                        self._last_report = now
                    self._draw(now)
                    square_sum = 0.0
                    sample_peak = 0.0
                    count = 0
                    last_time = now
                    next_frame = now + FRAME_SECONDS
        except Exception as exc:
            log("capture worker error", self.node_name, repr(exc))
        finally:
            if proc:
                self._terminate(proc)
            with self.lock:
                self.status = "offline"
                self.meter.reset()
            try:
                self._draw(time.monotonic())
            except Exception as exc:
                log("final image cleanup failed", self.node_name, repr(exc)[:160])
            log("capture stopped", self.node_name)

    @staticmethod
    def _terminate(proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
        if proc.stdout:
            proc.stdout.close()


class CaptureManager:
    def __init__(self):
        self.registry = NodeRegistry()
        self.control = PipeWireControl(self.registry)
        self.lock = threading.RLock()
        self.captures = {}
        self.instances = {}
        self.context_nodes = {}
        self.image_hashes = {}
        self.preview_images = {}
        self.control_states = {}
        self.target_locks = {}
        self.last_keypress = {}
        self.control_stop = threading.Event()
        self.control_wakeup = threading.Event()
        self.control_workers = set()
        self.pending_controls = {}
        self._last_image_log = 0.0
        self._image_window = time.monotonic()
        self._image_count = 0
        self.control_thread = threading.Thread(target=self._control_loop,
                                              name="vu-control-state", daemon=True)
        self.control_thread.start()

    def get_instance(self, context):
        with self.lock:
            instance = self.instances.get(context)
            return dict(instance) if instance else None

    def control_state(self, context, instance=None):
        instance = instance or self.get_instance(context) or {}
        if instance.get("control_action", "none") == "none":
            return None
        target = instance.get("control_target", "")
        if not target:
            return {"available": False, "error": "CONTROL OFF"}
        with self.lock:
            return dict(self.control_states.get(target,
                        {"available": False, "error": "CHECKING"}))

    def control_targets(self):
        return [node for node in self.registry.snapshot() if is_safe_target(node)]

    def _target_lock(self, target):
        with self.lock:
            return self.target_locks.setdefault(target, threading.Lock())

    def _redraw_context(self, context):
        with self.lock:
            node_name = self.context_nodes.get(context)
            capture = self.captures.get(node_name) if node_name else None
            instance = self.instances.get(context)
        if capture:
            capture._draw(time.monotonic())
        elif instance:
            node = self.registry.find(instance["node_name"]) or {}
            state = self.control_state(context, instance) or node.get("display_state")
            self.update_image(context, render_svg(instance["label"] or node.get("description"),
                              "live" if node else "offline", 0, 0, state,
                              instance["control_action"], instance["appearance"]))

    def _control_loop(self):
        while not self.control_stop.is_set():
            self.control_wakeup.wait(1.5)
            self.control_wakeup.clear()
            if self.control_stop.is_set():
                return
            with self.lock:
                specs = [(context, value.get("control_target", ""),
                          value.get("control_action", "none"))
                         for context, value in self.instances.items()]
            targets = sorted({target for _, target, action in specs
                              if target and action != "none"})
            for context, _, _ in specs:
                instance = self.get_instance(context)
                if instance and not instance["appearance"].vu:
                    self._redraw_context(context)
            for target in targets:
                try:
                    with self._target_lock(target):
                        state = self.control.read(target, refresh=False)
                except Exception as exc:
                    state = {"available": False, "error": str(exc)[:32] or "TARGET OFFLINE"}
                with self.lock:
                    changed = self.control_states.get(target) != state
                    self.control_states[target] = state
                    contexts = [context for context, selected, action in specs
                                if selected == target and action != "none"]
                if changed:
                    for context in contexts:
                        self._redraw_context(context)

    def handle_key_down(self, context):
        now = time.monotonic()
        with self.lock:
            instance = self.instances.get(context)
            if self.control_stop.is_set() or not instance or instance["control_action"] == "none":
                return
            native_step = (instance["control_action"] in ("volume_up", "volume_down")
                           and instance.get("unmute_on_volume_change") is True)
            if not native_step and now - self.last_keypress.get(context, 0.0) < 0.15:
                return
            self.last_keypress[context] = now
            target = instance["control_target"]
            if target in self.pending_controls:
                self.pending_controls[target].append((context, instance))
                return
            self.pending_controls[target] = deque([(context, instance)])
            worker = threading.Thread(target=self._drain_controls, args=(target,),
                                      name="vu-key-control", daemon=True)
            self.control_workers.add(worker)
            worker.start()

    def _drain_controls(self, target):
        # Preserve keyDown order across the three actions sharing a target.
        while True:
            with self.lock:
                pending = self.pending_controls[target]
                if not pending or self.control_stop.is_set():
                    del self.pending_controls[target]
                    self.control_workers.discard(threading.current_thread())
                    return
                context, instance = pending.popleft()
                visible = self.instances.get(context) is instance
            if visible:
                try:
                    self._run_control(context, instance)
                except Exception as exc:
                    log("control worker error", repr(exc)[:180])

    def _run_control(self, context, instance):
        target = instance.get("control_target", "")
        action = instance.get("control_action", "none")
        try:
            if not target:
                raise ControlError("CONTROL OFF")
            with self._target_lock(target):
                with self.lock:
                    if self.control_stop.is_set() or self.instances.get(context) is not instance:
                        return
                state = self.control.apply(target, action, instance)
            log("control action", action, target, "volume", f'{state["volume"]:.3f}',
                "muted", state["muted"])
        except Exception as exc:
            state = {"available": False, "error": str(exc)[:32] or "CONTROL ERROR"}
            log("control action failed", action, target or "(none)", repr(exc)[:180])
        with self.lock:
            if context in self.instances and self.instances[context].get("control_target", "") == target:
                if target:
                    self.control_states[target] = state
        with self.lock:
            siblings = [key for key, value in self.instances.items() if value["control_target"] == target]
        for key in siblings:
            self._redraw_context(key)

    def update_image(self, context, image):
        digest = hashlib.sha1(image.encode("utf-8")).digest()
        with self.lock:
            if context not in self.instances or self.image_hashes.get(context) == digest:
                return
            self.image_hashes[context] = digest
            self.preview_images[context] = image
        try:
            send_event({"event": "setImage", "context": context,
                        "payload": {"image": image, "state": 0}})
            now = time.monotonic()
            self._image_count += 1
            if now - self._image_window >= 5.0:
                elapsed = now - self._image_window
                log("image updates", self._image_count, "in", f"{elapsed:.1f}s",
                    "rate", f"{self._image_count / elapsed:.1f} fps", "last SVG bytes", len(image))
                self._image_count = 0
                self._image_window = now
            if now - self._last_image_log >= 60.0:
                log("image transport active", context, "SVG bytes", len(image))
                self._last_image_log = now
        except (OSError, WebSocketException, ConnectionError) as exc:
            log("image send failed", context, str(exc)[:120])

    def bind(self, context, settings):
        settings = dict(settings) if isinstance(settings, dict) else {}
        for field in ("node_name", "control_target", "theme", "control_action"):
            if not isinstance(settings.get(field), str):
                settings.pop(field, None)
        node_name = (settings.get("node_name") or "").strip()
        if len(node_name) > 256 or "\x00" in node_name:
            node_name = ""
        control_target = (settings.get("control_target") or "").strip()
        if len(control_target) > 256 or "\x00" in control_target:
            control_target = ""
        allowed_actions = {"none", "volume_up", "volume_down", "mute_toggle",
                           "set_volume", "reset_volume"}
        control_action = settings.get("control_action", "none")
        if control_action not in allowed_actions:
            control_action = "none"
        try:
            label = str(settings.get("label") or "").strip()[:24]
        except Exception:
            label = ""
        instance_settings = {
            "_local_context": context,
            "node_name": node_name,
            "label": label,
            "appearance": options(settings),
            "control_target": control_target,
            "control_action": control_action,
            "unmute_on_volume_change": settings.get("unmute_on_volume_change") is True,
            "step_mode": settings.get("step_mode", "preset"),
            "volume_step": settings.get("volume_step", 5),
            "custom_step": settings.get("custom_step", 5),
            "target_volume": settings.get("target_volume", 50),
            "reset_volume": settings.get("reset_volume", 100),
        }
        node_name = node_name if instance_settings["appearance"].vu else ""
        self.control.bind(context, instance_settings)
        old = None
        capture = None
        stop_old = False
        with self.lock:
            self.instances[context] = instance_settings
            previous = self.context_nodes.get(context)
            if previous == node_name and node_name:
                capture = self.captures.get(node_name)
                if capture:
                    capture.add(context)
                self.control_wakeup.set()
                return
            self.context_nodes[context] = node_name
            old = self.captures.get(previous) if previous else None
            if old and previous != node_name:
                stop_old = old.detach(context)
                if stop_old and self.captures.get(previous) is old:
                    self.captures.pop(previous, None)
            if not node_name:
                capture = None
            else:
                capture = self.captures.get(node_name)
                if capture is None:
                    capture = Capture(self, node_name)
                    self.captures[node_name] = capture
                capture.add(context)
        if stop_old:
            old._thread.join(timeout=2)
        if capture is None:
            self._redraw_context(context)
        self.control_wakeup.set()

    def remove(self, context):
        with self.lock:
            previous = self.context_nodes.pop(context, None)
            self.instances.pop(context, None)
            self.image_hashes.pop(context, None)
            self.preview_images.pop(context, None)
            self.last_keypress.pop(context, None)
            capture = self.captures.get(previous) if previous else None
            empty = capture.detach(context) if capture else False
            if empty and self.captures.get(previous) is capture:
                self.captures.pop(previous, None)
        if empty:
            capture._thread.join(timeout=2)

    def close(self):
        self.control_stop.set()
        self.control_wakeup.set()
        self.control_thread.join(timeout=2)
        with self.lock:
            workers = list(self.control_workers)
        for worker in workers:
            worker.join(timeout=2)
        with self.lock:
            captures = list(self.captures.values())
            self.captures.clear()
            self.instances.clear()
            self.context_nodes.clear()
        for capture in captures:
            capture.stop_event.set()
        for capture in captures:
            capture._thread.join(timeout=2)
        self.registry.close()


def _setting_payload(msg):
    payload = msg.get("payload") or {}
    if isinstance(payload.get("settings"), dict):
        return payload["settings"]
    if isinstance(payload, dict):
        return payload
    return {}


def run(args):
    global _ws, _manager
    retry = RECONNECT_MIN
    while True:
        sock = None
        manager = None
        try:
            sock = connect_opendeck(args.port)
            _ws = sock
            manager = CaptureManager()
            _manager = manager
            send_event({"event": args.registerEvent, "uuid": args.pluginUUID})
            log("registered; target render rate", FPS, "Hz")
            retry = RECONNECT_MIN
            while True:
                try:
                    data = sock.recv()
                except ConnectionClosedOK:
                    return
                if not isinstance(data, str):
                    continue
                try:
                    msg = json.loads(data)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                event = msg.get("event")
                context = msg.get("context")
                action = msg.get("action")
                action_uuid = action if isinstance(action, str) else action.get("UUID") if isinstance(action, dict) else None
                if event == "willAppear" and context and action_uuid == ACTION_UUID:
                    prior = manager.get_instance(context)
                    manager.bind(context, _setting_payload(msg))
                    if prior is None:
                        log("action visible", context, manager.get_instance(context).get("node_name"))
                elif event == "didReceiveSettings" and context and context in manager.instances:
                    manager.bind(context, _setting_payload(msg))
                elif event == "keyDown" and context and context in manager.instances:
                    if action_uuid == ACTION_UUID:
                        manager.handle_key_down(context)
                elif event == "willDisappear" and context:
                    manager.remove(context)
                    log("action hidden", context)
                elif event == "sendToPlugin" and context in manager.instances and (msg.get("payload") or {}).get("request") in ("approve", "revoke"):
                    payload = msg["payload"]
                    try:
                        name = manager.get_instance(context)["control_target"]
                        if payload["request"] == "revoke":
                            manager.control.revoke(context)
                        else:
                            manager.control.approve(context, name, payload.get("identity"))
                        message = "Permission updated"
                    except (ControlError, OSError, ValueError, subprocess.SubprocessError) as exc:
                        message = str(exc)[:180]
                    send_event({"event":"sendToPropertyInspector","context":context,
                                "payload":{"request":"permission","message":message}})
                elif event == "sendToPlugin" and context and (msg.get("payload") or {}).get("request") == "preview":
                    with manager.lock:
                        preview = manager.preview_images.get(context)
                    if preview:
                        send_event({"event": "sendToPropertyInspector", "context": context,
                                    "payload": {"request": "preview", "image": preview}})
                elif event == "sendToPlugin" and context and (msg.get("payload") or {}).get("request") == "nodes":
                    send_event({"event": "sendToPropertyInspector", "context": context,
                                "payload": {"request": "nodes", "nodes": manager.registry.snapshot(),
                                            "runtime": manager.control.error or ("Missing " + ", ".join(t for t in ("pw-cat","pw-dump") if not shutil.which(t)) if not all(shutil.which(t) for t in ("pw-cat","pw-dump")) else ""),
                                            "control_targets": [dict(n, approved=manager.control.approved(context,n)) for n in manager.control_targets()]}})
        except (OSError, WebSocketException, ConnectionError, ValueError) as exc:
            if _shutdown.is_set():
                break
            log("OpenDeck connection lost; reconnecting", repr(exc))
        finally:
            if manager:
                manager.close()
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
            _ws = None
            _manager = None
        if _shutdown.wait(retry):
            break
        retry = min(RECONNECT_MAX, retry * 2)
    log("stopped")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-port", type=int, required=True)
    parser.add_argument("-pluginUUID", required=True)
    parser.add_argument("-registerEvent", required=True)
    parser.add_argument("-info", default="{}")
    args = parser.parse_args()
    def stop_signal(signum, _frame):
        _shutdown.set()
        if _ws:
            try:
                _ws.close_socket()
            except OSError:
                pass
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    run(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("fatal", repr(exc))
        raise
