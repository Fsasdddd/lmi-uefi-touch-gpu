"""Pin v55 and retain final diagnostics without substituting for spatial proof."""
import json,re,shutil,struct
from lmi_display_v40_policy import validate,checked,KERNEL_SHA as BASE_SHA
KERNEL_SHA='ea3a3cb1ad5d6a6edd71464806152b1ac0da42c4c0cd9bb61a656580ff705924'
AUDIT_SHA='3cd1299bf2195c6ff996cf625b62975821d31a39aa1dff22eadd4376dc783bbd'
HOST_SHA='335b5c486a747ede6dc4498756b43456a16412e94b0a2fac486ff83c1560eb07'
DIAGNOSTIC_SHA='56277dd7258312b07782937a4cdb8bb0c7fe47669140f2b01f53af764b9015e1'
NATIVE_SHA='0e5736afa5c40882194c9f816e334941c0794b5a82da3b7fc7df447e988615d8'
DESKTOP_SHA='3dafcfe92e7014c5f80b2fdb6c4d7e00a5da0876fecef0837b838af6e92c844e'
V54_LOG_SHA='706f448309769fc884ea47cad4087be7fdf300bdb35358f8ff5d61e9ee29a3a5'
ALLOWED=[(11386880,11403264),(10353136,10353140),(4574416,4574420),
         (13588952,13588960),(13964696,13964704),(13964712,13964720)]

def branch(raw,at,pc,kind):
    word=struct.unpack_from('<I',raw,at)[0];imm=word&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    assert word&0xfc000000==kind
    return pc+imm*4

def stage(root,out):
    sealed,meta=validate(root)
    import lmi_display_v54_policy
    evidence=checked(root/'out/lmi-checkpoint-63-ios-probe-test-display-v54-desktop-180/checkpoint-63.log',V54_LOG_SHA).decode()
    prior=lmi_display_v54_policy.observe(evidence)
    assert prior['diagnostic_complete'] and 5 in prior['geometry_matching_variants']
    measured=[r for r in prior['pattern_results'] if r['variant']==5]
    assert len(measured)==5 and all(all(int(a,16)^int(b,16)==0x484aa7cb for a,b in zip(r['bypass_crc'],r['scaled_crc'])) for r in measured)
    folder=root/'out/lmi-display-probe-v55e'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-dma-host-v55/result.json',HOST_SHA))
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==BASE_SHA
    assert all(audit[k] for k in ('layout_unchanged','original_source_bytes_exact','runtime_outside_extension_exact','automatic_pattern_probe'))
    assert audit['register_writes'] and audit['desktop_pipeline'] and audit['conditional_desktop_enable']
    assert audit['experimental_color_normalization'] and not audit['bypass_pixel_equivalence']
    assert host['v50_refusal_reproduced']
    assert host['result']=='PASS' and host['asan_ubsan'] and not host['hardware_tested']
    for name,digest in audit['sources'].items():
        checked(root/'tools'/name,digest);checked(folder/name,digest)
    for name,digest in host['sources'].items():checked(root/'tools'/name,digest)
    checked(root/'tools/build-lmi-display-v55.py',audit['builder_sha256'])
    checked(folder/'compositor-layout.json',audit['compositor_layout_sha256'])
    for report_path,expected in [('out/lmi-display-probe-v55-host/result.json',DIAGNOSTIC_SHA),
                                 ('out/lmi-display-v55-startup-host/result.json',NATIVE_SHA),
                                 ('out/lmi-display-v55-desktop-host/result.json',DESKTOP_SHA)]:
        report=json.loads(checked(root/report_path,expected))
        assert report['result']=='PASS' and report['asan_ubsan'] and not report['hardware_tested']
        for name,digest in report['sources'].items():checked(root/'tools'/name,digest)
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
    meta['sha256']=KERNEL_SHA;meta['display_v55']=meta.pop('display_v40')
    meta['display_v55'].update(readonly=False,automatic_pattern_probe=True,desktop_pipeline=True,conditional_desktop_enable=True,experimental_color_normalization=True,bypass_pixel_equivalence=False,
        spatial_scaler_verified=False,dma_verified=False,return_restoration=True)
    target=out/'display-v55-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-dma-host-v55/result.json',target/'dma-host-check.json')
    shutil.copy2(root/'out/lmi-display-probe-v55-host/result.json',target/'probe-host-check.json')
    shutil.copy2(root/'out/lmi-display-v55-startup-host/result.json',target/'startup-host-check.json')
    shutil.copy2(root/'out/lmi-display-v55-desktop-host/result.json',target/'desktop-host-check.json')
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta


def observe(log):
    lines=log.splitlines();rows=[];bad=[];stats=[]
    pattern=re.compile(r'LMI_DPU_PROBE stage=(\d+) ok=([01]) exp=([0-9a-f]+) got=([0-9a-f]+) ticks=(\d+)')
    stat=re.compile(r'LMI_DPU_DESKTOP n=(\d+) sub=(\d+) done=(\d+) dt=(\d+)')
    for i,line in enumerate(lines):
        if 'LMI_DPU_PROBE stage=' in line:
            m=pattern.fullmatch(line)
            if not m:bad.append(line);continue
            s,o,e,a,t=m.groups();rows.append(dict(stage=int(s),ok=bool(int(o)),expected=int(e,16),actual=int(a,16),ticks=int(t),position=i))
        if 'LMI_DPU_DESKTOP n=' in line:
            m=stat.fullmatch(line)
            if not m:bad.append(line);continue
            stats.append(dict(zip(('frames','submitted','completed','ticks'),map(int,m.groups())),position=i))
    stages=[1,2]
    for n in range(5):stages.extend(1000+n*10+k for k in range(9))
    stages += [90,91,9000]
    markers=[[i for i,l in enumerate(lines) if l==m] for m in
        ['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_BEGIN live=1','LMI_DPU_EXPERIMENTAL','LMI_DPU_PROBE_RETURN restored=1']]
    complete=(not bad and [r['stage'] for r in rows]==stages and all(len(x)==1 for x in markers) and
        markers[0][0]<markers[1][0]<rows[0]['position']<rows[-1]['position']<markers[2][0]<markers[3][0] and
        all(r['ok'] for r in rows) and not any(m in log for m in
        ['LMI_DPU_PROBE_RETURN restored=0','LMI_DPU_REFUSAL','LMI_DPU_FALLBACK','LMI_DPU_DESKTOP enabled=1']))
    if complete:
        complete=rows[0]['expected']==rows[0]['actual']==rows[0]['ticks']==0
        # The native ABI writes raw expected XOR bias, rather than changing the
        # evidence or claiming exact bypass colors. Keep independent endpoint
        # and prior measured reference checks in addition to the live sequence.
        references=[(0x484aa7cb,0xf874a603),(0x61f329b8,0xd303a7bd),(0x8e26faa5,0x3cd674a0),
                    (0xb4f9e37c,0x06096d79),(0x5b2c3061,0xe9dcbe64)]
        for n,(a,b) in enumerate(references):
            g=rows[2+9*n:2+9*n+9];refs=[a,b,b,a]
            valid=all(r['expected']==r['actual']==ref for r,ref in zip(g[:4],refs))
            valid=valid and all(r['expected']==r['actual']==(ref^0x484aa7cb) for r,ref in zip(g[4:8],refs))
            valid=valid and g[8]['expected']==a and g[8]['actual']==b and g[8]['ticks']==(4 if n==0 else n-1)
            complete=complete and valid
        total,eligible,final=rows[-3:]
        complete=bool(complete and total['expected']==total['actual']==40 and total['ticks']==0 and
            eligible['expected']==0x484aa7cb and eligible['actual']==40 and eligible['ticks']==0 and
            final['expected']==40 and final['actual']==2 and final['ticks']==0)
    stats_ok=(len(stats)==1 and stats[0]['frames']>0 and stats[0]['submitted']==40+stats[0]['frames'] and
        stats[0]['completed'] in [stats[0]['submitted']-1,stats[0]['submitted']] and stats[0]['ticks']>0 and
        all(len(x)==1 for x in markers) and markers[2][0]<stats[0]['position']<markers[3][0])
    desktop=bool(complete and stats_ok)
    return dict(probe_result='NORMALIZED_EXPERIMENT_QUALIFIED' if complete else 'NOT_QUALIFIED',
        normalized_experiment_qualified=bool(complete),hardware_tested=True,
        hardware_scaling_verified=False,bypass_pixel_equivalence=False,performance_verified=False,
        desktop_pipeline_enabled=desktop,desktop_experimental=True,crc_bias='0x484aa7cb',
        desktop_average_fps=(stats[0]['frames']*19200000/stats[0]['ticks'] if desktop else None),
        return_restored=len(markers[3])==1,probe_samples=rows,desktop_stats=stats,malformed=bad)

