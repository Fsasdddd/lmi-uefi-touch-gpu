"""Synthetic admission fixtures only; never rewrite hardware evidence."""
from pathlib import Path
import copy,hashlib,json,re
import lmi_display_v70_policy as policy
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v70-policy-host';out.mkdir(exist_ok=True)
log=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v66-desktop-180/checkpoint-63.log').read_text(encoding='utf-8')
assert not policy.validate_run(policy.observe(log))['passed'],'v66 is not GPU desktop evidence'
fixture=re.sub(r'(?m)^LMI_DPU_FAST .*$', 'LMI_DPU_FAST 2105 105 3',log)
fixture=re.sub(r'(?m)^LMI_FRAME_STRIDE .*$', 'LMI_FRAME_STRIDE 100',fixture)
first='LMI_GPU_BLIT 2000 2000 22138368000 100 1900 1990 14\n'
last='LMI_GPU_BLIT_LIFETIME 2 10 2 108 2000 1000000 0\n'
# Use an independently calculated byte count, rather than trusting any log.
assert 4544*2436==11069184
first='LMI_GPU_BLIT 2000 2000 '+str(2000*4544*2436)+' 100 1900 1990 14\n'
fixture=fixture.replace('LMI_GPU_QUEUE\n',first+last+'LMI_GPU_QUEUE\n')
cache='LMI_GPU_TARGET_CACHE 10 1990 9 '+str(1990*2*((4544*2436+16383)&~16383))+' 100000\n'
fixture=fixture.replace(last,last+cache)
overlap='LMI_GPU_COPY_OVERLAP 2000 2000 8000 6000 1000 100000\n'
pending='LMI_GPU_COPY_PENDING 0\n'
fixture=fixture.replace(cache,cache+overlap+pending)
good=policy.observe(fixture);valid=policy.validate_run(good)
assert valid['passed'],valid
assert not policy.validate_run(policy.observe(fixture.replace('LMI_GPU_BLIT','LMI_GPU_FRAME')))['passed']
cases=3;failures=[]
def reject(label,text):
    global cases
    result=policy.validate_run(policy.observe(text));assert not result['passed'],label
    failures.append(dict(case=label,failed_checks=result['failed_checks']));cases+=1
tags=['LMI_DPU_FAST','LMI_FRAME_STRIDE','LMI_SWAP_FENCE','LMI_DPU_PRECLEAN','LMI_GPU_BLIT','LMI_GPU_BLIT_LIFETIME','LMI_GPU_TARGET_CACHE','LMI_GPU_COPY_OVERLAP','LMI_GPU_COPY_PENDING']
for tag in tags:
    line,=re.findall(r'(?m)^'+tag+r' .*$',fixture)
    reject(tag+'-missing',fixture.replace(line+'\n',''))
    reject(tag+'-duplicate',fixture.replace(line+'\n',line+'\n'+line+'\n'))
    reject(tag+'-malformed',fixture.replace(line,line+' junk'))
    reject(tag+'-negative',fixture.replace(line,line.replace(' ',' -',1)))
for index in [0,1,2,3,4,6]:
    row=first.strip().split();row[index+1]=str(int(row[index+1])+1)
    reject('gpu-count-'+str(index),fixture.replace(first,' '.join(row)+'\n'))
for index,value in [(0,11),(1,11),(2,11),(4,1999),(5,0),(6,1)]:
    row=last.strip().split();row[index+1]=str(value)
    reject('lifetime-'+str(index),fixture.replace(last,' '.join(row)+'\n'))
for index,value in [(0,0),(0,11),(1,1989),(2,11),(3,1),(4,0)]:
    row=cache.strip().split();row[index+1]=str(value)
    reject('target-cache-'+str(index)+'-'+str(value),fixture.replace(cache,' '.join(row)+'\n'))
old=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v68-desktop-180/checkpoint-63.log').read_text(encoding='utf-8')
assert not policy.validate_run(policy.observe(old))['passed'],'v68 lacks target-cache evidence'
cases+=1
reject('GPU-pretended-to-be-CPU' ,fixture.replace('LMI_DPU_FAST 2105 105 3','LMI_DPU_FAST 2105 2105 3'))
reject('partial-frame-not-accounted',fixture.replace('LMI_DPU_FAST 2105 105 3','LMI_DPU_FAST 2105 105 2'))
reject('CPU-strides-exceed-CPU-copies',fixture.replace('LMI_FRAME_STRIDE 100','LMI_FRAME_STRIDE 106'))
reject('missing-fresh-copy',re.sub(r'(?m)^LMI_CP_COPY .*\n','',fixture))
reject('fault-held',fixture+'LMI_GPU_DESKTOP_FAULT_HELD\n')
reject('out-of-order',fixture.replace(first,'').replace('LMI_RAM_ONLY_TIMER_EXPIRED\n',first+'LMI_RAM_ONLY_TIMER_EXPIRED\n'))
for marker,count in [('LMI_GPU_QUEUE',8),('LMI_GPU_MAP_BATCH',3)]:
    row=re.search(r'(?m)^'+marker+r'\n'+r'[0-9a-f]{16}\n'*count,fixture)[0]
    reject(marker+'-missing',fixture.replace(row,''))
    reject(marker+'-duplicate',fixture.replace(row,row+row))
    reject(marker+'-extra-word',fixture.replace(row,row+'0000000000000001\n'))
for path in valid['failed_checks']:assert False,path
# Each mandatory admission boolean independently gates the run.
for key,value in good.items():
    if value is True:
        trial=copy.deepcopy(good);trial[key]=False
        if not policy.validate_run(trial)['passed']:cases+=1
    elif isinstance(value,dict):
        for sub,flag in value.items():
            if flag is True:
                trial=copy.deepcopy(good);trial[key][sub]=False
                if not policy.validate_run(trial)['passed']:cases+=1
# These are admission fixtures, not measured runtime evidence.
for index,value in [(0,1999),(1,1999),(2,7999),(3,5999),(4,2001),(5,0)]:
    row=overlap.strip().split();row[index+1]=str(value)
    reject('copy-overlap-'+str(index),fixture.replace(overlap,' '.join(row)+'\n'))
reject('copy-still-pending',fixture.replace(pending,'LMI_GPU_COPY_PENDING 42\n'))
reject('copy-order',fixture.replace(overlap+pending,pending+overlap))
reject('overlap-overflow',fixture.replace(overlap,overlap.replace(' 8000 ',' '+str(1<<64)+' ')))
reject('pending-overflow',fixture.replace(pending,'LMI_GPU_COPY_PENDING '+str(1<<64)+'\n'))
old=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v69-desktop-180/checkpoint-63.log').read_text(encoding='utf-8')
reject('v69-has-no-async-copy-evidence',old)
for row in ['2000 2000 2000 0 0 0','2000 2000 8000 6000 0 100000']:
    trial=fixture.replace(overlap,'LMI_GPU_COPY_OVERLAP '+row+'\n')
    assert policy.validate_run(policy.observe(trial))['passed'],row
    cases+=1
for field in ['counts_valid','pending_zero','record_order_valid']:
    trial=copy.deepcopy(good);trial['gpu_copy_overlap'][field]=False
    assert not policy.validate_run(trial)['passed'];cases+=1
(out/'synthetic-fixture.log').write_text(fixture,encoding='utf-8')
(out/'synthetic-observation.json').write_text(json.dumps(good,indent=2)+'\n')
report=dict(result='PASS',scenarios=cases,synthetic_only=True,hardware_tested=False,
    raw_v66_rejected=True,legacy_policy_unchanged=True,failure_cases=failures,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in
             ['lmi_display_v70_policy.py','check-lmi-display-v70-policy.py']})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',cases,'v70 policy cases; synthetic fixtures only')
