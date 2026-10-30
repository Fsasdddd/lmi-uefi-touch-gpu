"""Freeze reviewed v74, keeping every v73 release artifact unchanged."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
candidate=ROOT/'out/lmi-display-wait-v74';prepared=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v74-reviewed'
parent_path=ROOT/'out/lmi-display-timing-v73/offline-release.json';parent=json.loads(parent_path.read_text())
paths={parent_path}
for name,digest in parent['artifacts'].items():
    path=ROOT/name;assert sha(path)==digest,name;paths.add(path)
audit=json.loads((candidate/'build-audit.json').read_text())
report_paths=[ROOT/'out/lmi-display-wait-v74-host/result.json',ROOT/'out/lmi-display-wait-v74-link-review/result.json',
    ROOT/'out/lmi-display-v74-policy-host/result.json']
reports=[json.loads(p.read_text()) for p in report_paths]
assert all(r['result']=='PASS' for r in reports)
assert reports[0]['scenarios']==16 and len(reports[0]['mutations_caught'])==5 and reports[2]['cases']==27
prep=json.loads((prepared/'prepared-only.json').read_text())
assert prep['result']=='HOST_PREPARED_ONLY' and prep['device_access'] is False and prep['display_v74']
assert prep['kernel_sha256']==audit['sha256']==reports[1]['kernel_sha256']
assert sha(prepared/'display-v74-candidate/mach.development.bcm2837')==audit['sha256']
for report in [audit,*reports]:
    for name,digest in report['inputs'].items():
        path=ROOT/name;assert sha(path)==digest,name;paths.add(path)
for directory in [candidate,*[p.parent for p in report_paths],prepared/'tools']:
    paths.update(p for p in directory.rglob('*') if p.is_file() and p.name!='offline-release.json')
paths.update(ROOT/'tools'/name for name in ['lmi-display-wait-v74.c','lmi-display-wait-v74.h',
    'build-lmi-display-wait-v74.py','check-lmi-display-wait-v74.py','check-lmi-display-wait-v74.c',
    'audit-lmi-display-wait-v74-linked.py','lmi_display_v74_policy.py','check-lmi-display-v74-policy.py',
    'prepare-lmi-display-wait-v74.py','test-lmi-checkpoints-v74.py','freeze-lmi-display-wait-v74.py'])
paths.update([prepared/'prepared-only.json',prepared/'kernel-checkpoint.bin',prepared/'display-v74-candidate/execution-profile.json'])
report=dict(result='OFFLINE_REVIEWED',kernel_sha256=audit['sha256'],frozen_v73_files_verified=len(parent['artifacts']),
    host_scenarios=16,mutations_caught=5,synthetic_admission_cases=27,actual_object_and_link_reproduced=True,
    independent_hook_decode=True,original_dpu_poll_and_timeout_preserved=True,v72_touch_preserved=True,
    original_gpu_code_preserved=True,prepare_only_passed=True,device_access=False,hardware_tested=False,
    performance_change=True,performance_verified=False,wifi_integrated=False,
    artifacts={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)})
target=candidate/'offline-release.json';assert not target.exists();target.write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(parent['artifacts']),'frozen parent files unchanged;',len(paths),'v74 release artifacts')
