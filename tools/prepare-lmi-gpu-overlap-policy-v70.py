"""Pin the reviewed v70 release and require real per-copy completion records."""
from pathlib import Path
import hashlib,json,re
r=Path(__file__).resolve().parents[1];t=r/'tools'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,s):
    p=t/n;assert not p.exists(),p;p.write_text(s)
s=(t/'lmi_display_v69_policy.py').read_text()
stage=s[:s.index('def record(')]
stage=stage.replace('import lmi_display_v58_policy as display', 'import lmi_display_v58_policy as display\nimport lmi_display_v69_policy as prior')
stage=stage.replace('v69','v70').replace('gpu-cache','gpu-overlap')
# prior must still be the frozen v69 parser, not a self-import.
stage=stage.replace('import lmi_display_v70_policy as prior','import lmi_display_v69_policy as prior')
pins={'KERNEL_SHA':r/'out/lmi-gpu-overlap-v70/mach.development.bcm2837',
      'AUDIT_SHA':r/'out/lmi-gpu-overlap-v70/build-audit.json',
      'HOST_SHA':r/'out/lmi-gpu-overlap-v70-host/result.json',
      'LINK_SHA':r/'out/lmi-gpu-overlap-v70-link-review/result.json'}
for key,p in pins.items():stage=re.sub(key+r"='[0-9a-f]+'",key+'='+repr(sha(p)),stage)
stage=stage.replace("host['scenarios']==28 and len(host['mutations_caught'])==14", "host['scenarios']==29 and len(host['mutations_caught'])==17")
stage=stage.replace("'independent_packet_decode','static_analysis']", "'independent_packet_decode','static_analysis','delayed_gpu_execution','copy_fence_join','native_tail_submission']")
stage=stage.replace("'correct_native_gpu_lock','frozen_backend_and_dpu_preserved']", "'correct_native_gpu_lock','real_copy_fence_binding','unlocked_delay_binding','no_direct_queue_drain','frozen_backend_and_dpu_preserved']")
stage=stage.replace("'target_cache_reuse','post_invalidate_preserved'", "'async_copy_join','per_copy_fence','unlocked_copy_wait','stop_pending_backing_preserved','target_cache_reuse','post_invalidate_preserved'")
at=stage.index("    target=out/")
stage=stage[:at]+f'''    checked(root/'tools/lmi_display_v69_policy.py',{sha(t/'lmi_display_v69_policy.py')!r})
    stop_path=root/'out/lmi-gpu-overlap-v70-stop/result.json'
    stop=json.loads(checked(stop_path,{sha(r/'out/lmi-gpu-overlap-v70-stop/result.json')!r}))
    assert stop['result']=='PASS'
    for flag in ['actual_backend','asan_ubsan','outstanding_copy_stopped','backing_retained','no_service_lock_after_stop']:assert stop[flag]
    for n,d in stop['inputs'].items():checked(root/n,d)
'''+stage[at:]
stage=stage.replace("for path,name in [(host_path,'frame-host-check.json'),(link_path,'frame-link-review.json')]", "for path,name in [(host_path,'frame-host-check.json'),(link_path,'frame-link-review.json'),(stop_path,'frame-stop-check.json')]")
stage=stage.replace('bounded_source_mappings=8,target_cache_reuse=True', 'bounded_source_mappings=8,async_gpu_copy=True,per_copy_fence_join=True,unlocked_gpu_wait=True,target_cache_reuse=True')
stage+='''record=prior.record

def observe(log):
    result=prior.observe(log)
    values=record(log,'LMI_GPU_COPY_OVERLAP',6)
    pending=record(log,'LMI_GPU_COPY_PENDING',1)
    tags=['LMI_GPU_TARGET_CACHE ','LMI_GPU_COPY_OVERLAP ','LMI_GPU_COPY_PENDING ','LMI_GPU_QUEUE\\n']
    ordered=all(log.count(tag)==1 for tag in tags) and all(log.index(a)<log.index(b) for a,b in zip(tags,tags[1:]))
    draws=result.get('gpu_frame',{}).get('counts',{}).get('draws')
    valid=bool(values and pending==[0] and ordered and result['gpu_frame']['counts_valid'] and
        values[0]==values[1]==draws and values[0]>0 and values[2]==values[1]+values[3] and
        values[1]<=values[2]<=1000*values[1] and values[4]<=values[1] and
        (values[3]>0)==(values[5]>0))
    names=['queued','finished','wait_polls','busy_polls','later_queued','unlocked_wait_ticks']
    result['gpu_copy_overlap']=dict(counts_valid=valid,pending_zero=pending==[0],
        counts=dict(zip(names,values or [])),pending=pending,record_order_valid=ordered,
        later_submission_observed=bool(valid and values[4]>0),
        unlocked_wait_exercised=bool(valid and values[3]>0),
        execution_overlap_proven=False,performance_verified=False)
    return result

def validate_run(observation):
    result=prior.validate_run(observation)
    checks=observation.get('gpu_copy_overlap',{})
    for name in ['counts_valid','pending_zero','record_order_valid']:
        if checks.get(name) is not True:result['failed_checks'].append('gpu_copy_overlap.'+name)
    result['passed']=not result['failed_checks']
    result['scope']='v70 actual copy-fence completion, zero pending DMA, GPU/CPU accounting and unchanged display/source/queue safety; legacy verification separate'
    return result
'''
write('lmi_display_v70_policy.py',stage)
s=(t/'test-lmi-checkpoints-v69.py').read_text().replace('v69','v70').replace('gpu-cache','gpu-overlap')
s=s.replace('[*range(40,67),69]', '[*range(40,67),70]')
s=s.replace("'check-lmi-display-v70-policy.py')", "'check-lmi-display-v70-policy.py','check-lmi-gpu-overlap-stop-v70.py','lmi_display_v69_policy.py')")
write('test-lmi-checkpoints-v70.py',s)
