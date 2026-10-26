"""One-copy CPU experiment with pinned ancestry and independent hit evidence."""
import json,re,shutil,struct
import lmi_display_v58_policy as prior
checked=prior.checked
KERNEL_SHA='136c6a00184f8dd2527306f6df8e4fde1d1f6f91ed3f9f7971548a7996086f88'
AUDIT_SHA='3f32356b9e59456e75dd197430a7611099dde283ac05f8fac82ddde566c5ec20'
HOST_SHA='71c6453b024ab439f8aadab1345a7322fcb88cb667aab87c85a60b8e5d043bff'
PRIOR_SHA='2fa338a1b449a9fcb081e64bffb9a8f34693ca56238e15d479d32f948d2411e9'
RANGES=[[5040644,5040844],[5042468,5042608],[5042804,5042833],[5044584,5045092],
        [5045332,5046032],[11387068,11387072],[10354048,10354052],[5072428,5072432]]
def stage(root,out):
    checked(root/'tools/lmi_display_v58_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-display-fast-v59b'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-fast-v59-host/result.json',HOST_SHA))
    assert host['result']=='PASS' and host['asan_ubsan'] and host['scenarios']==17 and host['original_compositor_used'] and not host['hardware_tested']
    for report in (audit,host):
        for name,digest in report['sources'].items():checked(root/'tools'/name,digest)
    checked(root/'out/lmi-replaced-gpu-body-audit/result.json',audit['reused_region_audit_sha256'])
    checked(root/'out/lmi-direct-surface-layout/layout.json',audit['surface_layout_sha256'])
    checked(root/'hackios/xnu/files/iokit/Kernel/MiniIOSurface.h',audit['source_class_sha256'])
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    for key in ['abi_entries_preserved','outside_edits_exact','dma_mappings_unchanged','gpu_async_unchanged','touch_unchanged','native_show_queue_record_retained','full_frame_one_copy']:
        assert audit[key]
    assert not audit['direct_surface_dma'] and not audit['hardware_tested']
    assert audit['allowed_file_ranges']==RANGES
    original=baseline.read_bytes();check=bytearray(raw);assert len(check)==len(original)
    for a,b in RANGES:check[a:b]=original[a:b]
    assert check==original
    assert raw[0xb42ff8:0xb43000]==bytes(8)
    for (a,b),hook in zip(RANGES[-3:],audit['hooks']):
        pc=int(hook['pc'],16);word=struct.unpack_from('<I',raw,a)[0]
        d=word&0x3ffffff;d=d-(1<<26) if d&(1<<25) else d
        assert word&0xfc000000==0x94000000 and pc+4*d==int(hook['new'],16)
    target=out/'display-v59-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-fast-v59-host/result.json',target/'fast-host-check.json')
    meta['display_v59']=meta.pop('display_v58');meta['sha256']=KERNEL_SHA
    meta['display_v59'].update(cpu_compositor_preserved=False,partial_compositor_preserved=True,full_frame_one_copy=True,
        dma_mappings_unchanged=True,direct_surface_dma=False,native_show_queue_record_retained=True)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def fast_path(log):
    lines=[l for l in log.splitlines() if 'LMI_DPU_FAST' in l]
    found=re.findall(r'(?m)^LMI_DPU_FAST (\d+) (\d+) (\d+)$',log)
    counts=list(map(int,found[0])) if len(found)==len(lines)==1 else None
    markers=['LMI_DPU_PROBE_RETURN restored=1\n','LMI_DPU_FAST ','LMI_GPU_ASYNC_DRAINED\n','LMI_RAM_ONLY_TIMER_EXPIRED\n']
    order=all(log.count(m)==1 for m in markers) and all(log.index(a)<log.index(b) for a,b in zip(markers,markers[1:]))
    valid=bool(counts is not None and order and counts[0]==counts[1] and counts[0]+counts[2]>0 and prior.asynchronous(log)['exit_gpu_drain_verified'])
    return dict(counts_valid=valid,fast_frames=counts[0] if counts else None,copy_calls=counts[1] if counts else None,
        ordinary_frames=counts[2] if counts else None,fast_path_exercised=bool(valid and counts[0]>0),
        direct_surface_dma=False,performance_verified=False)

def observe(log):
    result=prior.observe(log);result['fast_path']=fast_path(log)
    result['performance_verified']=False
    return result
