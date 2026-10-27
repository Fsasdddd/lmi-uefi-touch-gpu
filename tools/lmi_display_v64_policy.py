"""Four-inflight GPU admission; inherit all strict v63 display/retirement gates."""
import json,re,shutil,struct
import lmi_display_v63_policy as prior
checked=prior.checked
KERNEL_SHA='ba8f526f57fd67fd9386c05a077bd1366e6f201e196d7cdebff23b6e884fea51'
AUDIT_SHA='edb8c9b0ba15cb06abd5a047143301e83c9d246870a101ef1a062eee5af798cf'
HOST_SHA='3cd316b79e3f4678ea861c7820def1a87d88e4b96dbaaf885cc3c55bb6ba6721'
NATIVE_HOST_SHA='ceedce703b63a1119f3196715c678396b147b4f680c6b2a22536ff5749ac7625'
PRIOR_SHA='e411e2b9be26278cfad1711191359f27941e779128e30306034e2d9514a341a6'
LINK_SHA='bf715eb76167eb4fd8d66ee57c245414da6c96246723d28ab455e5012f8d8ed3'

def stage(root,out):
    checked(root/'tools/lmi_display_v63_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-gpu-queue-v64b'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-gpu-queue-v64-host/result.json',HOST_SHA))
    native=json.loads(checked(root/'out/lmi-gpu-map-v64-native-host/result.json',NATIVE_HOST_SHA))
    link=json.loads(checked(root/'out/lmi-gpu-queue-v64-link-review/result.json',LINK_SHA))
    assert host['result']=='PASS' and host['asan_ubsan'] and host['scenarios']==50
    assert len(host['mutations_caught'])==7 and host['max_inflight']==4 and not host['hardware_tested']
    assert native['result']=='PASS' and native['asan_ubsan'] and native['scenarios']==16
    assert native['native_page_table_routines_verbatim'] and native['cpu_device_memory_separate']
    for report in (audit,host):
        for n,d in report['sources'].items():checked(root/'tools'/n,d)
    for report in (audit,native,link):
        for n,d in report['inputs'].items():checked(root/n,d)
    for n,d in audit['effective_object_inputs'].items():checked(root/n,d)
    checked(root/'out/lmi-gpu-queue-v64-host/check.c',host['generated_source_sha256'])
    checked(root/'out/lmi-gpu-map-v64-native-host/check.c',native['generated_source_sha256'])
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for key in ['replacement_object_reproduced','actual_link_reproduced','placed_sections_verified',
                'hooks_verified','outside_edits_exact','obsolete_entries_disabled','dsb_sy_present']:
        assert link[key]
    assert not link['hardware_tested'] and not link['performance_verified']
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    for key in ['outside_edits_exact','display_fence_bytes_preserved','cleanup_rebound_to_v62',
                'dma_attributes_unchanged','first_page_real_drain','commit_real_drain','null_handoff_dsb_only',
                'real_cache_ranges_drain','actual_scratch_retirement','rptr_space_checked','obsolete_entry_stubs']:
        assert audit[key]
    assert audit['max_inflight']==4 and not audit['direct_surface_dma'] and not audit['hardware_tested']
    assert [(s['start'],s['bytes'],s['capacity']) for s in audit['sections']]==[
        ('0xfffffff0074d9c88',4756,5060),('0xfffffff0074d21d4',64,64),('0xfffffff0074d3220',68,72),
        ('0xfffffff0074d22f8',576,1708),('0xfffffff0074d3338',176,448)]
    original=baseline.read_bytes();restored=bytearray(raw);assert len(raw)==len(original)
    for a,b in audit['allowed_file_ranges']:
        assert 0<=a<b<=len(raw);restored[a:b]=original[a:b]
    assert restored==original and len(audit['hooks'])==16
    # gpu_cached=1 has an unrelated native cache call outside gGPULock.
    # This experiment pins the reviewed default: NC command BOs.
    loader=(root/'out/lmi-loader/loader.efi').read_bytes()
    assert re.findall(rb'\bgpu_cached=(\d+)\b',loader) in ([],[b'0'])
    target=out/'display-v64-candidate';assert not target.exists();shutil.copytree(folder,target)
    for path,name in [(root/'out/lmi-gpu-queue-v64-host/result.json','queue-host-check.json'),
                      (root/'out/lmi-gpu-map-v64-native-host/result.json','native-host-check.json'),
                      (root/'out/lmi-gpu-queue-v64-link-review/result.json','link-review.json')]:shutil.copy2(path,target/name)
    meta['display_v64']=meta.pop('display_v63');meta['sha256']=KERNEL_SHA
    meta['display_v64'].update(single_outstanding=False,max_inflight=4,null_handoff_dsb_only=True,
        actual_scratch_retirement=True,rptr_space_checked=True,real_cache_ranges_drain=True,
        direct_surface_dma=False,wifi_integrated=False,performance_verified=False)
    meta['lmi_gpu_desktop'].update(source='tools/lmi-gpu-desktop-v64.c',
        source_sha256=audit['sources']['lmi-gpu-desktop-v64.c'],max_inflight=4)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def queue(log):
    rows=re.findall(r'(?m)^LMI_GPU_QUEUE\n'+r'([0-9a-f]{16})\n'*8+r'(?=LMI_GPU_MAP_BATCH\n)',log)
    values=[int(v,16) for v in rows[0]] if len(rows)==log.count('LMI_GPU_QUEUE')==1 else None
    names=['limit','peak','overlap_submissions','capacity_waits','empty_barriers','submitted','completed','stop_state']
    counts=dict(zip(names,values or []))
    markers=['LMI_SWAP_FENCE ','LMI_GPU_QUEUE\n','LMI_GPU_MAP_BATCH\n','LMI_GPU_ASYNC_DRAINED\n']
    ordered=all(log.count(m)==1 for m in markers) and all(log.index(a)<log.index(b) for a,b in zip(markers,markers[1:]))
    valid=bool(values and ordered and counts['limit']==4 and 1<=counts['peak']<=4 and
        counts['peak']<=counts['submitted']<1<<32 and counts['submitted']==counts['completed'] and
        counts['empty_barriers']>=counts['submitted'] and counts['capacity_waits']<=counts['submitted'] and
        counts['peak']-1<=counts['overlap_submissions']<counts['submitted'] and counts['stop_state']==2 and
        (counts['peak']>1)==(counts['overlap_submissions']>0) and
        prior.map_batch(log)['counts_valid'])
    return dict(counts_valid=valid,counts=counts,
        overlap_exercised=bool(valid and counts['peak']>1 and counts['overlap_submissions']>0),
        real_completion_drained=bool(valid),performance_verified=False)

def observe(log):
    result=prior.observe(log);result['gpu_queue']=queue(log)
    result['performance_verified']=False
    return result

def validate_run(observation):
    result=prior.validate_run(observation)
    required=['counts_valid','overlap_exercised','real_completion_drained']
    part=observation.get('gpu_queue')
    result['failed_checks'] += ['gpu_queue.'+n for n in required if not isinstance(part,dict) or part.get(n) is not True]
    result['passed']=not result['failed_checks']
    result['scope']='v64 four-inflight GPU plus unchanged strict v63 display/retirement gates; legacy verifier still required'
    return result
