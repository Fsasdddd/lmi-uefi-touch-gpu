"""Measured source-pitch copy experiment with pinned ancestry and hit evidence."""
import json,re,shutil,struct
import lmi_display_v58_policy as prior
checked=prior.checked
KERNEL_SHA='a63c3a995f6a97b957b71183d8c0be0596c9de2a1b9eeaa0fdc584fc15274dc7'
AUDIT_SHA='964745bc6c3de2e4235c224a58f1f625353633b8c082bec0d267293c6d9b945b'
HOST_SHA='8157368d42671fd0de6fc135a3a46e2e70824735ea6d2f8f11c9c7475e6ed8e9'
PRIOR_SHA='2fa338a1b449a9fcb081e64bffb9a8f34693ca56238e15d479d32f948d2411e9'
RANGES=[[5040644,5040784],[5042468,5042732],[5042804,5042840],[5043452,5044072],
        [5044584,5045096],[5045332,5046072],[11387068,11387072],[10354048,10354052],[5072428,5072432]]
def stage(root,out):
    checked(root/'tools/lmi_display_v58_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-display-fast-v61'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-fast-v61-host/result.json',HOST_SHA))
    assert host['result']=='PASS' and host['asan_ubsan'] and host['scenarios']==21 and host['original_compositor_used'] and not host['hardware_tested']
    for report in (audit,host):
        for name,digest in report['sources'].items():checked(root/'tools'/name,digest)
    checked(root/'out/lmi-replaced-gpu-body-audit/result.json',audit['reused_region_audit_sha256'])
    checked(root/'out/lmi-direct-surface-layout/layout.json',audit['surface_layout_sha256'])
    checked(root/'hackios/xnu/files/iokit/Kernel/MiniIOSurface.h',audit['source_class_sha256'])
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    for key in ['abi_entries_preserved','outside_edits_exact','dma_mappings_unchanged','gpu_async_unchanged','touch_unchanged','native_show_queue_record_retained','full_frame_one_copy']:
        assert audit[key]
    assert not any(n in audit['bindings'] for n in ['snprintf','printf','vsnprintf'])
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
    target=out/'display-v61-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-fast-v61-host/result.json',target/'fast-host-check.json')
    meta['display_v61']=meta.pop('display_v58');meta['sha256']=KERNEL_SHA
    meta['display_v61'].update(cpu_compositor_preserved=False,partial_compositor_preserved=True,full_frame_one_copy=True,
        source_pitches=[4544,4608],destination_pitch=4544,
        dma_mappings_unchanged=True,direct_surface_dma=False,native_show_queue_record_retained=True)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def fast_path(log):
    lines=[l for l in log.splitlines() if 'LMI_DPU_FAST' in l]
    found=re.findall(r'(?m)^LMI_DPU_FAST (\d+) (\d+) (\d+)$',log)
    counts=list(map(int,found[0])) if len(found)==len(lines)==1 else None
    stride_lines=[l for l in log.splitlines() if 'LMI_FRAME_STRIDE' in l]
    strides=re.findall(r'(?m)^LMI_FRAME_STRIDE (\d+)$',log)
    stride=int(strides[0]) if len(strides)==len(stride_lines)==1 else None
    markers=['LMI_DPU_PROBE_RETURN restored=1\n','LMI_DPU_FAST ','LMI_FRAME_STRIDE ','LMI_GPU_ASYNC_DRAINED\n','LMI_RAM_ONLY_TIMER_EXPIRED\n']
    order=all(log.count(m)==1 for m in markers) and all(log.index(a)<log.index(b) for a,b in zip(markers,markers[1:]))
    valid=bool(counts is not None and stride is not None and all(0<=n<1<<64 for n in counts) and
        order and counts[0]==counts[1] and 0<counts[0]+counts[2]<1<<64 and 0<=stride<=counts[0] and
        prior.asynchronous(log)['exit_gpu_drain_verified'])
    return dict(counts_valid=valid,fast_frames=counts[0] if counts else None,copy_calls=counts[1] if counts else None,
        ordinary_frames=counts[2] if counts else None,fast_path_exercised=bool(valid and counts[0]>0),
        strided_frames=stride,strided_path_exercised=bool(valid and stride>0),
        direct_surface_dma=False,performance_verified=False)

def observe(log):
    result=prior.observe(log);result['fast_path']=fast_path(log)
    result['qualification_metadata']=qualification_metadata(log)
    stats=result.get('desktop_stats',[]);fast=result['fast_path']
    matching=bool(len(stats)==1 and fast['counts_valid'] and fast['fast_frames']+fast['ordinary_frames']==stats[0]['frames'])
    fast['matches_desktop_frames']=matching
    fast['fast_path_exercised']=bool(fast['fast_path_exercised'] and matching)
    fast['strided_path_exercised']=bool(fast['strided_path_exercised'] and matching)
    result['performance_verified']=False
    return result

def qualification_metadata(log):
    masks=re.findall(r'(?m)^LMI_FRAME_GUARD (\d+)$',log)
    rows=re.findall(r'(?m)^LMI_FRAME_META ((?:\d+ ){9}\d+)$',log)
    lines=[line for line in log.splitlines() if 'LMI_FRAME_GUARD' in line or 'LMI_FRAME_META' in line]
    values=list(map(int,rows[0].split())) if len(rows)==1 else None
    valid=bool(len(masks)==len(rows)==1 and len(lines)==2 and int(masks[0])<128 and
        values and all(0<=v<1<<64 for v in values) and values[5] in (0,1))
    if not valid:return dict(valid=False)
    def signed(v):return v-(1<<32) if v&(1<<31) else v
    def rect(a,b):return [signed(a>>32),signed(a&0xffffffff),signed(b>>32),signed(b&0xffffffff)]
    return dict(valid=True,rejection_mask=int(masks[0]),surface_id=values[0],width=values[1]>>32,height=values[1]&0xffffffff,
        pitch=values[2]>>32,pixel_format=hex(values[2]&0xffffffff),allocation_bytes=values[3]>>32,offset=values[3]&0xffffffff,
        layers_set=values[4],client_backed=bool(values[5]),source=rect(values[6],values[7]),destination=rect(values[8],values[9]),
        scope='First single-layer source metadata, captured once. A zero snapshot can mean no eligible source reached the decoder.')
