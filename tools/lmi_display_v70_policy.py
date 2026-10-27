"""New GPU/CPU accounting, with unchanged display and DMA safety requirements.

The frozen v61 fast-copy equation intentionally does not describe v70.
This policy parses original records directly; it never rewrites logs or
pretends a GPU copy was a CPU copy. Legacy verification remains separate.
"""
import json,re,shutil
import lmi_display_v66_policy as ancestor
import lmi_display_v58_policy as display
import lmi_display_v69_policy as prior
checked=ancestor.checked
KERNEL_SHA='c641a036d700a9543e2c946f88a6e802240a8572702b4245062ddd14f85dfb3b'
AUDIT_SHA='53b950ca0ebf9dacaffa54c0a2ce36e75b997949342ef1f3dc10cfb51ad4d43e'
HOST_SHA='4f2e5d2ce1ce9edd77c5cad42e5a8c9b2f929c98b763e7b7062cd6e0314fb03e'
LINK_SHA='e6a202ae1be392ba8108c55c7422d2b836418c5f753d4c05c2c6fcf15d5acd1b'
def stage(root,out):
    checked(root/'tools/lmi_display_v66_policy.py','e0c8b3134547bb411015928a3bcda68843677e1daa512423bd6fb92a6f4ee463')
    baseline,meta=ancestor.stage(root,out)
    folder=root/'out/lmi-gpu-overlap-v70'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host_path=root/'out/lmi-gpu-overlap-v70-host/result.json'
    host=json.loads(checked(host_path,HOST_SHA))
    link_path=root/'out/lmi-gpu-overlap-v70-link-review/result.json'
    link=json.loads(checked(link_path,LINK_SHA))
    assert host['result']=='PASS' and host['scenarios']==29 and len(host['mutations_caught'])==17 and host['dirty_cacheline_eviction'] and host['cache_ownership_transitions'] and host['state_readback_verified']
    for flag in ['asan_ubsan','actual_v64_backend','original_compositor_pipeline','separate_cpu_dma_views','independent_packet_decode','static_analysis','delayed_gpu_execution','copy_fence_join','native_tail_submission']:assert host[flag]
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for flag in ['object_reproduced','link_reproduced','placed_sections_verified','hooks_verified','outside_edits_exact',
        'full_rx_space_audit','obsolete_entries_disabled','loaded_entry_pointers_preserved','no_writable_globals',
        'correct_native_gpu_lock','real_copy_fence_binding','unlocked_delay_binding','no_direct_queue_drain','frozen_backend_and_dpu_preserved']:assert link[flag]
    for report in (audit,host):
        for n,d in report['sources'].items():checked(root/'tools'/n,d)
    for n,d in host['generated_sources'].items():checked(host_path.parent/n,d)
    for report in (audit,link):
        for n,d in report['inputs'].items():checked(root/n,d)
    assert audit['base_sha256']==meta['sha256'] and audit['sha256']==KERNEL_SHA and len(audit['hooks'])==5
    for flag in ['outside_edits_exact','journal_prefix_preserved','desktop_gpu_copy','partial_cpu_compositor_preserved',
        'async_copy_join','per_copy_fence','unlocked_copy_wait','stop_pending_backing_preserved','target_cache_reuse','post_invalidate_preserved','source_retirement_unchanged','touch_unchanged','dpu_pipeline_unchanged','allocations_retained_until_ram_return','gpu_2d_blit','state_page_gpu_writable','register_readback']:assert audit[flag]
    old=baseline.read_bytes();restored=bytearray(raw);assert len(old)==len(raw)
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=old[a:z]
    assert restored==old and not audit['hardware_tested'] and not audit['performance_verified']
    checked(root/'tools/lmi_display_v69_policy.py','0dfa1d2a179e66015720b526f4119b7cec3cccac1ab592a093cd3aef145cc0b3')
    stop_path=root/'out/lmi-gpu-overlap-v70-stop/result.json'
    stop=json.loads(checked(stop_path,'81761f5fbe86f4e3f5d026b6d8e9a639715515876620e8089f8bf78f4a925d3e'))
    assert stop['result']=='PASS'
    for flag in ['actual_backend','asan_ubsan','outstanding_copy_stopped','backing_retained','no_service_lock_after_stop']:assert stop[flag]
    for n,d in stop['inputs'].items():checked(root/n,d)
    target=out/'display-v70-candidate';assert not target.exists();shutil.copytree(folder,target)
    for path,name in [(host_path,'frame-host-check.json'),(link_path,'frame-link-review.json'),(stop_path,'frame-stop-check.json')]:shutil.copy2(path,target/name)
    meta['display_v70']=meta.pop('display_v66');meta['sha256']=KERNEL_SHA
    meta['display_v70'].update(desktop_gpu_copy=True,cpu_full_frame_copy_fallback=True,partial_cpu_compositor=True,
        all_cpu_copies_removed=False,gpu_2d_blit=True,register_readback_verified_per_copy=True,
        bounded_source_mappings=8,async_gpu_copy=True,per_copy_fence_join=True,unlocked_gpu_wait=True,target_cache_reuse=True,post_invalidate_preserved=True,direct_surface_scanout=False,wifi_integrated=False,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta
record=prior.record

def observe(log):
    result=prior.observe(log)
    values=record(log,'LMI_GPU_COPY_OVERLAP',6)
    pending=record(log,'LMI_GPU_COPY_PENDING',1)
    tags=['LMI_GPU_TARGET_CACHE ','LMI_GPU_COPY_OVERLAP ','LMI_GPU_COPY_PENDING ','LMI_GPU_QUEUE\n']
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
