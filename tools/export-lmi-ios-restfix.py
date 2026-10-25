"""Rebuild/export the REST job repair in WSL without touching canonical images or devices."""
from pathlib import Path
import datetime, hashlib, json, os, plistlib, shutil, stat, subprocess, sys, zlib

repo = Path(__file__).resolve().parents[1]
work = Path('/root/hackios-lmi/hackios')
user = work / 'userland'
out = repo / 'out/lmi-ios-images-restfix'
canonical = repo / 'out/lmi-ios-images'
resume = sys.argv[1:] == ['--resume-verification']
assert resume or not out.exists(), f'Use a new output directory: {out}'
assert not resume or not (out / 'manifest.json').exists(), 'Completed image sets are immutable; use a new output directory'
assert not resume or not (out / 'root.apfs').exists() or (out / 'root.apfs').stat().st_nlink == 1, 'Do not rewrite an image hardlinked into evidence'
if not resume:
    out.mkdir()

def record(path):
    digest = hashlib.sha256(); crc = size = 0
    with path.open('rb') as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk); crc = zlib.crc32(chunk, crc); size += len(chunk)
    return dict(bytes=size, sha256=digest.hexdigest(), crc32=f'{crc:08x}')

def save(name, obj):
    (out / name).write_text(json.dumps(obj, indent=2) + '\n')

before = (repo / 'out/lmi-mkjobs-rest-check/mkjobs.before.py').read_bytes()
fixed = (repo / 'userland-source/userland/mkjobs.py').read_bytes()
target = user / 'mkjobs.py'
assert target.read_bytes() == (fixed if resume else before), 'WSL source must match reviewed bytes'
assert b'for env_name in' in fixed and fixed != before
mode = stat.S_IMODE(target.stat().st_mode)
build = user / 'build.sh'
build_text = build.read_text()
assert 'drawable_test unavailable in PREBUILT' in build_text
assert not any((work / 'ios165' / name).is_symlink() for name in ('rootfs', 'cryptex', 'cryptex-app'))
meta = json.loads((canonical / 'manifest.json').read_text())
canonical_before = record(canonical / 'system.apfs')
assert all(canonical_before[k] == meta['images']['system.apfs'][k] for k in canonical_before)
source_before = record(user / 'system.apfs')
# A small-image-only rebuild: refuse before invoking build.sh if its documented system rebuild
# prerequisites are newer. PREBUILT keeps the unchanged stage0 timestamp.
system_time = (user / 'system.apfs').stat().st_mtime_ns
for dep in (user / 'obj/stage0', work / 'ios165/system.manifest', work / 'ios165/cryptex', work / 'ios165/cryptex-app'):
    assert not dep.exists() or dep.stat().st_mtime_ns <= system_time, f'Would rebuild system.apfs: {dep}'
assert (user / 'obj/stage0').read_bytes() == (work / 'prebuilt/userland/stage0').read_bytes()
if not resume:
    target.write_bytes(fixed)
assert stat.S_IMODE(target.stat().st_mode) == mode
env = os.environ.copy()
for key in ('SYSTEM', 'FLASHBOOT', 'GL', 'ADSP', 'INJECT', 'STOREFRONT', 'EXTRA', 'EXTRA_SHARE',
            'RC', 'RC_JOBS', 'QUIET', 'JOBS', 'WIFID', 'CHECK', 'RWA_PACKED16', 'JB'):
    env.pop(key, None)
env.update(PREBUILT='1', REST='1')
if not resume:
    print('Rebuilding WSL root.apfs with PREBUILT=1 REST=1', flush=True)
    with (out / 'build.log').open('w') as log:
        subprocess.run(['bash', str(build)], cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
source_after = record(user / 'system.apfs')
assert source_after == source_before, 'WSL system.apfs unexpectedly changed; canonical remains untouched'
# Both Apple variants share Label/MachServices/ProgramArguments, but one explicitly requires
# IsDarwinOS while the other explicitly excludes it. Preserve the iOS variant in this iOS image.
variant_exclusion = user / 'root/LaunchDaemons/com.apple.sysdiagnose.darwinos.plist'
ios_variant = user / 'root/LaunchDaemons/com.apple.sysdiagnose.plist'
exclusions = []
if variant_exclusion.exists():
    excluded_bytes = variant_exclusion.read_bytes()
    darwin_job = plistlib.loads(excluded_bytes)
    ios_job = plistlib.loads(ios_variant.read_bytes())
    assert darwin_job['_LimitLoadToVariant'] == ios_job['_LimitLoadFromVariant'] == 'IsDarwinOS'
    for key in ('Label', 'ProgramArguments', 'MachServices'):
        assert darwin_job[key] == ios_job[key], key
    exclusions.append(dict(path='/LaunchDaemons/' + variant_exclusion.name, job=darwin_job,
                           sha256=hashlib.sha256(excluded_bytes).hexdigest(),
                           reason='Requires IsDarwinOS; kept the paired iOS job that excludes IsDarwinOS'))
    save('variant-exclusions.json', exclusions)
    variant_exclusion.unlink()
    with (out / 'variant-repack.log').open('w') as log:
        subprocess.run([sys.executable, str(work / 'tools/apfs/mkapfs.py'), '-z', '--plain', 'fw',
                        '-o', str(user / 'root.apfs'), 'redwood=' + str(user / 'root')],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    if resume:
        shutil.copyfile(user / 'root.apfs', out / 'root.apfs')
elif resume:
    exclusions = json.loads((out / 'variant-exclusions.json').read_text())
if not resume:
    os.link(canonical / 'system.apfs', out / 'system.apfs')
assert os.path.samefile(canonical / 'system.apfs', out / 'system.apfs')
if not resume:
    shutil.copyfile(user / 'root.apfs', out / 'root.apfs')
else:
    assert record(out / 'root.apfs') == record(user / 'root.apfs')
reader = work / 'apfs-work/apfs-tool'

def cat(image, path):
    return subprocess.check_output([str(reader), 'cat', str(image), path], timeout=60, stderr=subprocess.PIPE)

def census_jobs(image):
    census = subprocess.check_output([str(reader), 'census', str(image), '/LaunchDaemons'], text=True)
    paths = [line.split('\t')[0] for line in census.splitlines() if line.split('\t')[0].startswith('/LaunchDaemons/')]
    files = [path for path in paths if path.endswith('.plist')]
    assert not any('RWA_PACKED16' in path for path in paths), paths
    records = []
    for path in files:
        data = cat(image, path); job = plistlib.loads(data)
        # Stock Apple job filenames can differ from Label (idscredentialsagent is one).
        records.append(dict(path=path, label=job['Label'], sha256=hashlib.sha256(data).hexdigest(),
                            program=job.get('Program') or job.get('ProgramArguments', [''])[0],
                            MachServices=job.get('MachServices', {})))
    assert len({entry['label'] for entry in records}) == len(records)
    return census, records

census, jobs = census_jobs(out / 'root.apfs')
(out / 'root-census.txt').write_text(subprocess.check_output([str(reader), 'census', str(out / 'root.apfs')], text=True))
old_census = subprocess.check_output([str(reader), 'census', str(canonical / 'root.apfs'), '/LaunchDaemons'], text=True)
old_names = {line.split('\t')[0] for line in old_census.splitlines()}
new_paths = [entry['path'] for entry in jobs if entry['path'] not in old_names]
angels_dir = work / 'ios165/rootfs/System/Library/LaunchAngels'
angel_names = {path.name for path in angels_dir.glob('*.plist')}
angels = [entry['label'] for entry in jobs if Path(entry['path']).name in angel_names]
assert new_paths and angels, 'Expected REST jobs and LaunchAngels'
assert len(jobs) == len(list((user / 'root/LaunchDaemons').glob('*.plist')))
save('jobs-verification.json', dict(total_jobs=len(jobs), unique_labels=len(jobs), added_job_count=len(new_paths),
    added_paths=new_paths, launch_angel_count=len(angels), launch_angels=angels, malformed_RWA_PACKED16_absent=True, jobs=jobs))
with (out / 'apfs-check.log').open('w') as log:
    subprocess.run([sys.executable, str(repo / 'tools/check-lmi-apfs-image.py'), str(out / 'root.apfs'),
                    'redwood=' + str(user / 'root')], stdout=log, stderr=subprocess.STDOUT, check=True)

verification = json.loads((repo / 'out/ios165-download-verification.json').read_text())
assert len(verification['dmgs']) == 3 and all(entry['verified'] for entry in verification['dmgs'])
apple = []
for path in ('/sbin/launchd.ios', '/usr/libexec/backboardd', '/usr/libexec/runningboardd',
             '/usr/libexec/containermanagerd', '/usr/libexec/logd', '/System/Library/CoreServices/SpringBoard.app/SpringBoard'):
    source_path = work / 'ios165/rootfs' / ('sbin/launchd' if path == '/sbin/launchd.ios' else path.lstrip('/'))
    data = cat(out / 'system.apfs', path)
    assert data and data == source_path.read_bytes(), path
    apple.append(dict(image_path=path, original=str(source_path), bytes=len(data),
                      sha256=hashlib.sha256(data).hexdigest(), unmodified=True))
save('apple-services-verification.json', dict(image_sha256=canonical_before['sha256'],
    reader_sha256=record(reader)['sha256'], executables=apple,
    scope='Byte identity in APFS only; runtime and desktop require separate live evidence.'))
shutil.copyfile(repo / 'out/ios165-download-verification.json', out / 'download-verification.json')
images = {}
for name in ('system.apfs', 'root.apfs'):
    images[name] = dict(**record(out / name), source=str(canonical / name if name == 'system.apfs' else user / name), local=str(out / name))
assert record(canonical / 'system.apfs') == canonical_before
save('manifest.json', dict(images=images, apple_launchd=verification['apple_launchd'], source=verification['source'], persistent_storage_writes=False))
save('build-provenance.json', dict(created_at=datetime.datetime.now().astimezone().isoformat(),
    environment={'PREBUILT': '1', 'REST': '1'}, mkjobs_before_sha256=hashlib.sha256(before).hexdigest(),
    mkjobs_after_sha256=hashlib.sha256(fixed).hexdigest(), mkjobs_mode=oct(mode), build_sh_sha256=record(build)['sha256'],
    WSL_system_before=source_before, WSL_system_after=source_after, canonical_system_unchanged=True,
    system_is_canonical_hardlink=True, root_source=str(user / 'root.apfs'),
    no_device_access=True, no_flash_writes=True, jobs=len(jobs), launch_angels=len(angels),
    platform_variant_exclusions=exclusions))
print(json.dumps(dict(output=str(out), jobs=len(jobs), added_jobs=len(new_paths), launch_angels=len(angels), images=images), indent=2), flush=True)
