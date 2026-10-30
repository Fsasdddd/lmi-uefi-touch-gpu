"""Freeze the isolated v76 candidate, reviews and unchanged historical release."""
from pathlib import Path
import hashlib, json

ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
parent_path=ROOT/'out/lmi-render-wait-v75/offline-release.json'
parent=json.loads(parent_path.read_text())
paths={parent_path}
for name,digest in parent['artifacts'].items():
    path=ROOT/name;assert sha(path)==digest,name;paths.add(path)
folder=ROOT/'out/lmi-render-minimal-v76'
audit=json.loads((folder/'build-audit.json').read_text())
host=ROOT/'out/lmi-render-minimal-v76b-host/result.json'
policy=ROOT/'out/lmi-display-v76-policy-host/result.json'
prepared=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v76-reviewed'
prep=json.loads((prepared/'prepared-only.json').read_text())
assert prep['result']=='HOST_PREPARED_ONLY' and prep['device_access'] is False and prep['display_v76']
assert prep['kernel_sha256']==audit['sha256']
assert sha(prepared/'display-v76-candidate/mach.development.bcm2837')==audit['sha256']
for report in [audit,json.loads(host.read_text()),json.loads(policy.read_text())]:
    if 'cases' in report or 'scenarios' in report:assert report['result']=='PASS'
    for name,digest in report['inputs'].items():
        path=ROOT/name;assert sha(path)==digest,name;paths.add(path)
for directory in [folder,host.parent,policy.parent,ROOT/'out/lmi-render-minimal-v76-host',prepared/'tools']:
    paths.update(p for p in directory.rglob('*') if p.is_file() and p.name!='offline-release.json')
names=['build-lmi-render-minimal-v76.py','check-lmi-render-minimal-v76.py','lmi_display_v76_policy.py',
    'check-lmi-display-v76-policy.py','prepare-lmi-render-minimal-v76.py','test-lmi-checkpoints-v76.py',
    'freeze-lmi-render-minimal-v76.py','verify-lmi-v76-release.py']
paths.update(ROOT/'tools'/n for n in names)
paths.update([prepared/'prepared-only.json',prepared/'kernel-checkpoint.bin',
              prepared/'display-v76-candidate/execution-profile.json'])
release=dict(result='OFFLINE_REVIEWED',kernel_sha256=audit['sha256'],baseline='v73',
    frozen_v75_files_verified=len(parent['artifacts']),native_arm64_scenarios=15,
    original_200us_control=True,machine_code_mutation_rejected=True,
    whole_image_outside_one_instruction_exact=True,unchanged_v73_runtime_admission=True,
    prepare_only_passed=True,device_access=False,hardware_tested=False,
    performance_verified=False,wifi_integrated=False,
    artifacts={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)})
target=folder/'offline-release.json';assert not target.exists()
target.write_text(json.dumps(release,indent=2)+'\n')
print('PASS:',len(parent['artifacts']),'frozen prior files unchanged;',len(paths),'release files pinned')
