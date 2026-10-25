"""Compare historical lmi binary patches with captured firmware, without applying them."""
from pathlib import Path
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[1]
repo = root / 'dependency-cache/historical-lmi-binaries'
commit = '1ecaca247888bc9aa73ee1b7fa9c06e6f1b5fc92'
capture = root / 'firmware-extracted/xbl_4/BOOT.XF.3.2-00304-SM8250-2'
out = root / 'out/lmi-firmware-audit'
out.mkdir(parents=True, exist_ok=True)
modules = ['ButtonsDxe', 'DALSYSDxe', 'TzDxe', 'UsbConfigDxe', 'UsbMsdDxe']
paths = subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-r', '--name-only', commit,
    *[f'lmi/QcomPkg/Drivers/{m}' for m in modules]], text=True).splitlines()
def sha(data):
    return hashlib.sha256(data).hexdigest()
def blob(path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', f'{commit}:{path}'])
metadata = blob('lmi/XBL.info').decode()
(out / 'XBL.info').write_text(metadata)
report = dict(historical_commit=commit, historical_metadata=metadata,
              patches_applied=False, modules=[])
for p in paths:
    if not p.endswith(('.efi', '.inf')):
        continue
    data = blob(p)
    target = out / 'historical' / p
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    if not p.endswith('.efi'):
        continue
    current = capture / Path(p).relative_to('lmi')
    # Patched filenames correspond to a pristine base module name.
    if '.patched.' in current.name:
        current = current.with_name(current.name.split('.patched.')[0] + '.efi')
    record = dict(path=p, bytes=len(data), sha256=sha(data), capture_present=current.exists())
    if current.exists():
        raw = current.read_bytes()
        record.update(capture_bytes=len(raw), capture_sha256=sha(raw), identical_to_capture=raw==data)
        if len(raw) == len(data):
            offsets = [i for i, (a, b) in enumerate(zip(raw, data)) if a != b]
            groups = []
            for offset in offsets:
                if groups and offset == groups[-1][1]:
                    groups[-1][1] += 1
                else:
                    groups.append([offset, offset+1])
            record.update(changed_bytes=len(offsets), changed_ranges=groups)
    report['modules'].append(record)
(out / 'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
for item in report['modules']:
    print(item['path'], 'matches capture:', item.get('identical_to_capture'),
          'changed bytes:', item.get('changed_bytes', 'different size'))
print('Historical metadata:', metadata)
