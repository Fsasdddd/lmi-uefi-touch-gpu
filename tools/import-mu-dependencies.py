"""Import Windows-downloaded pinned Git submodules into the Linux Mu tree."""
from pathlib import Path
import json
import subprocess

root = Path(__file__).resolve().parents[1]
mu = Path.home() / 'hackios-lmi/mu-silicium'
manifest = json.loads((root / 'dependency-cache/manifest.json').read_text())
for item in manifest:
    cache = root / 'dependency-cache' / item['cache']
    parent = mu / item.get('parent_path', '')
    relative = item.get('relative', item['path'])
    subprocess.run(['git', '-C', str(parent), 'config', f"submodule.{relative}.url", str(cache)], check=True)
    subprocess.run(['git', '-C', str(parent), '-c', 'protocol.file.allow=always',
                    'submodule', 'update', '--init', '--depth=1', '--', relative], check=True)
    actual = subprocess.check_output(['git', '-C', str(mu/item['path']), 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == item['commit'], (item['path'], actual)
    print(f"Imported and verified {item['path']}: {actual}", flush=True)
