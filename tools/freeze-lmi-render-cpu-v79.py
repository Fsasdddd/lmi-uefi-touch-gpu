"""Freeze the reviewed v79 release and verify its complete v77 ancestry."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / 'out/lmi-render-cpu-v79'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


parent_path = ROOT / 'out/lmi-cpu-epss-v77e/offline-release.json'
parent = json.loads(parent_path.read_text())
paths = {parent_path}
for name, digest in parent['artifacts'].items():
    path = ROOT / name
    assert sha(path) == digest, name
    paths.add(path)
prepared = ROOT / 'out/lmi-checkpoint-63-ios-probe-test-display-v79-short45-prepare-b'
prep = json.loads((prepared / 'prepared-only.json').read_text())
assert prep['result'] == 'HOST_PREPARED_ONLY' and not prep['device_access'] and prep['display_v79']
assert prep['kernel_sha256'] == sha(folder / 'mach.development.bcm2837')
for directory in [folder, ROOT / 'out/lmi-render-cpu-v79-host', ROOT / 'out/lmi-render-cpu-v79-policy',
                  ROOT / 'out/lmi-v79-integration', ROOT / 'out/lmi-loader-v78', prepared / 'tools']:
    paths.update(p for p in directory.rglob('*') if p.is_file())
for name in ['prepared-only.json', 'kernel-checkpoint.bin', 'display-v79-candidate/execution-profile.json']:
    paths.add(prepared / name)
for name in ['build-lmi-render-cpu-v79.py', 'check-lmi-render-cpu-v79.py', 'check-lmi-display-v79-policy.py',
             'prepare-lmi-render-cpu-v79.py', 'finalize-lmi-render-cpu-v79.py', 'lmi_display_v79_policy.py',
             'test-lmi-render-cpu-v79.py', 'analyze-lmi-display-v79.py', 'freeze-lmi-render-cpu-v79.py']:
    paths.add(ROOT / 'tools' / name)
paths.update(ROOT / name for name in [
    'out/lmi-loader-v78-test/lmi-diagnostics.img', 'out/lmi-loader-v78-test/manifest.json',
    'out/lmi-gpu-research/mode46-desktop-preflight-v78.json',
    'out/lmi-checkpoint-63-ios-probe-test-display-v54-desktop-180/checkpoint-63.log',
])
for name in ['out/lmi-render-cpu-v79/build-audit.json', 'out/lmi-render-cpu-v79-host/result.json',
             'out/lmi-render-cpu-v79-policy/result.json']:
    report = json.loads((ROOT / name).read_text())
    if 'scenarios' in report:
        assert report['result'] == 'PASS'
    for source, digest in report['inputs'].items():
        path = ROOT / source
        assert sha(path) == digest, source
        paths.add(path)
target = folder / 'offline-release.json'
assert not target.exists()
report = dict(
    result='OFFLINE_REVIEWED', kernel_sha256=prep['kernel_sha256'],
    previous_frozen_files_verified=len(parent['artifacts']), actual_arm64_scenarios=15,
    policy_scenarios=10, native_gpu_poll_us=50, cpu_request_restore_inherited_from='v77',
    loader_reused='v78', observation_seconds=45, host_query_delay_seconds=50,
    prepare_only_passed=True, hardware_tested=False, performance_verified=False,
    measured_animation_fps=None, wifi_integrated=False,
    artifacts={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)},
)
target.write_text(json.dumps(report, indent=2) + '\n')
print('PASS:', len(parent['artifacts']), 'previous artifacts;', len(paths), 'v79 release files frozen')
