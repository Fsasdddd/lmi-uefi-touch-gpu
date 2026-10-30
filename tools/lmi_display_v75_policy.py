"""v75 rendering poll statistics, with complete unchanged v73 safety checks."""
import json,shutil
import lmi_display_v73_policy as prior
from lmi_display_v71_policy import record
checked=prior.checked
KERNEL_SHA='82da06497828d0f1956c06bc26a30b0a9055fc97169a0f95411c5a8c0c1c63d0'
AUDIT_SHA='f0754a0d166a1fb306162fcef18397c2be0f649e2325ce683a707793acb78ada'
HOST_SHA='120c2d4a97f0cdd9358facb8d618f1c692e0666ba57c32b212c0dff6fdead1b8'
LINK_SHA='1d48f21871701d1c5297b89b660c50de46c6d5086a418177647bbbb09b0108f5'
PRIOR_SHA='8cf330b0787fe9c4a8aa393e3d5a6237f07bee3ec97444f6015dae273b961ee3'
def stage(root,out):
    checked(root/'tools/lmi_display_v73_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-render-wait-v75';raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host_path=root/'out/lmi-render-wait-v75-host/result.json';link_path=root/'out/lmi-render-wait-v75c-link-review/result.json'
    host=json.loads(checked(host_path,HOST_SHA));link=json.loads(checked(link_path,LINK_SHA))
    assert host['result']=='PASS' and host['scenarios']==16 and len(host['mutations_caught'])==5 and host['concurrent_writers']==4
    for name in ['asan_ubsan','tsan','static_analysis','frozen_timing_prefix_preserved','original_delay_arguments_verified',
        'allocation_and_null_state_verified','histogram_boundaries_and_wrap_verified','stop_before_logging']:assert host[name]
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for name in ['object_reproduced','link_reproduced','independent_instruction_decode','hooks_verified','free_tails_only',
        'no_writable_globals','v73_timing_code_exact','original_gpu_code_exact','v72_touch_preserved','outside_edits_exact',
        'dpu_poll_loop_and_timeout_exact','original_delay_bound','no_new_irq_masking_or_locks',
        'native_poll_arguments_and_lock_bracket_verified','atomic_counters_decoded']:assert link[name]
    for report in [audit,host,link]:
        for name,digest in report['inputs'].items():checked(root/name,digest)
    original=baseline.read_bytes();restored=bytearray(raw)
    assert audit['base_sha256']==meta['sha256']==prior.KERNEL_SHA and audit['sha256']==KERNEL_SHA
    assert len(raw)==len(original) and len(audit['hooks'])==3
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=original[a:z]
    assert restored==original and audit['native_gpu_poll_us']==50 and audit['original_gpu_poll_us']==200
    for name in ['append_only_journal','atomic_delay_metrics','original_dpu_poll_exact','v73_timing_code_preserved',
        'v72_touch_preserved','original_gpu_code_preserved','original_fences_and_timeout_preserved']:assert audit[name]
    assert not audit['hot_path_logging'] and not audit['hardware_tested'] and not audit['performance_verified']
    target=out/'display-v75-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(host_path,target/'render-host-review.json');shutil.copy2(link_path,target/'render-link-review.json')
    meta['display_v75']=meta.pop('display_v73');meta['sha256']=KERNEL_SHA
    meta['display_v75'].update(native_gpu_fence_poll_us=50,previous_native_gpu_fence_poll_us=200,
        concurrent_render_wait_statistics=True,v74_busy_spin_included=False,
        all_prior_gpu_display_safety_required=True,performance_change=True,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta
def render_delay(log):
    values=record(log,'LMI_RENDER_DELAY',9);other=record(log,'LMI_RENDER_DELAY_OTHER',1);valid=False
    if values:
        count,total,maximum,*bins=values
        edges=(19200,76800,160000,320000,640000);lower=(0,19201,76801,160001,320001,640001);upper=(*edges,maximum)
        minimum=sum(n*lo for n,lo in zip(bins,lower));ceiling=sum(n*min(hi,maximum) for n,hi in zip(bins,upper))
        maxbin=next((i for i,edge in enumerate(edges) if maximum<=edge),5)
        valid=(sum(bins)==count and minimum<=total<=ceiling and
            ((count==0 and total==maximum==0) or (count>0 and maximum<=total<=count*maximum and bins[maxbin]>0 and not any(bins[maxbin+1:]))))
    ordered=(log.count('LMI_TIME_COUNTS ')==1 and log.count('LMI_RENDER_DELAY ')==1 and log.count('LMI_RENDER_DELAY_OTHER ')==1 and
        log.index('LMI_TIME_COUNTS ')<log.index('LMI_RENDER_DELAY ')<log.index('LMI_RENDER_DELAY_OTHER '))
    return dict(histogram_valid=bool(valid),exercised=bool(values and values[0]>0),
        original_arguments_only=other==[0],after_timing_records=ordered,
        metric=dict(zip(('count','ticks','max_ticks','under_1ms','under_4ms','under_120hz','under_60hz','under_30hz','longer'),values or [])),
        mean_us=values[1]/values[0]/19.2 if values and values[0] else None,
        max_us=values[2]/19.2 if values else None,other=other,
        measured_animation_fps=None,performance_verified=False,
        scope='Elapsed time of native gpuWait polling delays, while the original GPU lock is released. Concurrent waits may overlap; this sum is not serial GPU execution time or animation FPS.')
def observe(log):
    result=prior.observe(log);result['render_delay']=render_delay(log);return result
def validate_run(observation):
    result=prior.validate_run(observation)
    for name in ['histogram_valid','exercised','original_arguments_only','after_timing_records']:
        if observation.get('render_delay',{}).get(name) is not True:result['failed_checks'].append('render_delay.'+name)
    result['passed']=not result['failed_checks'];result['scope']='v75 render polling statistics plus full v73 timing/GPU/source/DPU safety; legacy verification remains separate'
    return result
