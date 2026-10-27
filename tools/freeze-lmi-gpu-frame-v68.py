"""Pin the separately reviewed v68 release; never alter frozen v67 files."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1];candidate=root/'out/lmi-gpu-frame-v68b'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((root/'out/lmi-gpu-frame-v67/offline-release.json').read_text())
for n,d in old['artifacts'].items():assert sha(root/n)==d,n
paths={root/n for n in old['artifacts']}
report_paths=[candidate/'build-audit.json',root/'out/lmi-gpu-frame-v68-host/result.json',
    root/'out/lmi-gpu-blit-v68-host/result.json',root/'out/lmi-gpu-frame-v68b-link-review/result.json',
    root/'out/lmi-display-v68-policy-host/result.json']
for q in report_paths:
    report=json.loads(q.read_text());paths.add(q)
    if q.name!='build-audit.json':assert report['result']=='PASS'
    for n,d in report.get('sources',{}).items():
        p=root/'tools'/n;assert sha(p)==d,n;paths.add(p)
    for n,d in report.get('inputs',{}).items():
        p=root/n;assert sha(p)==d,n;paths.add(p)
    for n,d in report.get('fixture_sha256',{}).items():
        p=root/n;assert sha(p)==d,n;paths.add(p)
    for n,d in report.get('generated_sources',{}).items():
        p=q.parent/n;assert sha(p)==d,n;paths.add(p)
proof_path=root/'out/lmi-v67-integration/firmware-semantics-review.json'
proof=json.loads(proof_path.read_text());paths.add(proof_path)
assert not proof['hardware_tested'] and not proof['performance_verified']
assert proof['state_register_values']==21 and proof['state_save_packets']==14 and proof['state_restore_packets']==7
for n,d in proof['artifacts'].items():
    p=root/n;assert sha(p)==d,n;paths.add(p)
prepared=root/'out/lmi-checkpoint-63-ios-probe-test-display-v68-reviewed'
p=prepared/'prepared-only.json';prep=json.loads(p.read_text());paths.add(p)
assert prep['result']=='HOST_PREPARED_ONLY' and not prep['device_access'] and prep['display_v68']
kernel=candidate/'mach.development.bcm2837'
assert sha(kernel)==prep['kernel_sha256']==json.loads(report_paths[0].read_text())['sha256']
assert sha(prepared/'display-v68-candidate/mach.development.bcm2837')==sha(kernel)
for p in (prepared/'tools').rglob('*'):
    if p.is_file():paths.add(p)
paths.update([kernel,candidate/'code-review.md',Path(__file__),root/'tools/test-lmi-checkpoints-v68.py',
              prepared/'kernel-checkpoint.bin',prepared/'display-v68-candidate/execution-profile.json'])
report=dict(result='OFFLINE_REVIEWED',kernel_sha256=sha(kernel),hardware_tested=False,device_access=False,
    frozen_v67_files_verified=len(old['artifacts']),desktop_gpu_2d_copy=True,state_readback_registers=21,
    partial_cpu_fallback=True,all_cpu_display_work_removed=False,wifi_integrated=False,performance_verified=False,
    artifacts={str(q.relative_to(root)):sha(q) for q in sorted(paths)})
(candidate/'offline-release.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: v68b release pinned;',report['frozen_v67_files_verified'],'frozen v67 artifacts unchanged')
