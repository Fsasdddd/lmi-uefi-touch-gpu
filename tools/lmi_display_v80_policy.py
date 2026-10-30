"""Asynchronous DPU admission in addition to all v79 CPU/GPU/DPU checks."""
import hashlib,json,re,shutil
import lmi_display_v79_policy as prior
checked=prior.checked
KERNEL_SHA='988f7afd8ef6b1f08cc7600b12cf686776efcd8e7e8128348093f141d8201a39'
AUDIT_SHA='84dd555b57a539568a80046199e7c88830405f1fc97d0709895380985f281d04'
REVIEW_SHA='b5f54d17f0cff39431d59e0cc9c30b8a78ea9929da6e85ade3aa4fc52358c215'
PRIOR_SHA='a8e4fae9039d13e7eeb67a4ec8b78646da9e763a7aa9e1849377643ea431b50a'


def verify_image(original,raw,audit):
    assert hashlib.sha256(original).hexdigest()==prior.KERNEL_SHA
    assert hashlib.sha256(raw).hexdigest()==KERNEL_SHA and len(raw)==len(original)
    assert audit['base_sha256']==prior.KERNEL_SHA and audit['sha256']==KERNEL_SHA
    assert len(audit['allowed_file_ranges'])==4 and len(audit['hooks'])==3
    restored=bytearray(raw)
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=original[a:z]
    assert restored==original
    for key in ['outside_edits_exact','original_gpu_fences_and_copy_exact',
                'original_source_drop_and_retirement_exact','original_dpu_poll_and_submit_exact',
                'original_cpu_request_restore_and_psci_exact']:
        assert audit[key]


def stage(root,out):
    checked(root/'tools/lmi_display_v79_policy.py',PRIOR_SHA)
    folder=root/'out/lmi-display-async-v80a'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    review_path=root/'out/lmi-display-async-v80-review-b/result.json'
    review=json.loads(checked(review_path,REVIEW_SHA))
    assert review['result']=='PASS' and review['kernel_sha256']==KERNEL_SHA
    assert review['host_scenarios']==12 and review['native_scenarios']==11
    assert review['stream_frames']==512 and len(review['mutations_caught'])==3
    for key in ['linked_code_reproduced','outside_edits_exact','asan_ubsan','thread_sanitizer']:assert review[key]
    for report in [audit,review]:
        for name,digest in report['inputs'].items():checked(root/name,digest)
    baseline,meta=prior.stage(root,out)
    verify_image(baseline.read_bytes(),raw,audit)
    target=out/'display-v80-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(review_path,target/'concurrency-review.json')
    meta['display_v80']=meta.pop('display_v79');meta['sha256']=KERNEL_SHA
    meta['display_v80'].update(asynchronous_dpu_worker=True,
        source_drop_and_retirement_order_exact=True,one_pipeline_lock=True,
        original_gpu_dpu_cpu_safety_required=True,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta


def observe(log):
    result=prior.observe(log)
    lines=[line for line in log.splitlines() if line.startswith('LMI_DPU_ASYNC ')]
    matches=re.findall(r'(?m)^LMI_DPU_ASYNC ((?:[0-9]+ ){9}[0-9]+)$',log)
    values=list(map(int,matches[0].split())) if len(matches)==1 else []
    valid=len(lines)==len(matches)==1 and len(values)==10 and all(0<=v<1<<64 for v in values)
    names=['attempted','started','failed','enqueued','submitted','completed','waits','polls','failures','pending']
    counts=dict(zip(names,values))
    if valid:
        attempted,started,failed,enqueued,submitted,completed,waits,polls,failures,pending=values
        valid &= attempted==started==1 and failed==failures==0 and enqueued==submitted>0
        valid &= submitted-1<=completed<=submitted and polls>=completed and pending==(1<<64)-1
        stats=result.get('desktop_stats',[])
        valid &= len(stats)==1 and stats[0]['frames']==enqueued
        valid &= len(stats)==1 and stats[0]['submitted']==40+submitted and stats[0]['completed']==40+completed
        valid &= log.count('LMI_CPU_EPSS_RESTORE_DOMAIN ')==3
        valid &= log.rfind('LMI_CPU_EPSS_RESTORE_DOMAIN ')<log.find('LMI_DPU_ASYNC ')
    result['async_dpu']=dict(records_and_counts_valid=bool(valid),counts=counts,
        hardware_concurrency_measured=False,measured_animation_fps=None,performance_verified=False,
        scope='Worker start, queued/submitted frames and real inherited completion accounting. Does not measure physical render/scan overlap or FPS.')
    return result


def validate_run(observation):
    result=prior.validate_run(observation)
    if observation.get('async_dpu',{}).get('records_and_counts_valid') is not True:
        result['failed_checks'].append('async_dpu.records_and_counts_valid')
    result['passed']=not result['failed_checks']
    return result
