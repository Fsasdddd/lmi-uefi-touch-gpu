"""Overlay only libredwood's bounded native HID initialization retry on the frozen v35 image.

Run in WSL. Preserve prior candidates, full baseline filesystem and input sources.
No device access; no firmware, display, GLES or startup-job changes.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
base = root / 'out/lmi-gpu-gl-copy-v35'
base_tree = Path('/root/hackios-lmi/out/lmi-gpu-gl-copy-v35/root')
out = root / 'out/lmi-gpu-gl-hid-initial-v38'
tree = Path('/root/hackios-lmi/out/lmi-gpu-gl-hid-initial-v38/root')
src = root / 'userland-source/userland/src'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert not out.exists() and not tree.exists(), 'Preserve existing candidates'
assert sha(base / 'root.apfs') == '4fe1b6afda3bf9543be923240c31accfac8e6e19316b926f7fc85a7e70aada3b'
meta = json.loads((base / 'manifest.json').read_text())
for name, expected in meta['files'].items():
    assert sha(base_tree / name) == expected, name
check = json.loads((root / 'out/lmi-hid-usage-host/result.json').read_text())
assert check['result'] == 'PASS' and check['scenarios'] == 117
assert check['source_sha256'] == sha(src / 'inject.c')
# Bind the new source to precisely the existing hook's decision/body, retaining
# every other previously validated input, lsd, and observer change.
before = (base / 'inject.c').read_text()
after = (src / 'inject.c').read_text()
begin = '#ifdef LMI_HID_USAGE_RECHECK\n'
end = '\n/* One frame of the touch screen:'
assert before.split(begin, 1)[0] == after.split(begin, 1)[0]
assert before.split(end, 1)[1] == after.split(end, 1)[1]
# All changes are constrained to the HID initialization hook block above.

retry_check = root / 'out/lmi-hid-initial-retry-host/result.json'
retry = json.loads(retry_check.read_text())
assert retry['result'] == 'PASS' and retry['scenarios'] == 1350
assert retry['max_native_calls'] == 3 and retry['manual_setters'] is False
assert retry['source_sha256'] == sha(src / 'inject.c')
out.mkdir()
for path in base.iterdir():
    if path.is_file() and path.name not in ('root.apfs', 'manifest.json', 'build.log', 'check.log'):
        shutil.copy2(path, out / path.name)
shutil.copy2(src / 'inject.c', out / 'inject.c')
for name in ('redwood_input.h', 'redwood_gl.h'):
    assert sha(src / name) == sha(base / name), name
cc = '/root/hackios-lmi/hackios/xnu-deps/host/bin/xnu-clang'
sdk = '/root/hackios-lmi/gpu-build-env/theos/sdks/iPhoneOS16.5.sdk'
with (out / 'inject-build.log').open('w') as log:
    subprocess.run([cc, '-arch', 'arm64', '-isysroot', sdk, '-O1',
        '-DLMI_INPUT_TRACE=1', '-DLMI_LSD_SINGLE_USER=1',
        '-DLMI_HID_SIMPLE_RETRY=1', '-DLMI_HID_ROUTING_TRACE=1',
        '-DLMI_HID_USAGE_RECHECK=1', '-DLMI_HID_INITIAL_RETRY=1', '-dynamiclib',
        '-install_name', '/redwood/lib/libredwood.dylib',
        '-framework', 'CoreFoundation', '-framework', 'IOKit', '-lobjc',
        '-o', str(out / 'libredwood.dylib'), str(out / 'inject.c')],
        stdout=log, stderr=subprocess.STDOUT, check=True)
tree.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(base_tree, tree, symlinks=True)
shutil.copy2(out / 'libredwood.dylib', tree / 'lib/libredwood.dylib')


def inventory(folder):
    return {str(p.relative_to(folder)): ('symlink', str(p.readlink())) if p.is_symlink()
            else ('file', sha(p)) if p.is_file() else ('directory', '')
            for p in folder.rglob('*')}


old, new = inventory(base_tree), inventory(tree)
assert old.keys() == new.keys()
changed = sorted(name for name in old if old[name] != new[name])
assert changed == ['lib/libredwood.dylib'], changed
image = out / 'root.apfs'
with (out / 'build.log').open('w') as log:
    subprocess.run(['python3', '/root/hackios-lmi/hackios/tools/apfs/mkapfs.py',
        '-z', '--plain', 'fw', '-o', str(image), 'redwood=' + str(tree)],
        stdout=log, stderr=subprocess.STDOUT, check=True)
with (out / 'check.log').open('w') as log:
    subprocess.run(['python3', str(root / 'tools/check-lmi-apfs-image.py'),
        str(image), 'redwood=' + str(tree)], stdout=log, stderr=subprocess.STDOUT, check=True)
meta.update(image=str(image), bytes=image.stat().st_size, sha256=sha(image), source=str(tree))
meta['files']['lib/libredwood.dylib'] = sha(tree / 'lib/libredwood.dylib')
meta['input_trace_source_sha256']['inject.c'] = sha(out / 'inject.c')
meta['hid_initial_retry'] = dict(
    baseline_image_sha256=sha(base / 'root.apfs'), changed_files=changed,
    observed_bad_cache='13/4 with builtIn=NO', max_native_calls=3,
    host_check_sha256=sha(retry_check),
    builder_sha256=sha(Path(__file__).resolve()), hardware_verified=False)
(out / 'manifest.json').write_text(json.dumps(meta, indent=2) + '\n')
print(json.dumps(dict(image=str(image), sha256=meta['sha256'], changed_files=changed), indent=2))
