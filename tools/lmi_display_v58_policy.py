"""Bind async GPU code to the already qualified v57 display/frequency base."""
import json,re,shutil,struct
import lmi_display_v57_policy as prior
KERNEL_SHA='52068a7d3c30af9cbbaea89cf906f61848c607f82d3e3bc7a7a35bdc1f14c0ea'
# Filled from the completed, immutable build and host reports before staging.
AUDIT_SHA='6eaa7689f2b7725c8a5ddbc70d9904e99c17982821722ea80dbfe3d50c4657ec'
HOST_SHA='b55e6cfd1db14aa623b1297ad7bfe8f16f8aa1066e285d220c70c8b10f670efa'
PRIOR_SHA='d4ccf285f94c3cd8554e0090c6f4bc680e87ae39accbbE16285e0f5f2d71ed77'.lower()
checked=prior.checked
def stage(root,out):
    checked(root/'tools/lmi_display_v57_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-gpu-async-v58h'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-gpu-async-v58-host/result.json',HOST_SHA))
    assert host['result']=='PASS' and host['asan_ubsan'] and host['scenarios']==41 and not host['hardware_tested']
    for report in (audit,host):
        for name,digest in report['sources'].items():checked(root/'tools'/name,digest)
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    assert audit['baseline_reproduced'] and audit['outside_edits_exact'] and audit['single_outstanding']
    assert audit['submission_asynchronous'] and audit['bytes']==5048 and audit['capacity']==5060
    assert audit['timer_cleanup']=='0xfffffff007ae0448'
    assert audit['timer_wrapper']=='0xfffffff0074da624'
    original=baseline.read_bytes();assert len(raw)==len(original)
    ranges=audit['allowed_file_ranges']
    assert len(ranges)==18 and ranges[0]==[5069960,5075008] and ranges[-1]==[4574416,4574420]
    assert all(b-a==4 for a,b in ranges[1:])
    check=bytearray(raw)
    for a,b in ranges:
        assert 0<=a<b<=len(raw);check[a:b]=original[a:b]
    assert check==original
    target=out/'display-v58-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-gpu-async-v58-host/result.json',target/'async-host-check.json')
    meta['display_v58']=meta.pop('display_v57');meta['sha256']=KERNEL_SHA
    meta['display_v58'].update(async_gpu=True,single_outstanding=True,gpu_exit_drain=True,cpu_compositor_preserved=True)
    meta['lmi_gpu_desktop'].update(base_source_sha256=meta['lmi_gpu_desktop']['source_sha256'],
        source='tools/lmi-gpu-desktop-v58.c',source_sha256=audit['sources']['lmi-gpu-desktop-v58.c'],asynchronous=True)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def asynchronous(log):
    faults=['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD']
    # Only the return wrapper emits this, after native SMP/DPU cleanup and
    # exact GPU idle+scratch completion. Missing evidence never implies idle.
    marker='LMI_GPU_ASYNC_DRAINED\n'
    drained=log.count(marker)==1 and not any(v in log for v in faults)
    restored=log.count('LMI_DPU_PROBE_RETURN restored=1\n')==1
    expired=log.count('LMI_RAM_ONLY_TIMER_EXPIRED\n')==1
    order=drained and restored and expired and log.index('LMI_DPU_PROBE_RETURN restored=1\n')<log.index(marker)<log.index('LMI_RAM_ONLY_TIMER_EXPIRED\n')
    return dict(exit_gpu_drain_verified=bool(order),fault_held=any(v in log for v in faults),
        submission_overlap_measured=False,performance_verified=False)

def observe(log):
    result=prior.observe(log);result['async_gpu']=asynchronous(log)
    result['performance_verified']=False
    return result
