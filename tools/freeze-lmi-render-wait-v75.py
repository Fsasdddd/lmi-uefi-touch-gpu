"""Freeze reviewed v75, including all unchanged v74 historical release artifacts."""
from pathlib import Path
import hashlib, json

ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
candidate=ROOT/'out/lmi-render-wait-v75'
prepared=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v75-reviewed'
parent_path=ROOT/'out/lmi-display-wait-v74/offline-release.json'
parent=json.loads(parent_path.read_text())
paths={parent_path}
for name,digest in parent['artifacts'].items():
    path=ROOT/name;assert sha(path)==digest,name;paths.add(path)
audit=json.loads((candidate/'build-audit.json').read_text())
report_paths=[ROOT/'out/lmi-render-wait-v75-host/result.json',
    ROOT/'out/lmi-render-wait-v75c-link-review/result.json',
    ROOT/'out/lmi-display-v75-policy-host/result.json']
reports=[json.loads(path.read_text()) for path in report_paths]
assert all(report['result']=='PASS' for report in reports)
assert reports[0]['scenarios']==16 and len(reports[0]['mutations_caught'])==5
assert reports[0]['tsan'] and reports[0]['concurrent_writers']==4 and reports[2]['cases']==35
prep=json.loads((prepared/'prepared-only.json').read_text())
assert prep['result']=='HOST_PREPARED_ONLY' and prep['device_access'] is False and prep['display_v75']
assert prep['kernel_sha256']==audit['sha256']==reports[1]['kernel_sha256']
assert sha(prepared/'display-v75-candidate/mach.development.bcm2837')==audit['sha256']
for report in [audit,*reports]:
    for name,digest in report['inputs'].items():
        path=ROOT/name;assert sha(path)==digest,name;paths.add(path)
directories=[candidate,*[path.parent for path in report_paths],prepared/'tools',
    ROOT/'out/lmi-render-wait-v75-link-review',ROOT/'out/lmi-render-wait-v75b-link-review']
for directory in directories:
    paths.update(path for path in directory.rglob('*') if path.is_file() and path.name!='offline-release.json')
paths.update(ROOT/'tools'/name for name in ['lmi-render-wait-v75.c','lmi-render-wait-v75.h',
    'build-lmi-render-wait-v75.py','check-lmi-render-wait-v75.py','check-lmi-render-wait-v75.c',
    'audit-lmi-render-wait-v75-linked.py','lmi_display_v75_policy.py','check-lmi-display-v75-policy.py',
    'prepare-lmi-render-wait-v75.py','test-lmi-checkpoints-v75.py','freeze-lmi-render-wait-v75.py',
    'verify-lmi-v75-release.py'])
paths.update([prepared/'prepared-only.json',prepared/'kernel-checkpoint.bin',
    prepared/'display-v75-candidate/execution-profile.json'])
release=dict(result='OFFLINE_REVIEWED_HANDOFF_READY',kernel_sha256=audit['sha256'],
    frozen_v74_files_verified=len(parent['artifacts']),baseline_version='v73',
    host_scenarios=16,mutations_caught=5,concurrent_writers=4,tsan_passed=True,
    synthetic_admission_cases=35,actual_object_and_link_reproduced=True,
    independent_hook_decode=True,original_dpu_poll_and_timeout_preserved=True,
    v72_touch_preserved=True,original_gpu_code_preserved=True,
    native_gpu_poll_us=50,previous_native_gpu_poll_us=200,v74_busy_spin_included=False,
    prepare_only_passed=True,device_access=False,hardware_tested=False,
    performance_change=True,performance_verified=False,wifi_integrated=False,
    next_action='Continue from handoff in a new window; no v75 device test started',
    artifacts={path.relative_to(ROOT).as_posix():sha(path) for path in sorted(paths)})
target=candidate/'offline-release.json';assert not target.exists()
target.write_text(json.dumps(release,indent=2)+'\n')
print('PASS:',len(parent['artifacts']),'frozen v74 files unchanged;',len(paths),'v75 release artifacts')
