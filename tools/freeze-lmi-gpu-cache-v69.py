"""Pin v69 inputs, retaining and rechecking the complete frozen v68 release."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1];candidate=root/'out/lmi-gpu-cache-v69'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((root/'out/lmi-gpu-frame-v68b/offline-release.json').read_text())
for n,d in old['artifacts'].items():assert sha(root/n)==d,n
paths={root/n for n in old['artifacts']}
reports=[candidate/'build-audit.json',root/'out/lmi-gpu-cache-v69-host/result.json',
         root/'out/lmi-gpu-cache-v69-link-review/result.json',root/'out/lmi-display-v69-policy-host/result.json']
for q in reports:
    report=json.loads(q.read_text());paths.add(q)
    if q.name!='build-audit.json':assert report['result']=='PASS'
    for n,d in report.get('sources',{}).items():
        p=root/'tools'/n;assert sha(p)==d,n;paths.add(p)
    for n,d in report.get('inputs',{}).items():
        p=root/n;assert sha(p)==d,n;paths.add(p)
    for n,d in report.get('generated_sources',{}).items():
        p=q.parent/n;assert sha(p)==d,n;paths.add(p)
prepared=root/'out/lmi-checkpoint-63-ios-probe-test-display-v69-reviewed-c'
prep=json.loads((prepared/'prepared-only.json').read_text());paths.add(prepared/'prepared-only.json')
assert prep['result']=='HOST_PREPARED_ONLY' and not prep['device_access'] and prep['display_v69']
kernel=candidate/'mach.development.bcm2837'
assert sha(kernel)==prep['kernel_sha256']==json.loads(reports[0].read_text())['sha256']
assert sha(prepared/'display-v69-candidate/mach.development.bcm2837')==sha(kernel)
for p in (prepared/'tools').rglob('*'):
    if p.is_file():paths.add(p)
paths.update([kernel,candidate/'code-review.md',Path(__file__),root/'tools/test-lmi-checkpoints-v69.py',
              prepared/'kernel-checkpoint.bin',prepared/'display-v69-candidate/execution-profile.json'])
paths.update(root/'tools'/n for n in ['prepare-lmi-gpu-cache-v69.py','prepare-lmi-gpu-cache-check-v69.py',
                                    'prepare-lmi-gpu-cache-build-v69.py','prepare-lmi-gpu-cache-policy-v69.py'])
report=dict(result='OFFLINE_REVIEWED',kernel_sha256=sha(kernel),hardware_tested=False,device_access=False,
    frozen_v68_files_verified=len(old['artifacts']),desktop_gpu_2d_copy=True,target_cache_reuse=True,
    dirty_cacheline_eviction_checked=True,post_invalidate_preserved=True,state_readback_registers=21,
    partial_cpu_fallback=True,all_cpu_display_work_removed=False,wifi_integrated=False,performance_verified=False,
    artifacts={str(q.relative_to(root)):sha(q) for q in sorted(paths)})
(candidate/'offline-release.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: v69 release pinned;',report['frozen_v68_files_verified'],'frozen v68 artifacts unchanged;',len(paths),'total')
