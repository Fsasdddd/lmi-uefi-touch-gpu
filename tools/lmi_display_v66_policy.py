"""Mandatory boot-only CP copy qualification, preserving all v65 admission."""
import json,re,shutil
import lmi_display_v65_policy as prior
checked=prior.checked
KERNEL_SHA='64ff409c50ca8deccef195ac787227c4dce7f0720934b64f35fa9f7f372f84c1'
AUDIT_SHA='021ab854a37fc5551abe0af5d6c928f357e48b8e64dfd4b78134731d8ce620bd'
HOST_SHA='ad9000e2c49223aa693c292953aaf3fe046a6ac2137cf6df19c9e52425756014'
LINK_SHA='d802644a6248eaec1f5a41fd44d79c83dc6f861f32b6f8ea58bd37d3716cc6d2'
PRIOR_SHA='77c093621ff5b1be1f6930cba2387d2729959ae3c07858d864008738cce7a024'
def stage(root,out):
    checked(root/'tools/lmi_display_v65_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-gpu-copy-v66c'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-gpu-copy-v66-host/result.json',HOST_SHA))
    link=json.loads(checked(root/'out/lmi-gpu-copy-v66-link-review/result.json',LINK_SHA))
    assert host['result']=='PASS' and host['scenarios']==25 and len(host['mutations_caught'])==8
    for flag in ['asan_ubsan','actual_v64_backend','separate_cpu_dma_views','independent_packet_decode','static_analysis']:assert host[flag]
    assert host['post_probe_jobs']==80 and not host['desktop_gpu_copy'] and not host['hardware_tested']
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for flag in ['object_reproduced','link_reproduced','placed_sections_verified','hooks_verified','outside_edits_exact',
                 'full_rx_tail_audit','obsolete_entry_disabled','loaded_entry_pointer_preserved',
                 'conditional_service_gate_verified','original_failure_block_preserved','no_writable_globals']:assert link[flag]
    for report in (audit,host):
        for n,d in report['sources'].items():checked(root/'tools'/n,d)
    for report in (audit,link):
        for n,d in report['inputs'].items():checked(root/n,d)
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    for flag in ['outside_edits_exact','full_rx_segments_scanned','boot_only_copy_probe','original_failure_block_preserved',
                 'display_copy_unchanged','source_retirement_unchanged','touch_unchanged']:assert audit[flag]
    assert not audit['desktop_gpu_copy'] and not audit['hardware_tested'] and not audit['performance_verified']
    original=baseline.read_bytes();restored=bytearray(raw);assert len(original)==len(raw)
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=original[a:z]
    assert restored==original
    target=out/'display-v66-candidate';assert not target.exists();shutil.copytree(folder,target)
    for path,name in [(root/'out/lmi-gpu-copy-v66-host/result.json','copy-host-check.json'),
                      (root/'out/lmi-gpu-copy-v66-link-review/result.json','link-review.json')]:shutil.copy2(path,target/name)
    meta['display_v66']=meta.pop('display_v65');meta['sha256']=KERNEL_SHA
    meta['display_v66'].update(boot_only_copy_probe=True,copy_probe_bytes=1020,desktop_gpu_copy=False,
        cpu_full_frame_copy=True,direct_surface_dma=False,wifi_integrated=False,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta
def copy_probe(log):
    rows=re.findall(r'(?m)^LMI_CP_COPY ((?:[0-9]+ ){5}[0-9]+)$',log)
    lines=[line for line in log.splitlines() if 'LMI_CP_COPY' in line]
    values=list(map(int,rows[0].split())) if len(rows)==len(lines)==1 else None
    counts=dict(zip(['bytes','ring_end','flush_marker','write_marker','mismatches','elapsed_ticks'],values or []))
    valid=bool(values and all(0<=v<1<<64 for v in values) and values[0]==1020 and values[1]==90 and values[4]==0 and values[5]>0)
    markers=['LMI_GPU_DESKTOP_READY\n','LMI_CP_COPY ','LMI_GPU_DESKTOP_RESULT\n','LMI_GPU_ASYNC_DRAINED\n']
    ordered=all(log.count(m)==1 for m in markers) and all(log.index(a)<log.index(b) for a,b in zip(markers,markers[1:]))
    service=re.findall(r'(?m)^LMI_GPU_DESKTOP_RESULT\n([0-9a-f]{16})$',log)==['0000000000000001']
    return dict(counts_valid=valid,counts=counts,
        fresh_completion_verified=bool(valid and values[2]==0x660c0de6 and values[3]==0x660c0de7),
        before_service_result=bool(valid and ordered and service),
        scope='One 1020-byte boot-only GPU copy; does not replace desktop CPU copying or measure FPS/bandwidth',
        desktop_gpu_copy=False,performance_verified=False)
def observe(log):
    result=prior.observe(log);result['copy_probe']=copy_probe(log);return result
def validate_run(observation):
    result=prior.validate_run(observation);part=observation.get('copy_probe')
    for name in ['counts_valid','fresh_completion_verified','before_service_result']:
        if not isinstance(part,dict) or part.get(name) is not True:result['failed_checks'].append('copy_probe.'+name)
    result['passed']=not result['failed_checks']
    result['scope']='v66 CP copy proof plus all strict v65 checks; legacy verifier still required'
    return result
