"""Pin reviewed v71 inputs/outputs and recheck all frozen v70 artifacts."""
from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parents[1];candidate=r/'out/lmi-gpu-deferred-cache-v71'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old_path=r/'out/lmi-gpu-overlap-v70/offline-release.json'
old=json.loads(old_path.read_text());paths={r/n for n in old['artifacts']}
for n,d in old['artifacts'].items():assert sha(r/n)==d,n
paths.add(old_path)
reports=[candidate/'build-audit.json',r/'out/lmi-gpu-deferred-cache-v71-host/result.json',
         r/'out/lmi-gpu-deferred-cache-v71-stop/result.json',r/'out/lmi-gpu-deferred-cache-v71-link-review/result.json',
         r/'out/lmi-display-v71-policy-host/result.json']
for p in reports:
    report=json.loads(p.read_text());paths.add(p)
    if p.name!='build-audit.json':assert report['result']=='PASS'
    for n,d in report.get('sources',{}).items():
        q=r/'tools'/n;assert sha(q)==d,n;paths.add(q)
    for n,d in report.get('inputs',{}).items():
        q=r/n;assert sha(q)==d,n;paths.add(q)
    for n,d in report.get('generated_sources',{}).items():
        q=p.parent/n;assert sha(q)==d,n;paths.add(q)
prepared=r/'out/lmi-checkpoint-63-ios-probe-test-display-v71-reviewed'
prep=json.loads((prepared/'prepared-only.json').read_text())
assert prep['result']=='HOST_PREPARED_ONLY' and not prep['device_access'] and prep['display_v71']
kernel=candidate/'mach.development.bcm2837'
assert sha(kernel)==prep['kernel_sha256']==json.loads(reports[0].read_text())['sha256']
assert sha(prepared/'display-v71-candidate/mach.development.bcm2837')==sha(kernel)
for directory in [candidate,r/'out/lmi-gpu-deferred-cache-v71-link-review',prepared/'tools']:
    paths.update(p for p in directory.rglob('*') if p.is_file() and p.name!='offline-release.json')
for directory in [r/'out/lmi-gpu-deferred-cache-v71-host',r/'out/lmi-gpu-deferred-cache-v71-stop']:
    paths.update(p for p in directory.rglob('*') if p.is_file() and p.suffix in ['.c','.log','.json'])
paths.update([Path(__file__),prepared/'prepared-only.json',prepared/'kernel-checkpoint.bin',
              prepared/'display-v71-candidate/execution-profile.json',r/'out/lmi-v71-integration/offline-prepare-console.log'])
paths.update(r/'tools'/n for n in ['prepare-lmi-gpu-deferred-cache-v71.py','prepare-lmi-gpu-deferred-check-v71.py',
             'prepare-lmi-gpu-deferred-build-v71.py','prepare-lmi-gpu-deferred-policy-v71.py'])
report=dict(result='OFFLINE_REVIEWED',kernel_sha256=sha(kernel),hardware_tested=False,device_access=False,
    frozen_v70_files_verified=len(old['artifacts']),desktop_gpu_2d_copy=True,async_copy_join=True,
    per_copy_fence=True,unlocked_gpu_wait=True,stop_pending_backing_retained=True,target_cache_reuse=True,
    post_invalidate_preserved=False,deferred_target_cpu_invalidate=True,cpu_transition_invalidate_required=True,state_readback_registers=21,partial_cpu_fallback=True,
    all_cpu_display_work_removed=False,wifi_integrated=False,performance_verified=False,
    artifacts={str(p.relative_to(r)):sha(p) for p in sorted(paths)})
target=candidate/'offline-release.json';assert not target.exists();target.write_text(json.dumps(report,indent=2)+'\n')
for n,d in json.loads(target.read_text())['artifacts'].items():assert sha(r/n)==d,n
print('PASS: v71 release pinned;',len(old['artifacts']),'frozen v70 files unchanged;',len(paths),'total')
