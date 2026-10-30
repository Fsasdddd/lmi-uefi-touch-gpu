"""Freeze completed v73 offline work and verify all frozen v72 artifacts."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
candidate=ROOT/'out/lmi-display-timing-v73'
prepared=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v73-reviewed'
old_path=ROOT/'out/lmi-touch-cadence-v72b/offline-release.json'
old=json.loads(old_path.read_text());paths={old_path}
for name,digest in old['artifacts'].items():
    path=ROOT/name;assert sha(path)==digest,name;paths.add(path)
audit=json.loads((candidate/'build-audit.json').read_text())
host_path=ROOT/'out/lmi-display-timing-v73b-host/result.json'
link_path=ROOT/'out/lmi-display-timing-v73b-link-review/result.json'
policy_path=ROOT/'out/lmi-display-v73-policy-host/result.json'
reports=[audit,*[json.loads(p.read_text()) for p in [host_path,link_path,policy_path]]]
assert reports[1]['result']=='PASS' and reports[1]['scenarios']==16 and len(reports[1]['mutations_caught'])==6
assert reports[2]['result']=='PASS' and reports[3]['result']=='PASS' and reports[3]['cases']==68
prep=json.loads((prepared/'prepared-only.json').read_text())
assert prep['result']=='HOST_PREPARED_ONLY' and prep['device_access'] is False and prep['display_v73']
assert prep['kernel_sha256']==audit['sha256']==reports[2]['kernel_sha256']
assert sha(prepared/'display-v73-candidate/mach.development.bcm2837')==audit['sha256']
for report in reports:
    for name,digest in report['inputs'].items():
        path=ROOT/name;assert sha(path)==digest,name;paths.add(path)
for directory in [candidate,host_path.parent,link_path.parent,policy_path.parent,
                  ROOT/'out/lmi-display-timing-v73-host',ROOT/'out/lmi-display-timing-v73-link-review',
                  prepared/'tools']:
    paths.update(p for p in directory.rglob('*') if p.is_file() and p.name!='offline-release.json')
paths.update(ROOT/'tools'/name for name in ['lmi-display-timing-v73.c','lmi-display-timing-v73.h',
    'build-lmi-display-timing-v73.py','check-lmi-display-timing-v73.py','check-lmi-display-timing-v73.c',
    'audit-lmi-display-timing-v73-linked.py','lmi_display_v73_policy.py','check-lmi-display-v73-policy.py',
    'prepare-lmi-display-timing-v73.py','test-lmi-checkpoints-v73.py','freeze-lmi-display-timing-v73.py'])
paths.update([prepared/'prepared-only.json',prepared/'kernel-checkpoint.bin',
              prepared/'display-v73-candidate/execution-profile.json'])
report=dict(result='OFFLINE_REVIEWED_PAUSED',kernel_sha256=audit['sha256'],
    frozen_v72_files_verified=len(old['artifacts']),host_scenarios=16,mutations_caught=6,
    synthetic_admission_cases=68,actual_object_and_link_reproduced=True,
    independent_hook_decode=True,v72_touch_preserved=True,original_gpu_code_preserved=True,
    prepare_only_passed=True,user_requested_pause_after_build=True,device_access=False,
    hardware_tested=False,performance_change=False,performance_verified=False,wifi_integrated=False,
    artifacts={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)})
target=candidate/'offline-release.json';assert not target.exists()
target.write_text(json.dumps(report,indent=2)+'\n')
for name,digest in report['artifacts'].items():assert sha(ROOT/name)==digest,name
print('PASS:',len(old['artifacts']),'frozen v72 files unchanged;',len(paths),'total release artifacts; v73 paused without device access')
