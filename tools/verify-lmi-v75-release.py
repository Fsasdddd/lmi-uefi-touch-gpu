"""Read-only verification of all v75 release artifacts in the existing workspace."""
from pathlib import Path
import argparse, hashlib, json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
args = p.parse_args()
root = args.workspace.resolve()
manifest = root / 'out/lmi-render-wait-v75/offline-release.json'
release = json.loads(manifest.read_text(encoding='utf-8'))
failures = []
for name, expected in release['artifacts'].items():
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        failures.append({'path': name, 'error': 'missing or outside workspace'})
        continue
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        failures.append({'path': name, 'error': 'SHA256 mismatch', 'actual': actual})
print(json.dumps(dict(result='PASS' if not failures else 'FAIL',
    files_checked=len(release['artifacts']), kernel_sha256=release['kernel_sha256'],
    device_access=False, failures=failures), ensure_ascii=False, indent=2))
raise SystemExit(bool(failures))
