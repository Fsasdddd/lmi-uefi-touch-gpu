"""Pin the automatic spatial DMA/scaler probe, separate from desktop scanout."""
import json,re,shutil,struct
from lmi_display_v40_policy import validate,checked,KERNEL_SHA as BASE_SHA
KERNEL_SHA='3057e8ddc9e5a252506cb360d56f4c42b84c7b4f7cd0ae5838931d4a76e39ef0'
AUDIT_SHA='20014fdc893c0730366a836b20e759b73184d1c5af4a5c1e107b29cbca561104'
HOST_SHA='01d8e0b8a57a41dbd577e6762c241d4b43078284f6f8dbf0abfeb9c738cb939e'
ALLOWED=[(11386880,11403264),(10353136,10353140),(4574416,4574420),
         (13588952,13588960),(13964696,13964704),(13964712,13964720)]

def branch(raw,at,pc,kind):
    word=struct.unpack_from('<I',raw,at)[0];imm=word&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    assert word&0xfc000000==kind
    return pc+imm*4

def stage(root,out):
    sealed,meta=validate(root);folder=root/'out/lmi-display-probe-v46'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-dma-host-v46/result.json',HOST_SHA))
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==BASE_SHA
    assert all(audit[k] for k in ('layout_unchanged','original_source_bytes_exact','runtime_outside_extension_exact','automatic_pattern_probe'))
    assert audit['register_writes'] and not audit['desktop_pipeline']
    assert host['result']=='PASS' and host['asan_ubsan'] and not host['hardware_tested']
    for name,digest in audit['sources'].items():
        checked(root/'tools'/name,digest);checked(folder/name,digest)
    for name,digest in host['sources'].items():checked(root/'tools'/name,digest)
    checked(root/'tools/build-lmi-display-v46.py',audit['builder_sha256'])
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
    meta['sha256']=KERNEL_SHA;meta['display_v46']=meta.pop('display_v40')
    meta['display_v46'].update(readonly=False,automatic_pattern_probe=True,desktop_pipeline=False,
        spatial_scaler_verified=False,dma_verified=False,return_restoration=True)
    target=out/'display-v46-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-dma-host-v46/result.json',target/'dma-host-check.json')
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def observe(log):
    rows=[];malformed=[];states=[];preflight=[]
    row=re.compile(r'LMI_DPU_PROBE stage=(\d+) ok=([01]) expected=([0-9a-f]+) actual=([0-9a-f]+) ticks=(\d+)')
    for line in log.splitlines():
        if line.startswith('LMI_DPU_PROBE stage='):
            m=row.fullmatch(line)
            if not m:malformed.append(line);continue
            stage,ok,expected,actual,ticks=m.groups()
            rows.append(dict(stage=int(stage),ok=int(ok),expected=int(expected,16),actual=int(actual,16),ticks=int(ticks)))
        if line.startswith('LMI_DPU_PROBE_STATE '):states.append(line)
        if line.startswith('LMI_DPU_PREFLIGHT'):preflight.append(line)
    expected_order=[1,2,10,11,10,11,3,12,13,12,13,4,5,6]
    restored=log.splitlines().count('LMI_DPU_PROBE_RETURN restored=1')==1
    valid=([r['stage'] for r in rows]==expected_order and all(r['ok'] for r in rows) and
        not malformed and not states and not preflight and restored and 'LMI_DPU_PROBE_REFUSED' not in log and
        'LMI_DPU_PROBE_RETURN restored=0' not in log and
        log.splitlines().count('LMI_DPU_PROBE_BEGIN automatic=1 desktop_pipeline=0')==1 and
        'LMI_SMP_OTHER_CORES_OFF' in log and
        log.index('LMI_SMP_OTHER_CORES_OFF')<log.index('LMI_DPU_PROBE_RETURN restored=1'))
    if valid:
        ref0,ref1=rows[6]['expected'],rows[6]['actual']
        valid=ref0!=ref1 and all(r['expected']==r['actual']==expected for r,expected in zip(
            [r for r in rows if r['stage'] in (10,11,12,13)], [ref0,ref1,ref1,ref0]*2))
        valid=valid and all(r['expected']==r['actual']==8 for r in rows[-2:])
    return dict(probe_result='SPATIAL_DMA_SCALER_VERIFIED' if valid else 'NOT_VERIFIED',
        probe_samples=rows,probe_malformed=malformed,probe_states=states,preflight_trace=preflight,return_restored=restored,
        dma_verified=bool(valid),hardware_scaling_verified=bool(valid),
        desktop_pipeline_enabled=False,performance_verified=False)
