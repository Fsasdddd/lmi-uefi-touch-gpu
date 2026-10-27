"""New GPU/CPU accounting, with unchanged display and DMA safety requirements.

The frozen v61 fast-copy equation intentionally does not describe v71.
This policy parses original records directly; it never rewrites logs or
pretends a GPU copy was a CPU copy. Legacy verification remains separate.
"""
import json,re,shutil
import lmi_display_v66_policy as ancestor
import lmi_display_v58_policy as display
import lmi_display_v70_policy as prior
checked=ancestor.checked
KERNEL_SHA='be0c25e5e871fe0b1d7f8378ec72eaf7b89414bcd675e07fc8219e4e18d9cf40'
AUDIT_SHA='b26b2fac99ac1d62fd03c16bf2845b23ad07a16ddf0683322a8037211b5d81fc'
HOST_SHA='6ae0cb41746f2ff6ea2116519de075ae82cd0403770129e1070ac6bd70231f8a'
LINK_SHA='de981bd2820277fe9d3ad0d08bc4259dfa6e52c6e4a4df6dd9f7f51cbef13135'
def stage(root,out):
    checked(root/'tools/lmi_display_v66_policy.py','e0c8b3134547bb411015928a3bcda68843677e1daa512423bd6fb92a6f4ee463')
    baseline,meta=ancestor.stage(root,out)
    folder=root/'out/lmi-gpu-deferred-cache-v71'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host_path=root/'out/lmi-gpu-deferred-cache-v71-host/result.json'
    host=json.loads(checked(host_path,HOST_SHA))
    link_path=root/'out/lmi-gpu-deferred-cache-v71-link-review/result.json'
    link=json.loads(checked(link_path,LINK_SHA))
    assert host['result']=='PASS' and host['scenarios']==32 and len(host['mutations_caught'])==20 and host['dirty_cacheline_eviction'] and host['cache_ownership_transitions'] and host['state_readback_verified']
    for flag in ['asan_ubsan','actual_v64_backend','original_compositor_pipeline','separate_cpu_dma_views','independent_packet_decode','static_analysis','delayed_gpu_execution','copy_fence_join','native_tail_submission','deferred_cpu_ownership','actual_cpu_preservation_observed']:assert host[flag]
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for flag in ['object_reproduced','link_reproduced','placed_sections_verified','hooks_verified','outside_edits_exact',
        'full_rx_space_audit','obsolete_entries_disabled','loaded_entry_pointers_preserved','no_writable_globals',
        'correct_native_gpu_lock','real_copy_fence_binding','unlocked_delay_binding','actual_full_frame_helper_binding','no_direct_queue_drain','frozen_backend_and_dpu_preserved']:assert link[flag]
    for report in (audit,host):
        for n,d in report['sources'].items():checked(root/'tools'/n,d)
    for n,d in host['generated_sources'].items():checked(host_path.parent/n,d)
    for report in (audit,link):
        for n,d in report['inputs'].items():checked(root/n,d)
    assert audit['base_sha256']==meta['sha256'] and audit['sha256']==KERNEL_SHA and len(audit['hooks'])==5
    for flag in ['outside_edits_exact','journal_prefix_preserved','desktop_gpu_copy','partial_cpu_compositor_preserved',
        'async_copy_join','per_copy_fence','unlocked_copy_wait','stop_pending_backing_preserved','target_cache_reuse','deferred_target_cpu_invalidate','state_post_invalidate_preserved','cpu_preservation_requires_ownership_transfer','source_retirement_unchanged','touch_unchanged','dpu_pipeline_unchanged','allocations_retained_until_ram_return','gpu_2d_blit','state_page_gpu_writable','register_readback']:assert audit[flag]
    old=baseline.read_bytes();restored=bytearray(raw);assert len(old)==len(raw)
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=old[a:z]
    assert restored==old and not audit['hardware_tested'] and not audit['performance_verified']
    assert audit['post_invalidate_preserved'] is False
    checked(root/'tools/lmi_display_v70_policy.py','50624e94f8bb8a3a8d9201891428fd888ea43a85922127fcdcd52a6a4a63d81c')
    checked(root/'tools/lmi_display_v69_policy.py','0dfa1d2a179e66015720b526f4119b7cec3cccac1ab592a093cd3aef145cc0b3')
    stop_path=root/'out/lmi-gpu-deferred-cache-v71-stop/result.json'
    stop=json.loads(checked(stop_path,'338eefb7a451a7796d8a952b9ea26e0bbbbc66c06ffad950e22a53fa33f7c638'))
    assert stop['result']=='PASS'
    for flag in ['actual_backend','asan_ubsan','outstanding_copy_stopped','backing_retained','no_service_lock_after_stop']:assert stop[flag]
    for n,d in stop['inputs'].items():checked(root/n,d)
    target=out/'display-v71-candidate';assert not target.exists();shutil.copytree(folder,target)
    for path,name in [(host_path,'frame-host-check.json'),(link_path,'frame-link-review.json'),(stop_path,'frame-stop-check.json')]:shutil.copy2(path,target/name)
    meta['display_v71']=meta.pop('display_v66');meta['sha256']=KERNEL_SHA
    meta['display_v71'].update(desktop_gpu_copy=True,cpu_full_frame_copy_fallback=True,partial_cpu_compositor=True,
        all_cpu_copies_removed=False,gpu_2d_blit=True,register_readback_verified_per_copy=True,
        bounded_source_mappings=8,async_gpu_copy=True,per_copy_fence_join=True,unlocked_gpu_wait=True,target_cache_reuse=True,post_invalidate_preserved=False,deferred_target_cpu_invalidate=True,cpu_transition_invalidate_required=True,direct_surface_scanout=False,wifi_integrated=False,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta
record=prior.record

def observe(log):
    result=prior.observe(log)
    values=record(log,'LMI_GPU_CPU_TRANSFER',4)
    owned=record(log,'LMI_GPU_CPU_OWNED',1)
    tags=['LMI_GPU_COPY_PENDING ','LMI_GPU_CPU_TRANSFER ','LMI_GPU_CPU_OWNED ','LMI_GPU_QUEUE\n']
    ordered=all(log.count(tag)==1 for tag in tags) and all(log.index(a)<log.index(b) for a,b in zip(tags,tags[1:]))
    draws=result.get('gpu_frame',{}).get('counts',{}).get('draws')
    valid=bool(values and owned and 0<=owned[0]<=3 and ordered and result['gpu_copy_overlap']['counts_valid'] and
        values[0]==draws and 0<=values[1]<values[0] and values[2]==values[1]*((4544*2436+16383)&~16383) and
        (values[1]>0)==(values[3]>0))
    result['deferred_cpu_cache']=dict(counts_valid=valid,record_order_valid=ordered,
        counts=dict(zip(['post_deferred','cpu_sync_targets','cpu_sync_bytes','cpu_sync_ticks'],values or [])),
        gpu_owned_mask=owned[0] if owned else None,
        skipped_full_target_traversals=values[0]-values[1] if valid else None,
        pending_copy_zero=result['gpu_copy_overlap']['pending_zero'],performance_verified=False,
        scope='A GPU-owned target may retain stale clean CPU cache until an explicit CPU access transition; this is separate from pending DMA.')
    result['target_cache']['post_invalidate_preserved']=False
    result['target_cache']['cpu_transition_invalidate_required']=True
    return result

def validate_run(observation):
    result=prior.validate_run(observation)
    for name in ['counts_valid','record_order_valid','pending_copy_zero']:
        if observation.get('deferred_cpu_cache',{}).get(name) is not True:result['failed_checks'].append('deferred_cpu_cache.'+name)
    result['passed']=not result['failed_checks']
    result['scope']='v71 deferred CPU cache transfers, actual copy-fence completion and unchanged strict display/source/queue safety; legacy verification separate'
    return result
