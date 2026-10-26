"""Pin v56 and retain final diagnostics without substituting for spatial proof."""
import json,re,shutil,struct
from lmi_display_v40_policy import validate,checked,KERNEL_SHA as BASE_SHA
KERNEL_SHA='c5e262e6f0843ea78e9d5549f48c57f0165e11c454acaf19d9d6dc55abefb1b3'
AUDIT_SHA='1dc90671af04ea360b51f2e278409c380aa72cb584faffb87f2647e6397a236c'
HOST_SHA='21bed4f12942ca6db148b4287103ed51ae83727bcb87ae8cdc2d94ec924468d1'
DIAGNOSTIC_SHA='e40f87cb6a1caf8d89c135d75c13bdfef2f6675a421ba236ad008a326a0dc8c3'
NATIVE_SHA='d64cf76d3478dc754eba0d9a7c1401ff6222e1c7e5c0096ba054e240128f9ef8'
DESKTOP_SHA='3c3ca824c231b2d7f0c8fe248a2f859f03f7d22d1ae06177fb39afc2e59f30f7'
V54_LOG_SHA='706f448309769fc884ea47cad4087be7fdf300bdb35358f8ff5d61e9ee29a3a5'
ALLOWED=[(11386880,11403264),(10353136,10353140),(4574416,4574420),
         (13588952,13588960),(13964696,13964704),(13964712,13964720)]

def branch(raw,at,pc,kind):
    word=struct.unpack_from('<I',raw,at)[0];imm=word&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    assert word&0xfc000000==kind
    return pc+imm*4

def stage(root,out):
    checked(root/'tools/lmi_display_v55_policy.py','94e5c03cff5d4ad96731b49f8f66ce6c30d584b292a40add2ce8afd8cf1dde17')
    sealed,meta=validate(root)
    import lmi_display_v54_policy
    evidence=checked(root/'out/lmi-checkpoint-63-ios-probe-test-display-v54-desktop-180/checkpoint-63.log',V54_LOG_SHA).decode()
    prior=lmi_display_v54_policy.observe(evidence)
    assert prior['diagnostic_complete'] and 5 in prior['geometry_matching_variants']
    measured=[r for r in prior['pattern_results'] if r['variant']==5]
    assert len(measured)==5 and all(all(int(a,16)^int(b,16)==0x484aa7cb for a,b in zip(r['bypass_crc'],r['scaled_crc'])) for r in measured)
    folder=root/'out/lmi-display-probe-v56f'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-dma-host-v56/result.json',HOST_SHA))
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==BASE_SHA
    assert all(audit[k] for k in ('layout_unchanged','original_source_bytes_exact','runtime_outside_extension_exact','automatic_pattern_probe'))
    assert audit['register_writes'] and audit['desktop_pipeline'] and audit['conditional_desktop_enable']
    assert audit['experimental_color_normalization'] and not audit['bypass_pixel_equivalence']
    assert host['v50_refusal_reproduced']
    assert host['result']=='PASS' and host['asan_ubsan'] and not host['hardware_tested']
    for name,digest in audit['sources'].items():
        checked(root/'tools'/name,digest);checked(folder/name,digest)
    for name,digest in host['sources'].items():checked(root/'tools'/name,digest)
    checked(root/'tools/build-lmi-display-v56.py',audit['builder_sha256'])
    checked(folder/'compositor-layout.json',audit['compositor_layout_sha256'])
    for report_path,expected in [('out/lmi-display-probe-v56-host/result.json',DIAGNOSTIC_SHA),
                                 ('out/lmi-display-v56-startup-host/result.json',NATIVE_SHA),
                                 ('out/lmi-display-v56-desktop-host/result.json',DESKTOP_SHA)]:
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
    meta['sha256']=KERNEL_SHA;meta['display_v56']=meta.pop('display_v40')
    meta['display_v56'].update(readonly=False,automatic_pattern_probe=True,desktop_pipeline=True,conditional_desktop_enable=True,experimental_color_normalization=True,bypass_pixel_equivalence=False,
        spatial_scaler_verified=False,dma_verified=False,return_restoration=True)
    target=out/'display-v56-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-dma-host-v56/result.json',target/'dma-host-check.json')
    shutil.copy2(root/'out/lmi-display-probe-v56-host/result.json',target/'probe-host-check.json')
    shutil.copy2(root/'out/lmi-display-v56-startup-host/result.json',target/'startup-host-check.json')
    shutil.copy2(root/'out/lmi-display-v56-desktop-host/result.json',target/'desktop-host-check.json')
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta



def observe(log):
    from lmi_display_v55_policy import observe as prior_observe
    costs=[]
    def canonical(m):
        n,sub,done,dt,cost=map(int,m.groups())
        costs.append(dict(frames=n,submitted=sub,completed=done,ticks=dt,cache_submit_ticks=cost))
        return f'LMI_DPU_DESKTOP n={n} sub={sub} done={done} dt={dt}'
    converted=re.sub(r'(?m)^LMI_DPU_DESKTOP (\d+) (\d+) (\d+) (\d+) (\d+)$',canonical,log)
    result=prior_observe(converted)
    candidates=[l for l in log.splitlines() if 'LMI_DPU_DESKTOP' in l]
    timing_ok=len(costs)==len(candidates)==1 and 0<costs[0]['cache_submit_ticks']<=costs[0]['ticks']
    result['desktop_pipeline_enabled']=bool(result['desktop_pipeline_enabled'] and timing_ok)
    result['desktop_average_fps']=result['desktop_average_fps'] if result['desktop_pipeline_enabled'] else None
    result['cache_submit_timing_valid']=bool(timing_ok)
    result['cache_submit_samples']=costs
    result['cache_submit_us_per_frame']=(costs[0]['cache_submit_ticks']/19.2/costs[0]['frames'] if result['desktop_pipeline_enabled'] else None)
    result['timing_scope']='CPU cache clean plus guarded DPU kickoff; excludes asynchronous scanout, compositor and GPU rendering'
    return result
