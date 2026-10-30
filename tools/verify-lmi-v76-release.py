"""Read-only verification of the v76 release and its pinned historical inputs."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'out/lmi-render-minimal-v76/offline-release.json').read_text())
failures=[]
for name,digest in manifest['artifacts'].items():
    path=(ROOT/name).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():failures.append(name);continue
    with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=digest:failures.append(name)
print(json.dumps(dict(result='FAIL' if failures else 'PASS',files_checked=len(manifest['artifacts']),
    kernel_sha256=manifest['kernel_sha256'],device_access=False,failures=failures),indent=2))
raise SystemExit(bool(failures))
