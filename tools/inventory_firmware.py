"""Inventory firmware extracted locally from this phone's XBL images."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
old_includes = root / "Mu-Silicium-v3.0/Platforms/Xiaomi/lmiPkg/Include"
required = set()
for name in ("DXE.inc", "APRIORI.inc"):
    required.update(re.findall(r"\bINF\s+Binaries/lmi/(\S+\.inf)", (old_includes / name).read_text()))
report = {"uefireader_commit": subprocess.check_output(["git", "-C", str(root / "UEFIReader"), "rev-parse", "HEAD"], text=True).strip(),
          "required_historical_binary_infs": sorted(required), "images": {}}
for name in ("xbl_4", "xbl_5"):
    image_root = root / "firmware-extracted" / name
    builds = []
    for build in image_root.iterdir():
        if not build.is_dir():
            continue
        files = {}
        for path in build.rglob("*"):
            if path.is_file():
                files[path.relative_to(build).as_posix()] = {"bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        missing = sorted(path for path in required if path not in files)
        builds.append({"build_id": build.name, "files": files, "inf_count": sum(path.endswith(".inf") for path in files),
                       "missing_historical_binary_infs": missing,
                       "patched_for_mu": False, "boot_compatible": "UNVERIFIED"})
        print(f"{name}: {build.name}, {len(files)} files, {builds[-1]['inf_count']} INF modules, {len(missing)} missing historical binary INF paths")
        if missing:
            print("Missing:", ", ".join(missing))
    report["images"][name] = {"source_sha256": hashlib.sha256((root / "device-info" / (name + ".img")).read_bytes()).hexdigest(), "builds": builds}
(root / "firmware-extracted/manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
