"""Build an isolated two-job OSLOG variant; run this script with WSL Python."""
from pathlib import Path
import copy
import datetime
import hashlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import zlib

repo = Path(__file__).resolve().parents[1]
work = Path('/root/hackios-lmi/hackios')
baseline = repo / 'out/lmi-ios-images-restfix'
out = repo / 'out/lmi-ios-images-lslog'
source = work / 'userland/root'
# Preserve Unix modes and links on ext4, independently of the original tree.
snapshot = Path('/root/hackios-lmi/out/lmi-ios-images-lslog/root')
assert sys.platform == 'linux', 'Run with WSL Python'
assert not out.exists() and not snapshot.parent.exists(), 'Completed/partial outputs are immutable; use a new directory'
out.mkdir()
snapshot.parent.mkdir(parents=True)


def record(path):
    sha = hashlib.sha256()
    size = crc = 0
    with path.open('rb') as stream:
        while data := stream.read(16 * 1024 * 1024):
            sha.update(data)
            size += len(data)
            crc = zlib.crc32(data, crc)
    return dict(bytes=size, sha256=sha.hexdigest(), crc32=f'{crc:08x}')


def save(name, value):
    (out / name).write_text(json.dumps(value, indent=2) + '\n')


def runlog(name, command):
    print(name, flush=True)
    with (out / name).open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def tree_records(root):
    found = {}
    for path in [root, *sorted(root.rglob('*'))]:
        st = path.lstat()
        entry = dict(mode=stat.S_IMODE(st.st_mode), kind=stat.S_IFMT(st.st_mode))
        if path.is_symlink():
            entry['target'] = os.readlink(path)
        elif path.is_file():
            entry.update(record(path))
        found['/' + str(path.relative_to(root))] = entry
    return found


meta = json.loads((baseline / 'manifest.json').read_text())
baseline_images_before = {name: record(baseline / name) for name in ('root.apfs', 'system.apfs')}
for name, measured in baseline_images_before.items():
    assert all(meta['images'][name][key] == value for key, value in measured.items()), name
source_before = tree_records(source)
runlog('baseline-apfs-check.log', [sys.executable, str(repo / 'tools/check-lmi-apfs-image.py'),
                                str(baseline / 'root.apfs'), 'redwood=' + str(source)])
shutil.copytree(source, snapshot, symlinks=True)
assert tree_records(snapshot) == source_before, 'Independent copy differs before edits'
targets = ['com.apple.SpringBoard', 'com.apple.lsd']
changes = []
for label in targets:
    path = snapshot / 'LaunchDaemons' / (label + '.plist')
    old = path.read_bytes()
    job = plistlib.loads(old)
    assert job['Label'] == label
    assert job.get('EnvironmentVariables', {}).get('OS_ACTIVITY_DT_MODE') is None
    job.setdefault('EnvironmentVariables', {})['OS_ACTIVITY_DT_MODE'] = 'YES'
    path.write_bytes(plistlib.dumps(job, fmt=plistlib.FMT_BINARY))
    new = path.read_bytes()
    restored = copy.deepcopy(plistlib.loads(new))
    del restored['EnvironmentVariables']['OS_ACTIVITY_DT_MODE']
    if not restored['EnvironmentVariables'] and 'EnvironmentVariables' not in plistlib.loads(old):
        del restored['EnvironmentVariables']
    assert restored == plistlib.loads(old), 'Unexpected plist semantic change'
    changes.append(dict(path='/LaunchDaemons/' + path.name, label=label,
                        before_sha256=hashlib.sha256(old).hexdigest(), after_sha256=hashlib.sha256(new).hexdigest(),
                        semantic_change={'EnvironmentVariables.OS_ACTIVITY_DT_MODE': 'YES'}))
snapshot_after = tree_records(snapshot)
changed = sorted(key for key in source_before if source_before[key] != snapshot_after[key])
assert changed == sorted(change['path'] for change in changes)
runlog('build.log', [sys.executable, str(work / 'tools/apfs/mkapfs.py'), '-z', '--plain', 'fw',
                     '-o', str(out / 'root.apfs'), 'redwood=' + str(snapshot)])
os.link(baseline / 'system.apfs', out / 'system.apfs')
assert os.path.samefile(baseline / 'system.apfs', out / 'system.apfs')
assert (out / 'root.apfs').stat().st_nlink == 1
runlog('apfs-check.log', [sys.executable, str(repo / 'tools/check-lmi-apfs-image.py'),
                         str(out / 'root.apfs'), 'redwood=' + str(snapshot)])
reader = work / 'apfs-work/apfs-tool'


def census(image):
    return subprocess.check_output([str(reader), 'census', str(image)], text=True)


old_census, new_census = census(baseline / 'root.apfs'), census(out / 'root.apfs')
(out / 'baseline-root-census.txt').write_text(old_census)
(out / 'root-census.txt').write_text(new_census)
old_lines = {line.split('\t')[0]: line for line in old_census.splitlines()}
new_lines = {line.split('\t')[0]: line for line in new_census.splitlines()}
assert old_lines.keys() == new_lines.keys()
census_changes = sorted(path for path in old_lines if old_lines[path] != new_lines[path])
assert census_changes == changed
for path in census_changes:
    # path/kind/mode/owner/group must stay unchanged; size/content hash may differ.
    assert old_lines[path].split('\t')[:5] == new_lines[path].split('\t')[:5]
for change in changes:
    path = change['path']
    before = subprocess.check_output([str(reader), 'cat', str(baseline / 'root.apfs'), path])
    after = subprocess.check_output([str(reader), 'cat', str(out / 'root.apfs'), path])
    assert before == (source / path.lstrip('/')).read_bytes()
    assert after == (snapshot / path.lstrip('/')).read_bytes()
    change['readback_verified'] = True
assert tree_records(source) == source_before, 'Original WSL root changed'
assert tree_records(snapshot) == snapshot_after, 'Snapshot changed during packing'
assert record(baseline / 'root.apfs') == baseline_images_before['root.apfs']
assert record(baseline / 'system.apfs') == baseline_images_before['system.apfs']
for name in ('apple-services-verification.json', 'download-verification.json', 'jobs-verification.json'):
    if (baseline / name).exists():
        shutil.copyfile(baseline / name, out / name)
# Keep the inherited jobs report accurate for the two deliberately changed files.
jobs_path = out / 'jobs-verification.json'
if jobs_path.exists():
    jobs = json.loads(jobs_path.read_text())
    for entry in jobs.get('jobs', []):
        for change in changes:
            if entry['path'] == change['path']:
                assert entry['sha256'] == change['before_sha256']
                entry['sha256'] = change['after_sha256']
    save('jobs-verification.json', jobs)
save('plist-verification.json', dict(changes=changes, changed_paths=changed,
     baseline_and_output_entries=len(old_lines), all_other_census_entries_identical=True,
     baseline_source_full_readback=True, output_snapshot_full_readback=True))
new_meta = copy.deepcopy(meta)
new_meta['images']['root.apfs'] = dict(**record(out / 'root.apfs'), source=str(snapshot), local=str(out / 'root.apfs'))
# system metadata is deliberately inherited unchanged; bytes are the same hardlinked file.
save('build-provenance.json', dict(created_at=datetime.datetime.now().astimezone().isoformat(),
     baseline=str(baseline), baseline_images=baseline_images_before, source=str(source), independent_root=str(snapshot),
     changes=changes, source_tree_unchanged=True, baseline_images_unchanged=True,
     system_is_baseline_hardlink=True, root_is_independent_file=True,
     injected_libraries_recompiled=False, no_device_access=True, persistent_storage_writes=False,
     build_script_sha256=record(Path(__file__))['sha256'], mkapfs_sha256=record(work / 'tools/apfs/mkapfs.py')['sha256']))
save('manifest.json', new_meta)
print(json.dumps(dict(output=str(out), manifest=str(out / 'manifest.json'), images=new_meta['images'], changed_paths=changed), indent=2))
