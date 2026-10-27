"""Pinned producer retirement experiment; source DMA remains disabled."""
import json,re,shutil,struct
import lmi_display_v58_policy as baseline_policy
import lmi_display_v61_policy as observation_policy
checked=baseline_policy.checked
KERNEL_SHA='c5f46d3325de6c52b6b5698ac7d24cbd1f1c07829e0d2305674921dade7ad373'
AUDIT_SHA='d01c6977e922bce834e46ca109bcf525949aae511c4e06cafb6b64a97035921e'
HOST_SHA='a0ef57d2e42eff8c5e99484913403c58479fa9fb191838c2bc0085b1ec5feda4'
BASELINE_POLICY_SHA='2fa338a1b449a9fcb081e64bffb9a8f34693ca56238e15d479d32f948d2411e9'
OBSERVATION_POLICY_SHA='da6813b284f19bc9888c362ac869d9ac7621e5a4d18461f8d60e8b889621a335'
RANGES=[[5037688,5037992],[5038240,5038544],[5040552,5040628],[5040632,5040640],
        [5040644,5040844],[5041792,5041828],[5042352,5042464],[5042468,5042720],
        [5042804,5042836],[5042844,5042852],[5042856,5042988],[5043452,5044308],
        [5044584,5045036],[5045332,5046080],[11387068,11387072],[10354048,10354052],
        [5072428,5072432],[10353080,10353084],[10352976,10352980],[10357188,10357192],[10356224,10356228]]
def stage(root,out):
    checked(root/'tools/lmi_display_v58_policy.py',BASELINE_POLICY_SHA)
    checked(root/'tools/lmi_display_v61_policy.py',OBSERVATION_POLICY_SHA)
    baseline,meta=baseline_policy.stage(root,out)
    folder=root/'out/lmi-display-fast-v62d'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-v62-host/result.json',HOST_SHA))
    assert host['result']=='PASS' and host['asan_ubsan'] and host['fence_cases']==26 and host['pixel_cases']==21
    assert host['real_pthread_waiters'] and host['original_compositor_used'] and not host['hardware_tested']
    for report in (audit,host):
        for name,digest in report['sources'].items():checked(root/'tools'/name,digest)
    for name,digest in host['generated_sources'].items():checked(root/'out/lmi-display-v62-host'/name,digest)
    checked(root/'out/lmi-replaced-gpu-body-audit-v62/result.json',audit['reused_region_audit_sha256'])
    checked(root/'out/lmi-direct-surface-layout/layout.json',audit['surface_layout_sha256'])
    checked(root/'out/lmi-display-fence-layout-v62/layout.json',audit['framebuffer_layout_sha256'])
    checked(root/'hackios/xnu/files/iokit/Kernel/MiniIOSurface.h',audit['source_class_sha256'])
    checked(root/'hackios/xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp',audit['framebuffer_source_sha256'])
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    for key in ['abi_entries_preserved','outside_edits_exact','dma_mappings_unchanged','gpu_async_unchanged',
                'touch_unchanged','native_show_queue_record_retained','full_frame_one_copy','producer_retirement']:
        assert audit[key]
    assert not any(n in audit['bindings'] for n in ['snprintf','printf','vsnprintf'])
    assert not audit['direct_surface_dma'] and not audit['hardware_tested']
    assert audit['allowed_file_ranges']==RANGES and len(audit['hooks'])==7
    original=baseline.read_bytes();check=bytearray(raw);assert len(check)==len(original)
    for a,b in RANGES:check[a:b]=original[a:b]
    assert check==original and raw[0xb42ff8:0xb43000]==bytes(8)
    for (a,b),hook in zip(RANGES[-7:],audit['hooks']):
        pc=int(hook['pc'],16);w=struct.unpack_from('<I',raw,a)[0]
        d=w&0x3ffffff;d=d-(1<<26) if d&(1<<25) else d
        assert b-a==4 and w&0xfc000000==(0x94000000 if hook['link'] else 0x14000000) and pc+4*d==int(hook['new'],16)
    target=out/'display-v62-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-v62-host/result.json',target/'host-check.json')
    meta['display_v62']=meta.pop('display_v58');meta['sha256']=KERNEL_SHA
    meta['display_v62'].update(cpu_compositor_preserved=False,partial_compositor_preserved=True,full_frame_one_copy=True,
        source_pitches=[4544,4608],destination_pitch=4544,producer_retirement=True,
        dma_mappings_unchanged=True,direct_surface_dma=False,native_show_queue_record_retained=True)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def retirement(log):
    rows=re.findall(r'(?m)^LMI_SWAP_FENCE ((?:\d+ ){9}\d+)$',log)
    lines=[l for l in log.splitlines() if 'LMI_SWAP_FENCE' in l]
    values=list(map(int,rows[0].split())) if len(rows)==len(lines)==1 else None
    markers=['LMI_DPU_PROBE_RETURN restored=1\n','LMI_DPU_FAST ','LMI_FRAME_STRIDE ',
             'LMI_SWAP_FENCE ','LMI_GPU_ASYNC_DRAINED\n','LMI_RAM_ONLY_TIMER_EXPIRED\n']
    order=all(log.count(m)==1 for m in markers) and all(log.index(a)<log.index(b) for a,b in zip(markers,markers[1:]))
    bounded=values is not None and all(0<=v<1<<64 for v in values)
    counts=dict(zip(['began','retired','waits','sleeps','timeouts','busy','closed','bad','held','wakes'],values or []))
    fast=observation_policy.fast_path(log)
    valid=bool(bounded and order and counts['began']==counts['retired']>0 and counts['held']==0 and
               counts['wakes']>=counts['retired'] and sum(counts[n] for n in ['timeouts','busy','closed','bad'])<=counts['waits'] and
               fast['counts_valid'] and counts['began']>=fast['fast_frames']+fast['ordinary_frames'])
    return dict(counts_valid=valid,counts=counts,source_release_verified=valid,
                producer_wait_exercised=bool(valid and counts['waits']>0),direct_surface_dma=False,performance_verified=False)

def observe(log):
    result=observation_policy.observe(log);result['producer_retirement']=retirement(log)
    counts=result['producer_retirement']['counts']
    if result['fast_path']['counts_valid'] and counts:
        result['producer_retirement']['matches_desktop_frames']=counts['began']>=result['fast_path']['fast_frames']+result['fast_path']['ordinary_frames']
    else:result['producer_retirement']['matches_desktop_frames']=False
    result['performance_verified']=False
    return result
