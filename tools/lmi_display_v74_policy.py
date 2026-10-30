"""Strict inherited GPU/DPU admission plus bounded short-wait accounting."""
import json,shutil
import lmi_display_v73_policy as prior
from lmi_display_v71_policy import record
checked=prior.checked
KERNEL_SHA='3334ca56324b14e7d6b0a6d110554de0646667b5d438b8e48bf953da0bb69f00'
AUDIT_SHA='e8e200063337a425dc5e9b98fda88986da52fb2e43cffc9592515c882053ea80'
HOST_SHA='c27b21f8e3c4871d652ff58bdafdce065e1f876f0bd22b34e3ba1754fce55305'
LINK_SHA='9eebbafece2872b9732bcdd2244f117507c9dfc41bd86f73715a1435ece34ce4'
PRIOR_SHA='8cf330b0787fe9c4a8aa393e3d5a6237f07bee3ec97444f6015dae273b961ee3'
def stage(root,out):
    checked(root/'tools/lmi_display_v73_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-display-wait-v74';raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host_path=root/'out/lmi-display-wait-v74-host/result.json'
    link_path=root/'out/lmi-display-wait-v74-link-review/result.json'
    host=json.loads(checked(host_path,HOST_SHA));link=json.loads(checked(link_path,LINK_SHA))
    assert host['result']=='PASS' and host['scenarios']==16 and len(host['mutations_caught'])==5
    for name in ['asan_ubsan','static_analysis','frozen_timing_prefix_preserved','wall_clock_budget_verified',
        'original_delay_arguments_verified','allocation_and_null_state_verified','preemption_and_counter_wrap_modeled','stop_before_logging']:assert host[name]
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for name in ['object_reproduced','link_reproduced','independent_instruction_decode','hooks_verified','free_tails_only',
        'no_writable_globals','v73_timing_code_exact','original_gpu_code_exact','v72_touch_preserved','outside_edits_exact',
        'dpu_poll_loop_and_timeout_exact','original_delay_bound','no_new_irq_masking_or_locks','spin_constants_decoded']:assert link[name]
    for report in [audit,host,link]:
        for name,digest in report['inputs'].items():checked(root/name,digest)
    original=baseline.read_bytes();restored=bytearray(raw)
    assert audit['base_sha256']==meta['sha256']==prior.KERNEL_SHA and audit['sha256']==KERNEL_SHA
    assert len(raw)==len(original) and len(audit['hooks'])==3
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=original[a:z]
    assert restored==original and audit['spin_step_ticks']==960 and audit['spin_budget_ticks']==160000
    for name in ['append_only_journal','original_dpu_poll_exact','v73_timing_code_preserved','v72_touch_preserved',
        'original_gpu_code_preserved','original_fences_and_timeout_preserved']:assert audit[name]
    assert not audit['hot_path_logging'] and not audit['hardware_tested'] and not audit['performance_verified']
    target=out/'display-v74-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(host_path,target/'wait-host-review.json');shutil.copy2(link_path,target/'wait-link-review.json')
    meta['display_v74']=meta.pop('display_v73');meta['sha256']=KERNEL_SHA
    meta['display_v74'].update(bounded_dpu_short_wait=True,spin_step_us=50,spin_wall_budget_us=160000/19.2,
        all_prior_gpu_display_safety_required=True,performance_change=True,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta
def short_wait(log):
    values=record(log,'LMI_DPU_SHORT_WAIT',7);valid=False
    if values:
        calls,spun,yielded,spin_ticks,yield_ticks,yield_max,other=values
        valid=(calls==spun+yielded and other<=yielded and spin_ticks>=spun*960 and
            (spun>0 or spin_ticks==0) and
            ((yielded==0 and yield_ticks==yield_max==0) or
             (yielded>0 and yield_max<=yield_ticks<=yielded*yield_max)))
    return dict(counts_valid=bool(valid),exercised=bool(values and values[0]>0 and values[1]>0),
        original_context_only=bool(values and values[-1]==0),
        counts=dict(zip(('calls','spun','yielded','spin_ticks','yield_ticks','yield_max','other'),values or [])),
        after_timing_records=bool(values and log.count('LMI_TIME_COUNTS ')==1 and log.index('LMI_TIME_COUNTS ')<log.index('LMI_DPU_SHORT_WAIT ')),
        measured_animation_fps=None,performance_verified=False)
def observe(log):
    result=prior.observe(log);result['dpu_short_wait']=short_wait(log);return result
def validate_run(observation):
    result=prior.validate_run(observation)
    for name in ['counts_valid','exercised','original_context_only','after_timing_records']:
        if observation.get('dpu_short_wait',{}).get(name) is not True:result['failed_checks'].append('dpu_short_wait.'+name)
    result['passed']=not result['failed_checks']
    result['scope']='v74 bounded waits and unchanged full v73 timing, GPU, source retirement and DPU checks; legacy verification remains separate'
    return result
