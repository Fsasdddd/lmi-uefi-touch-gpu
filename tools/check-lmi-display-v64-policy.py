"""Synthetic parser/gate cases, never stored as device evidence."""
from pathlib import Path
import copy,hashlib,itertools,json
import lmi_display_v63_policy as prior
from lmi_display_v64_policy import queue,validate_run
prefix='LMI_DPU_PROBE_RETURN restored=1\nLMI_DPU_FAST 40 40 7\nLMI_FRAME_STRIDE 17\nLMI_SWAP_FENCE 50 50 70 30 0 1 1 1 0 52\n'
mapping='LMI_GPU_MAP_BATCH\n0000000000000007\n0000000000002744\n0000000000000000\n'
tail='LMI_GPU_ASYNC_DRAINED\nLMI_RAM_ONLY_TIMER_EXPIRED\n'
values=[4,4,90,5,100,100,100,2]
def block(v):return 'LMI_GPU_QUEUE\n'+''.join(f'{n:016x}\n' for n in v)
good=prefix+block(values)+mapping+tail;checks=0
def check(log,valid=False,overlap=False):
    global checks
    checks+=1;r=queue(log)
    assert r['counts_valid']==valid and r['overlap_exercised']==overlap,(log,r)
    assert r['real_completion_drained']==valid and not r['performance_verified']
check(good,True,True);check('');check(prefix+mapping+tail)
for i in range(8):
    for replacement in [0,1,2,3,4,99,100,101,(1<<32)-1,1<<32,(1<<64)-1]:
        changed=values.copy();changed[i]=replacement
        limit,peak,overlaps,waits,barriers,submitted,completed,state=changed
        valid=(limit==4 and 1<=peak<=4 and peak<=submitted<1<<32 and submitted==completed and
               barriers>=submitted and waits<=submitted and peak-1<=overlaps<submitted and state==2 and
               (peak>1)==(overlaps>0))
        check(prefix+block(changed)+mapping+tail,valid,valid and peak>1)
for peak in [1,2,3,4]:
    changed=values.copy();changed[1]=peak;changed[2]=peak-1
    check(prefix+block(changed)+mapping+tail,True,peak>1)
for line in block(values).splitlines(keepends=True):
    check(good.replace(line,'',1))
    check(good.replace(line,line.rstrip()+' malformed\n',1))
check(good+block(values));check(good+'LMI_GPU_QUEUE malformed\n')
for bad in ['-1','1','f'*17,'G'*16,'']:
    check(good.replace('0000000000000004\n',bad+'\n',1))
for fault in ['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD','LMI_SWAP_FENCE_HELD']:
    check(good+fault+'\n')
for order in itertools.permutations([prefix,block(values),mapping,tail]):
    valid=order==(prefix,block(values),mapping,tail)
    check(''.join(order),valid,valid)
checks_parser=checks
required=['normalized_experiment_qualified','desktop_pipeline_enabled','return_restored',
    'fast_path.counts_valid','fast_path.fast_path_exercised','fast_path.matches_desktop_frames',
    'producer_retirement.counts_valid','producer_retirement.source_release_verified',
    'producer_retirement.producer_wait_exercised','producer_retirement.matches_desktop_frames',
    'async_gpu.exit_gpu_drain_verified','gpu_map_batch.counts_valid','gpu_map_batch.batching_exercised',
    'gpu_queue.counts_valid','gpu_queue.overlap_exercised','gpu_queue.real_completion_drained']
modeled={}
def put(obj,path,value,remove=False):
    parts=path.split('.')
    for part in parts[:-1]:obj=obj.setdefault(part,{})
    if remove:obj.pop(parts[-1])
    else:obj[parts[-1]]=value
for path in required:put(modeled,path,True)
put(modeled,'async_gpu.fault_held',False)
def gate(obj,failed):
    global checks
    checks+=1;r=validate_run(obj)
    assert r['passed']==(not failed) and set(r['failed_checks'])==set(failed),r
    assert not r['performance_verified']
gate(modeled,[])
for path in required+['async_gpu.fault_held']:
    for bad in ([False,None,0,1,'true',[],{}] if path in required else [True,None,0,1,'false',[],{}]):
        changed=copy.deepcopy(modeled);put(changed,path,bad);gate(changed,[path])
    changed=copy.deepcopy(modeled);put(changed,path,None,True);gate(changed,[path])
for parent in ['fast_path','producer_retirement','async_gpu','gpu_map_batch','gpu_queue']:
    changed=copy.deepcopy(modeled);changed[parent]=None
    gate(changed,[p for p in required+['async_gpu.fault_held'] if p.startswith(parent+'.')])
# Earlier raw failure remains a failure; this policy does not repair its evidence.
root=Path(__file__).resolve().parents[1]
log=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v63-desktop-180/checkpoint-63.log').read_text()
old=prior.validate_run(prior.observe(log));assert not old['passed']
from lmi_display_v64_policy import observe
current=validate_run(observe(log));assert not current['passed']
assert set(old['failed_checks'])<=set(current['failed_checks']);checks+=1
out=root/'out/lmi-display-v64-policy-host';out.mkdir(exist_ok=True)
names=['lmi_display_v64_policy.py','check-lmi-display-v64-policy.py','lmi_display_v63_policy.py','test-lmi-checkpoints.py']
report=dict(result='PASS',scenarios=checks,parser_cases=checks_parser,integration_cases=checks-checks_parser,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names},
    v63_raw_failure_preserved=True,hardware_tested=False,performance_verified=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',checks,'v64 parser/integration cases; prior raw failure still rejected')
