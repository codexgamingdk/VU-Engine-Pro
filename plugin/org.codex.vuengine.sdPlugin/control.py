"""Explicit, session-local permission for writes to bound virtual stereo sinks."""
import json
import math
import hashlib
import os
import tempfile
import fcntl
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import threading


class ControlError(RuntimeError):
    pass


def command(find=shutil.which, flatpak=None):
    if flatpak is None:
        flatpak = Path("/.flatpak-info").is_file()
    exe = find("flatpak-spawn" if flatpak else "wpexec")
    if not exe:
        return []
    return [exe, "--host", "wpexec"] if flatpak else [exe]


def is_safe_target(node):
    if not node:
        return False
    name = node["node_name"]
    return (node.get("eligible") is True and node.get("media_class") == "Audio/Sink"
            and bool(name) and not name.startswith(("@", "-"))
            and (not name.startswith("pwctl.") or
                 (name.startswith("pwctl.source.psou-") and not name.endswith(".out")))
            and all(type(node.get(key)) is int and node[key] >= 0
                    for key in ("id", "cookie", "serial")))


def identity(node):
    return {key: node[key] for key in ("node_name", "id", "cookie", "serial")}


def percent(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ControlError("Invalid percentage") from None
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise ControlError("Percentage is outside 0–100")
    return number


class PipeWireControl:
    def __init__(self, registry):
        self.registry = registry
        self.bindings = {}
        self.directory = Path(os.environ.get("XDG_STATE_HOME") or Path.home()/".local/state") / "vu-engine-pro"
        self.boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        self.lock = threading.RLock()
        self.prefix = command()
        self.error = "" if self.prefix else "Missing wpexec or Flatpak host bridge"

    @staticmethod
    def binding_key(context, settings):
        fields = ("control_target", "control_action", "volume_step", "custom_step",
                  "step_mode", "target_volume", "reset_volume", "unmute_on_volume_change")
        values = [context] + [settings.get(k) for k in fields]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()

    def bind(self, context, settings):
        with self.lock:
            self.bindings[context] = self.binding_key(context, settings)

    @contextmanager
    def store(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.directory / "approvals.json"
        fd = os.open(self.directory / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                records = json.loads(path.read_text()) if path.exists() else {}
                if not isinstance(records, dict) or any(not isinstance(v,dict) for v in records.values()):
                    raise ValueError()
            except (ValueError, OSError):
                raise ControlError("Approval file unreadable. Review or reset local approvals.") from None
            before = records.copy()
            yield records
            if before != records:
                with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as out:
                    json.dump(records, out)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(out.name, path)

    def revoke(self, context):
        with self.lock, self.store() as records:
            current = records.get(self.bindings.get(context), {})
            for key in list(records):
                if records[key].get("node_name") == current.get("node_name"):
                    del records[key]

    def approved(self, context, node):
        if not is_safe_target(node):
            return False
        try:
            with self.lock, self.store() as records:
                return records.get(self.bindings.get(context)) == dict(identity(node), boot=self.boot)
        except (OSError, ControlError):
            return False

    def _call(self, target, action, value=0, unmute=False):
        if not self.prefix:
            raise ControlError("WirePlumber control backend unavailable")
        req = dict(target, action=action, value=value, unmute=unmute)
        helper = Path(__file__).resolve().with_name("native_step.lua")
        try:
            result = subprocess.run([*self.prefix, str(helper), json.dumps(req)],
                                    capture_output=True, text=True, timeout=3, check=True)
            if result.stdout.strip() != "VU_OK":
                raise ControlError(result.stdout.strip()[:120] or "Target check failed")
        except (OSError, subprocess.SubprocessError) as exc:
            self.error = "Cannot run wpexec. Check its installation, host access and helper path."
            raise ControlError(self.error) from exc
        self.error = ""

    def approve(self, context, name, displayed):
        with self.lock:
            node = self.registry.refresh().get(name)
            if not is_safe_target(node) or identity(node) != displayed:
                raise ControlError("Target changed. Refresh and review it again.")
            if context not in self.bindings:
                raise ControlError("Key is unavailable")
            self._call(displayed, "inspect")
            with self.store() as records:
                records[self.bindings.get(context)] = dict(identity(node), boot=self.boot)

    def read(self, name, refresh=False):
        node = self.registry.find(name)
        if not is_safe_target(node) or not node.get("display_state"):
            raise ControlError("Target offline or unsupported")
        return dict(node["display_state"])

    def apply(self, name, action, settings):
        context = settings.get("_local_context")
        with self.lock:
            node = self.registry.refresh().get(name)
            if self.bindings.get(context) != self.binding_key(context, settings):
                raise ControlError("Key settings changed")
            with self.store() as records:
                if not is_safe_target(node) or records.get(self.bindings.get(context)) != dict(identity(node), boot=self.boot):
                    raise ControlError("Local approval required")
                value, unmute = 0, False
                if action in ("volume_down", "volume_up"):
                    custom = settings.get("step_mode") == "custom"
                    value = percent(settings.get("custom_step" if custom else "volume_step", 5))
                    value = max(1, round(value)) if custom else value if value in (1, 2, 5, 10) else 5
                    unmute = settings.get("unmute_on_volume_change") is True
                elif action in ("set_volume", "reset_volume"):
                    value = percent(settings.get("target_volume", 50) if action == "set_volume"
                                    else settings.get("reset_volume", 100))
                elif action != "mute_toggle":
                    raise ControlError("Unsupported action")
                self._call(identity(node), action, value, unmute)
            self.registry.refresh()
            return self.read(name)
