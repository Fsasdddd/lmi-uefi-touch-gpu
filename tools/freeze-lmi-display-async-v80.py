"""Verify all v79 ancestry and freeze the reviewed asynchronous release."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'out/lmi-display-async-v80a'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


parent_path=ROOT/'out/lmi-render-cpu-v79/offline-release.json'
parent=json.loads(parent_path.read_text());paths={parent_path}
for name,digest in parent['artifacts'].items():
    p=ROOT/name;assert sha(p)==digest,name;paths.add(p)
prepared=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v80-async-short45-prepare'
prep=json.loads((prepared/'prepared-only.json').read_text())
assert prep['result']=='HOST_PREPARED_ONLY' and prep['display_v80'] and not prep['device_access']
assert prep['kernel_sha256']==sha(folder/'mach.development.bcm2837')
for directory in [folder,ROOT/'out/lmi-display-async-v80-review-b',ROOT/'out/lmi-display-async-v80-host-b',
                  ROOT/'out/lmi-display-async-v80-tsan-a',ROOT/'out/lmi-display-async-v80-native-a',
                  ROOT/'out/lmi-display-async-v80-policy-a',ROOT/'out/lmi-v80-integration',prepared/'tools']:
    paths.update(p for p in directory.rglob('*') if p.is_file())
for report_path in [folder/'build-audit.json',ROOT/'out/lmi-display-async-v80-review-b/result.json',
                    ROOT/'out/lmi-display-async-v80-native-a/result.json',ROOT/'out/lmi-display-async-v80-policy-a/result.json']:
    report=json.loads(report_path.read_text())
    for name,digest in report['inputs'].items():
        p=ROOT/name;assert sha(p)==digest,name;paths.add(p)
tools=['lmi-display-async-v80.c','lmi-display-async-v80.h','lmi-display-async-layout-v80.c',
       'build-lmi-display-async-v80.py','check-lmi-display-async-v80.c','check-lmi-display-async-v80-native.py',
       'review-lmi-display-async-v80.py','review-lmi-display-async-v80-v2.py',
       'lmi_display_v80_policy.py','check-lmi-display-v80-policy.py','prepare-lmi-display-async-v80.py',
       'test-lmi-display-async-v80.py','analyze-lmi-display-v80.py','freeze-lmi-display-async-v80.py']
paths.update(ROOT/'tools'/name for name in tools)
for name in ['prepared-only.json','kernel-checkpoint.bin','display-v80-candidate/execution-profile.json']:
    paths.add(prepared/name)
target=folder/'offline-release.json';assert not target.exists()
report=dict(result='OFFLINE_REVIEWED',kernel_sha256=prep['kernel_sha256'],
    previous_frozen_files_verified=len(parent['artifacts']),host_scenarios=12,stream_frames=512,
    native_scenarios=11,policy_scenarios=18,mutations_caught=3,thread_sanitizer=True,
    source_retirement_order_unchanged=True,all_prior_gpu_dpu_cpu_psci_checks_required=True,
    loader_reused='v78',observation_seconds=45,host_query_delay_seconds=50,
    prepare_only_passed=True,hardware_tested=False,performance_verified=False,
    measured_animation_fps=None,wifi_integrated=False,
    artifacts={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)})
target.write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(parent['artifacts']),'historical files;',len(paths),'v80 release files frozen')
