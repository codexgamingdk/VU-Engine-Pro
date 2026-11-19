"""Build an offline review ZIP. Run from any directory."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED
import hashlib
import json

root = Path(__file__).resolve().parents[1]
bundle = root / "plugin/org.codex.vuengine.sdPlugin"
version = json.loads((bundle / "manifest.json").read_text())["Version"]
files = ["appearance.py", "control.py", "icons/plugin.svg", "manifest.json",
         "meter.py", "native_step.lua", "propertyInspector/index.html"]
vendor = bundle / "vendor"
files.extend(str(path.relative_to(bundle)) for path in vendor.rglob("*.py"))
files.append("vendor/websockets-16.0.dist-info/licenses/LICENSE")
files.extend(["LICENSE", "THIRD_PARTY_NOTICES"])
out = root / "dist"
out.mkdir(exist_ok=True)
archive = out / f"VU-Engine-Pro-{version}-linux.zip"
with ZipFile(archive, "w") as package:
    for name in sorted(files):
        entry = ZipInfo(f"{bundle.name}/{name}", (1980, 1, 1, 0, 0, 0))
        entry.create_system = 3
        entry.external_attr = (0o100755 if name == "meter.py" else 0o100644) << 16
        entry.compress_type = ZIP_STORED
        package.writestr(entry, ((root if name in ("THIRD_PARTY_NOTICES", "LICENSE") else bundle) / name).read_bytes())
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n")
print(digest)
