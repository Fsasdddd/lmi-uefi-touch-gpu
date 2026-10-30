"""Freeze final v77e inputs; verify every historical v76 release file first."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    with p.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
parent_path=ROOT/'out/lmi-render-minimal-v76/offline-release.json'
parent=json.loads(parent_path.read_text());paths={parent_path}
for name,digest in parent['artifacts'].items():
    p=ROOT/name;assert sha(p)==digest,name;paths.add(p)
folder=ROOT/'out/lmi-cpu-epss-v77e';prepared=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v77-reviewed-e'
audit=json.loads((folder/'build-audit.json').read_text())
prep=json.loads((prepared/'prepared-only.json').read_text())
assert prep['result']=='HOST_PREPARED_ONLY' and not prep['device_access'] and prep['display_v77']
assert prep['kernel_sha256']==audit['sha256']==sha(prepared/'display-v77-candidate/mach.development.bcm2837')
for directory in [folder,ROOT/'out/lmi-cpu-epss/host-c',ROOT/'out/lmi-cpu-epss/native-e',ROOT/'out/lmi-cpu-epss/link-c',ROOT/'out/lmi-cpu-epss/policy-b']:
    for p in directory.rglob('*'):
        if p.is_file() and p.name!='offline-release.json':paths.add(p)
    if (directory/'result.json').exists():assert json.loads((directory/'result.json').read_text())['result']=='PASS'
for directory in [ROOT/'out/lmi-cpu-epss/source-review',ROOT/'out/lmi-cpu-epss/board-profile-b',
                  ROOT/'out/lmi-cpu-epss/space-a',prepared/'tools',ROOT/'out/lmi-loader']:
    paths.update(p for p in directory.rglob('*') if p.is_file())
tools=['lmi-cpu-epss.h','lmi-cpu-epss.c','lmi-cpu-epss-native.c','capture-lmi-cpu-epss-profile.py',
    'check-lmi-cpu-epss.c','check-lmi-cpu-epss.py','build-lmi-cpu-epss-v77.py','check-lmi-cpu-epss-native.py',
    'audit-lmi-cpu-epss-space.py','audit-lmi-cpu-epss-linked.py','lmi_display_v77_policy.py',
    'check-lmi-display-v77-policy.py','prepare-lmi-cpu-v77.py','test-lmi-checkpoints-v77.py',
    'prepare-lmi-cpu-loader-v77.py','build-lmi-loader-v77.py','check-lmi-gpu-normal-preflight-v77.py',
    'freeze-lmi-cpu-epss-v77.py','verify-lmi-v77-release.py']
paths.update(ROOT/'tools'/name for name in tools)
paths.update([prepared/'prepared-only.json',prepared/'kernel-checkpoint.bin',prepared/'display-v77-candidate/execution-profile.json',
    ROOT/'out/lmi-loader-test/lmi-diagnostics.img',ROOT/'out/lmi-loader-test/manifest.json',
    ROOT/'out/lmi-uefi-loader-test/manifest.json',ROOT/'out/lmi-uefi-loader-test/SILICIUM_UEFI.fd',
    ROOT/'out/lmi-gpu-research/mode46-desktop-preflight-v77.json',ROOT/'out/lmi-cpu-epss/loader-variant-v77.json'])
for report_path in [folder/'build-audit.json',ROOT/'out/lmi-cpu-epss/host-c/result.json',
                    ROOT/'out/lmi-cpu-epss/native-e/result.json',ROOT/'out/lmi-cpu-epss/link-c/result.json',
                    ROOT/'out/lmi-cpu-epss/policy-b/result.json']:
    for name,digest in json.loads(report_path.read_text())['inputs'].items():
        p=ROOT/name;assert sha(p)==digest,name;paths.add(p)
report=dict(result='OFFLINE_REVIEWED',baseline='v73',kernel_sha256=audit['sha256'],
    previous_frozen_files_verified=len(parent['artifacts']),cpu_host_scenarios=291,
    actual_arm64_scenarios=13,policy_scenarios=14,mutations_caught=8,
    independent_link_reproduced=True,original_gpu_wait_200us=True,
    original_smp_stop_required=True,explicit_cpu_boot_arg='lmi_cpu=2',ddr_enabled=False,
    prepare_only_passed=True,device_access=False,hardware_tested=False,
    measured_cpu_frequency=None,measured_animation_fps=None,performance_verified=False,wifi_integrated=False,
    artifacts={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)})
target=folder/'offline-release.json';assert not target.exists()
target.write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(parent['artifacts']),'historical files unchanged;',len(paths),'v77 release files frozen')
