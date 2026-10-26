"""Pin the automatic spatial DMA/scaler probe, separate from desktop scanout."""
import json,re,shutil,struct
from lmi_display_v40_policy import validate,checked,KERNEL_SHA as BASE_SHA
KERNEL_SHA='ac96daf2272404804aba78b9a6b75c170cbbf1359cf34e86c67cfd8fbd9f2edd'
AUDIT_SHA='740e916abd12be3f63beac9b12b38cf25fa0878022840f6f601c7746b70d9e6e'
HOST_SHA='5cdfec7cc43f62ce313321ffd30a810d236772d00da3a3d211d197aaa2d19c17'
COMPOSITOR_SHA='3e372fb08e2a460bedef358cf8d65ae8934f8e3dc535c63872d1c6b84cacd5b3'
ALLOWED=[(11386880,11403264),(10353136,10353140),(4574416,4574420),
         (13588952,13588960),(13964696,13964704),(13964712,13964720)]

def branch(raw,at,pc,kind):
    word=struct.unpack_from('<I',raw,at)[0];imm=word&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    assert word&0xfc000000==kind
    return pc+imm*4

def stage(root,out):
    sealed,meta=validate(root);folder=root/'out/lmi-display-probe-v47p'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-dma-host-v47-final/result.json',HOST_SHA))
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==BASE_SHA
    assert all(audit[k] for k in ('layout_unchanged','original_source_bytes_exact','runtime_outside_extension_exact','automatic_pattern_probe'))
    assert audit['register_writes'] and audit['desktop_pipeline'] and audit['conditional_desktop_enable']
    assert host['result']=='PASS' and host['asan_ubsan'] and not host['hardware_tested']
    for name,digest in audit['sources'].items():
        checked(root/'tools'/name,digest);checked(folder/name,digest)
    for name,digest in host['sources'].items():checked(root/'tools'/name,digest)
    checked(root/'tools/build-lmi-display-v47.py',audit['builder_sha256'])
    checked(folder/'compositor-layout.json',audit['compositor_layout_sha256'])
    composite=json.loads(checked(root/'out/lmi-display-compositor-host-v47-final/result.json',COMPOSITOR_SHA))
    assert composite['result']=='PASS' and composite['asan_ubsan'] and not composite['hardware_tested']
    for name,digest in composite['sources'].items():checked(root/'tools'/name,digest)
    old=(sealed/'mach.development.bcm2837').read_bytes();assert len(raw)==len(old)
    assert audit['allowed_file_ranges']==[list(r) for r in ALLOWED]
    check=bytearray(raw)
    for lo,hi in ALLOWED:check[lo:hi]=old[lo:hi]
    assert check==old
    assert raw[0xb42fe0:0xb43000]==bytes(32)
    assert branch(raw,10353136,0xfffffff0079e39f0,0x14000000)==int(audit['observer'],16)
    assert branch(raw,4574416,0xfffffff007460cd0,0x94000000)==int(audit['cleanup'],16)
    trampoline=int(audit['trampoline'],16);at=11386880+trampoline-0xfffffff007ae0000
    assert struct.unpack_from('<I',raw,at)[0]==0xd10703ff
    assert branch(raw,at+4,trampoline+4,0x14000000)==0xfffffff0079e39f4
    meta['sha256']=KERNEL_SHA;meta['display_v47']=meta.pop('display_v40')
    meta['display_v47'].update(readonly=False,automatic_pattern_probe=True,desktop_pipeline=True,conditional_desktop_enable=True,
        spatial_scaler_verified=False,dma_verified=False,return_restoration=True)
    target=out/'display-v47-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-dma-host-v47-final/result.json',target/'dma-host-check.json')
    shutil.copy2(root/'out/lmi-display-compositor-host-v47-final/result.json',target/'compositor-host-check.json')
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def observe(log):
    rows=[];bad=[];refusals=[];stats=[]
    row=re.compile(r'LMI_DPU_PROBE stage=(\d+) ok=([01]) exp=([0-9a-f]+) got=([0-9a-f]+) ticks=(\d+)')
    stat=re.compile(r'LMI_DPU_DESKTOP n=(\d+) sub=(\d+) done=(\d+) dt=(\d+)')
    lines=log.splitlines()
    for line in lines:
        if line.startswith('LMI_DPU_PROBE stage='):
            m=row.fullmatch(line)
            if not m:bad.append(line);continue
            stage,ok,expected,actual,ticks=m.groups()
            rows.append(dict(stage=int(stage),ok=int(ok),expected=int(expected,16),actual=int(actual,16),ticks=int(ticks)))
        if line.startswith('LMI_DPU_REFUSAL'):refusals.append(line)
        if line.startswith('LMI_DPU_DESKTOP n='):
            m=stat.fullmatch(line)
            if not m:bad.append(line);continue
            stats.append(dict(zip(('frames','submitted','completed','ticks'),map(int,m.groups()))))
    restored=lines.count('LMI_DPU_PROBE_RETURN restored=1')==1
    off=lines.count('LMI_SMP_OTHER_CORES_OFF')==1
    valid=([r['stage'] for r in rows]==[1,2,10,11,10,11,3,12,13,12,13,4,7] and
        all(r['ok'] for r in rows) and not bad and not refusals and restored and off and
        lines.count('LMI_DPU_PROBE_BEGIN live=1')==1 and
        'LMI_DPU_PROBE_RETURN restored=0' not in log and
        log.index('LMI_SMP_OTHER_CORES_OFF')<log.index('LMI_DPU_PROBE_RETURN restored=1'))
    if valid:
        ref0,ref1=rows[6]['expected'],rows[6]['actual']
        valid=ref0!=ref1 and all(r['expected']==r['actual']==expected for r,expected in zip(
            [r for r in rows if r['stage'] in (10,11,12,13)], [ref0,ref1,ref1,ref0]*2))
        valid=valid and rows[-1]['expected']==rows[-1]['actual']==8
    enabled=lines.count('LMI_DPU_DESKTOP enabled=1')==1
    if enabled:
        enabled=0<=log.find('LMI_DPU_PROBE stage=7 ok=1')<log.index('LMI_DPU_DESKTOP enabled=1')
    consistent=bool(stats) and all(s['submitted']==8+s['frames'] and
        s['completed'] in (s['submitted']-1,s['submitted']) and s['ticks']>0 for s in stats)
    if consistent:
        consistent=all(b['frames']>=a['frames'] and b['submitted']>=a['submitted'] and
            b['completed']>=a['completed'] and b['ticks']>=a['ticks'] for a,b in zip(stats,stats[1:]))
    desktop=bool(valid and enabled and consistent and stats[-1]['frames']>0 and 'LMI_DPU_FALLBACK' not in log)
    return dict(probe_result='SPATIAL_DMA_SCALER_VERIFIED' if valid else 'NOT_VERIFIED',
        probe_samples=rows,malformed=bad,refusals=refusals,return_restored=restored,
        dma_verified=bool(valid),hardware_scaling_verified=bool(valid),desktop_stats=stats,
        desktop_pipeline_enabled=desktop,performance_verified=False,
        desktop_average_fps=(stats[-1]['frames']*19200000/stats[-1]['ticks'] if desktop else None))
