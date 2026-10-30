"""Read-only hash verification of the final CPU-only v77 RAM release."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
release=json.loads((ROOT/'out/lmi-cpu-epss-v77e/offline-release.json').read_text())
failed=[]
for name,digest in release['artifacts'].items():
    p=ROOT/name
    if not p.is_file():failed.append(name);continue
    with p.open('rb') as handle:actual=hashlib.file_digest(handle,'sha256').hexdigest()
    if actual!=digest:failed.append(name)
assert not failed,failed
print('PASS:',len(release['artifacts']),'v77 release and historical files unchanged')
