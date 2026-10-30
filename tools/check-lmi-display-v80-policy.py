"""Synthetic async records over untouched v79 evidence; never hardware claims."""
from pathlib import Path
import hashlib,json,re
import lmi_display_v80_policy as policy
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/lmi-display-async-v80-policy-a';OUT.mkdir(exist_ok=False)
base=ROOT/'out/lmi-render-cpu-v79/mach.development.bcm2837'
candidate=ROOT/'out/lmi-display-async-v80a/mach.development.bcm2837'
audit_path=candidate.parent/'build-audit.json';audit=json.loads(audit_path.read_text())
old,raw=base.read_bytes(),candidate.read_bytes();policy.verify_image(old,raw,audit)
source=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v79-short45/checkpoint-63.log'
log=source.read_text(encoding='utf-8');observed=policy.prior.observe(log)
assert policy.prior.validate_run(observed)['passed']
assert not policy.validate_run(policy.observe(log))['passed']
stats=observed['desktop_stats'][0]
values=[1,1,0,stats['frames'],stats['submitted']-40,stats['completed']-40,0,stats['submitted'],0,(1<<64)-1]
line='LMI_DPU_ASYNC '+' '.join(map(str,values))+'\n';combined=log+'\n'+line
assert policy.validate_run(policy.observe(combined))['passed']
assert policy.observe(combined)['async_dpu']['measured_animation_fps'] is None
bad_records={'duplicate':combined+line,'missing-cpu-restore':re.sub(r'(?m)^LMI_CPU_EPSS_RESTORE .*\n','',combined),
    'missing-source-lifetime':re.sub(r'(?m)^LMI_GPU_BLIT_LIFETIME .*\n','',combined),
    'missing-timing':re.sub(r'(?m)^LMI_TIME_FRAME .*\n','',combined)}
for name,index,value in [('not-started',1,0),('worker-failed',2,1),('wrong-enqueued',3,values[3]+1),
                         ('wrong-submitted',4,values[4]+1),('wrong-completed',5,values[5]-2),
                         ('failure-count',8,1),('pending-ready-frame',9,0)]:
    changed=values.copy();changed[index]=value
    bad_records[name]=log+'\nLMI_DPU_ASYNC '+' '.join(map(str,changed))+'\n'
for name,text in bad_records.items():assert not policy.validate_run(policy.observe(text))['passed'],name
bad_images=[]
for name,a,b in [('unmodified-v79',old,old),('wrong-parent',raw,raw),('truncated',old,raw[:-4])]:
    try:policy.verify_image(a,b,audit)
    except AssertionError:bad_images.append(name)
    else:raise AssertionError(name)
changed=bytearray(raw);changed[0xfffffff0079e5a7c-0xfffffff007004000]^=1
try:policy.verify_image(old,bytes(changed),audit)
except AssertionError:bad_images.append('extra-gpu-wait-edit')
else:raise AssertionError('extra-gpu-wait-edit')
paths=[Path(__file__),ROOT/'tools/lmi_display_v80_policy.py',base,candidate,audit_path,source]
report=dict(result='PASS',scenarios=3+len(bad_records)+len(bad_images),
    synthetic_records_are_not_hardware_evidence=True,original_hardware_log_unchanged=True,
    record_mutations_rejected=list(bad_records),image_mutations_rejected=bad_images,
    original_cpu_gpu_and_dpu_admission_retained=True,hardware_tested=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',report['scenarios'],'async image/record admission checks; all inherited safety required')
