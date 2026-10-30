"""Append display timings to the unchanged v72 GPU/display safety admission."""
import json,shutil
import lmi_display_v72_policy as prior
from lmi_display_v71_policy import record
checked=prior.checked
KERNEL_SHA='68ec1820fea704e99ab1ccac5d70f19670faa9428378f75592f251ff5ede56c2'
AUDIT_SHA='28be76910c0a461c790c06b82dbc0e020a925b37f9b25ba21cb8b01e60f53f5c'
HOST_SHA='e94b7a7042069023e15084a6c9c1c0225f279e917022cfb7a620762684750a1f'
LINK_SHA='c77e1827d83eb912da5643c14df1084dbf257488b8c926221f5695d7f574dcb3'
PRIOR_SHA='e24fdadaf1852a68cd13a52f6c2f9ebac61a033b49c8cf9f590538b8996a063c'
TAGS=('FRAME','GAP','SOURCE','COPY','DPU_WAIT','SUBMIT','TOTAL','CADENCE')


def stage(root,out):
    checked(root/'tools/lmi_display_v72_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-display-timing-v73'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host_path=root/'out/lmi-display-timing-v73b-host/result.json'
    link_path=root/'out/lmi-display-timing-v73b-link-review/result.json'
    host=json.loads(checked(host_path,HOST_SHA));link=json.loads(checked(link_path,LINK_SHA))
    assert host['result']=='PASS' and host['scenarios']==16 and len(host['mutations_caught'])==6
    for name in ['asan_ubsan','static_analysis','transparent_call_arguments_and_results','original_prefix_preserved',
                 'histogram_boundaries_verified','allocation_and_null_state_verified','stop_before_logging','no_hot_path_logging']:
        assert host[name]
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for name in ['object_reproduced','link_reproduced','independent_instruction_decode','hooks_verified',
                 'placed_sections_verified','free_tails_only','no_writable_globals','original_gpu_code_exact',
                 'outside_edits_exact','v72_touch_preserved','native_ready_abi_verified',
                 'original_source_implementation_bound','original_dpu_submit_bound']:
        assert link[name]
    for report in (audit,host,link):
        for name,digest in report['inputs'].items():checked(root/name,digest)
    original=baseline.read_bytes();restored=bytearray(raw)
    assert audit['base_sha256']==meta['sha256']==prior.KERNEL_SHA
    assert audit['sha256']==KERNEL_SHA and len(raw)==len(original)
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=original[a:z]
    assert restored==original and len(audit['hooks'])==5
    for name in ['append_only_journal','v71_gpu_code_preserved','v72_touch_preserved',
                 'original_source_wait_timeout_preserved','original_submit_timestamp_preserved',
                 'original_fences_and_dpu_poll_preserved']:
        assert audit[name]
    assert not audit['hot_path_logging'] and not audit['hardware_tested'] and not audit['performance_verified']
    target=out/'display-v73-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(host_path,target/'timing-host-review.json');shutil.copy2(link_path,target/'timing-link-review.json')
    meta['display_v73']=meta.pop('display_v72');meta['sha256']=KERNEL_SHA
    meta['display_v73'].update(display_timing=True,hot_path_logging=False,append_only_timing_journal=True,
        v72_touch_cadence_preserved=True,all_prior_gpu_display_safety_required=True,
        performance_change=False,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta


def timing(log):
    metrics={};checks=[]
    for name in TAGS:
        values=record(log,'LMI_TIME_'+name,9)
        valid=False
        if values:
            count,total,maximum,*bins=values
            edges=(19200,76800,160000,320000,640000)
            lower=(0,19201,76801,160001,320001,640001)
            upper=(*edges,maximum)
            minimum=sum(n*lo for n,lo in zip(bins,lower))
            ceiling=sum(n*min(hi,maximum) for n,hi in zip(bins,upper))
            max_bin=next((i for i,edge in enumerate(edges) if maximum<=edge),5)
            valid=(sum(bins)==count and minimum<=total<=ceiling and
                   ((count==0 and total==maximum==0) or
                    (count>0 and maximum<=total<=count*maximum and bins[max_bin]>0 and not any(bins[max_bin+1:]))))
            metrics[name.lower()]=dict(count=count,ticks=total,max_ticks=maximum,bins=bins,
                mean_us=total/count/19.2 if count else None,max_us=maximum/19.2)
        checks.append(valid)
    counts=record(log,'LMI_TIME_COUNTS',6)
    order=['LMI_TIME_'+name+' ' for name in TAGS]+['LMI_TIME_COUNTS ']
    ordered=all(log.count(tag)==1 for tag in order) and all(log.index(a)<log.index(b) for a,b in zip(order,order[1:]))
    related=False
    if all(checks) and counts:
        frame_ok,frame_other,submit_ok,submit_other,matched,unmatched=counts
        c=lambda name:metrics[name]['count']
        related=(frame_ok+frame_other==c('frame') and submit_ok+submit_other==c('submit')==matched+unmatched and
                 c('dpu_wait')==c('total')==matched and c('gap')<=c('frame') and c('copy')<=c('frame') and
                 c('cadence')==max(0,submit_ok-1))
    return dict(histograms_valid=all(checks),counter_relations_valid=bool(related),record_order_valid=ordered,
        counts=dict(zip(('frame_ok','frame_other','submit_ok','submit_other','matched','unmatched'),counts or [])),
        metrics=metrics,counter_hz=19200000,
        bin_upper_us=[1000,4000,1000000/120,1000000/60,1000000/30,None],
        measured_animation_fps=None,performance_verified=False,
        scope='FRAME includes native source waits and submit-to-copy-join. COPY overlaps FRAME and includes its native tail; SOURCE is the compositor ready callback, not every backend wait. DPU_WAIT is frame-return to native submit entry, including the original outer poll/delay. GAP is last successful submit return to frame entry and may include idle or failed frames. CADENCE includes idle; none of these counters measures panel FPS or physical touch-to-photon latency.')


def observe(log):
    result=prior.observe(log);result['display_timing']=timing(log);return result


def validate_run(observation):
    result=prior.validate_run(observation)
    for name in ['histograms_valid','counter_relations_valid','record_order_valid']:
        if observation.get('display_timing',{}).get(name) is not True:
            result['failed_checks'].append('display_timing.'+name)
    result['passed']=not result['failed_checks']
    result['scope']='v73 timing records plus unchanged v72/v71 GPU, source and DPU safety; legacy verification remains separate'
    return result
