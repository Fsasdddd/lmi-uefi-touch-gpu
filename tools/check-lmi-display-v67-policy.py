"""Synthetic admission fixtures only; never rewrite hardware evidence."""
from pathlib import Path
import copy,hashlib,json,re
import lmi_display_v67_policy as policy
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v67-policy-host';out.mkdir(exist_ok=True)
log=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v66-desktop-180/checkpoint-63.log').read_text(encoding='utf-8')
assert not policy.validate_run(policy.observe(log))['passed'],'v66 is not GPU desktop evidence'
fixture=re.sub(r'(?m)^LMI_DPU_FAST .*$', 'LMI_DPU_FAST 2105 105 3',log)
fixture=re.sub(r'(?m)^LMI_FRAME_STRIDE .*$', 'LMI_FRAME_STRIDE 100',fixture)
first='LMI_GPU_FRAME 2000 2000 22138368000 100 1900 1990 13\n'
last='LMI_GPU_FRAME_LIFETIME 2 10 2 108 2000 1000000 0\n'
# Use an independently calculated byte count, rather than trusting any log.
assert 4544*2436==11069184
first='LMI_GPU_FRAME 2000 2000 '+str(2000*4544*2436)+' 100 1900 1990 13\n'
fixture=fixture.replace('LMI_GPU_QUEUE\n',first+last+'LMI_GPU_QUEUE\n')
good=policy.observe(fixture);valid=policy.validate_run(good)
assert valid['passed'],valid
cases=2;failures=[]
def reject(label,text):
    global cases
    result=policy.validate_run(policy.observe(text));assert not result['passed'],label
    failures.append(dict(case=label,failed_checks=result['failed_checks']));cases+=1
tags=['LMI_DPU_FAST','LMI_FRAME_STRIDE','LMI_SWAP_FENCE','LMI_DPU_PRECLEAN','LMI_GPU_FRAME','LMI_GPU_FRAME_LIFETIME']
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
reject('GPU-pretended-to-be-CPU',fixture.replace('LMI_DPU_FAST 2105 105 3','LMI_DPU_FAST 2105 2105 3'))
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
(out/'synthetic-fixture.log').write_text(fixture,encoding='utf-8')
(out/'synthetic-observation.json').write_text(json.dumps(good,indent=2)+'\n')
report=dict(result='PASS',scenarios=cases,synthetic_only=True,hardware_tested=False,
    raw_v66_rejected=True,legacy_policy_unchanged=True,failure_cases=failures,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in
             ['lmi_display_v67_policy.py','check-lmi-display-v67-policy.py']})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',cases,'v67 policy cases; synthetic fixtures only')
