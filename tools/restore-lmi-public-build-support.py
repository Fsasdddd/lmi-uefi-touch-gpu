"""Restore published generated source inputs to ignored out/ for host checks."""
from pathlib import Path
import hashlib, json
root = Path(__file__).resolve().parents[1]
manifest = json.loads((root/'source-manifest.json').read_text(encoding='utf-8'))
entries = [x for x in manifest['public_files'] if x['path'].startswith('build-support/v72/out/')]
for entry in entries:
    source = root/entry['path']
    raw = source.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry['sha256'], source
    relative = Path(entry['path']).relative_to('build-support/v72')
    assert relative.parts[0] == 'out' and '..' not in relative.parts
    target = root/relative
    if target.exists():
        assert target.read_bytes() == raw, 'Preserve different existing input: '+str(target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
print('Restored', len(entries), 'public generated source inputs; no device access')
