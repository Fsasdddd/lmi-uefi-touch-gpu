"""Early PoC maintenance; all v64 DMA/source/queue checks remain required."""
import json,re,shutil
import lmi_display_v64_policy as prior
checked=prior.checked
KERNEL_SHA='0c61da0dda94a0280495d96af94c85edb8b28dea8f068e26b34f96fa885f44e6'
AUDIT_SHA='3d6df4d7d6940b492b296f20a1fdc2c689a190303b6d89c0f0e7fff959b17c6f'
HOST_SHA='47cb4cfdbbd7e3b4d0613b91f2297af59b200f2525492def061a194bf2e667cf'
LINK_SHA='9af0bfc254c3de324df4cb0c34b5bc0dc13b2684db916dc07d5946825fcf53cb'
PRIOR_SHA='ae167f944d92bbf85c985acfc69de366e6ce709ac94d92502e16ae83fa26157b'
def stage(root,out):
    checked(root/'tools/lmi_display_v64_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-display-preclean-v65b'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-preclean-v65-host/result.json',HOST_SHA))
    link=json.loads(checked(root/'out/lmi-display-preclean-v65-link-review/result.json',LINK_SHA))
    assert host['result']=='PASS' and host['scenarios']==33 and host['frozen_pixel_regressions']==21
    assert host['asan_ubsan'] and host['separate_cpu_poc_views'] and len(host['mutations_caught'])==6
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for flag in ['object_reproduced','link_reproduced','placed_sections_verified','hooks_verified',
                 'outside_edits_exact','full_rx_tail_audit','journal_prefix_preserved']:assert link[flag]
    for report in (audit,host):
        for n,d in report['sources'].items():checked(root/'tools'/n,d)
    for report in (audit,link):
        for n,d in report['inputs'].items():checked(root/n,d)
    assert audit['base_sha256']==meta['sha256'] and audit['sha256']==KERNEL_SHA
    assert len(audit['hooks'])==3 and audit['journal_prefix_bytes']==280
    for flag in ['outside_edits_exact','full_rx_segments_scanned','gpu_queue_unchanged','dpu_fences_unchanged',
                 'source_retirement_unchanged','touch_unchanged','preclean_overlap']:assert audit[flag]
    assert not audit['hardware_tested'] and not audit['performance_verified'] and not audit['direct_surface_dma']
    original=baseline.read_bytes();restored=bytearray(raw);assert len(original)==len(raw)
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=original[a:z]
    assert restored==original
    target=out/'display-v65-candidate';assert not target.exists();shutil.copytree(folder,target)
    for path,name in [(root/'out/lmi-display-preclean-v65-host/result.json','preclean-host-check.json'),
                      (root/'out/lmi-display-preclean-v65-link-review/result.json','link-review.json')]:
        shutil.copy2(path,target/name)
    meta['display_v65']=meta.pop('display_v64');meta['sha256']=KERNEL_SHA
    meta['display_v65'].update(preclean_overlap=True,cpu_full_frame_copy=True,
        direct_surface_dma=False,wifi_integrated=False,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta
def preclean(log):
    rows=re.findall(r'(?m)^LMI_DPU_PRECLEAN ((?:\d+ ){5}\d+)$',log)
    lines=[l for l in log.splitlines() if 'LMI_DPU_PRECLEAN' in l]
    values=list(map(int,rows[0].split())) if len(rows)==len(lines)==1 else None
    counts=dict(zip(['prepared','previous_scan_pending','consumed','fallback','failed','clean_ticks'],values or []))
    markers=['LMI_SWAP_FENCE ','LMI_DPU_PRECLEAN ','LMI_GPU_QUEUE\n','LMI_GPU_MAP_BATCH\n','LMI_GPU_ASYNC_DRAINED\n']
    ordered=all(log.count(m)==1 for m in markers) and all(log.index(a)<log.index(b) for a,b in zip(markers,markers[1:]))
    valid=bool(values and all(0<=v<1<<64 for v in values) and ordered and
        0<counts['consumed']<=counts['prepared'] and counts['previous_scan_pending']<=counts['prepared'] and
        counts['fallback']==counts['failed']==0 and counts['clean_ticks']>0)
    fast=prior.observe(log).get('fast_path',{})
    frames=fast['fast_frames']+fast['ordinary_frames'] if fast.get('counts_valid') else None
    return dict(counts_valid=valid,counts=counts,
        matches_desktop_frames=bool(valid and fast.get('counts_valid') and counts['prepared']==frames),
        preclean_exercised=bool(valid and counts['previous_scan_pending']>0),
        scope='Maintenance completed before software scan retirement; does not measure concurrent bus DMA or FPS',
        performance_verified=False)
def observe(log):
    result=prior.observe(log);result['preclean']=preclean(log);return result
def validate_run(observation):
    result=prior.validate_run(observation);part=observation.get('preclean')
    for name in ['counts_valid','matches_desktop_frames','preclean_exercised']:
        if not isinstance(part,dict) or part.get(name) is not True:result['failed_checks'].append('preclean.'+name)
    result['passed']=not result['failed_checks']
    result['scope']='v65 maintenance overlap plus unchanged strict v64 checks; legacy verifier still required'
    return result
