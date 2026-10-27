"""Strict new counters and inherited failures; synthetic logs stay in memory."""
from pathlib import Path
import copy,hashlib,json
import lmi_display_v64_policy as prior
from lmi_display_v65_policy import preclean,observe,validate_run
prefix='LMI_DPU_PROBE_RETURN restored=1\nLMI_DPU_FAST 40 40 7\nLMI_FRAME_STRIDE 17\nLMI_SWAP_FENCE 50 50 70 30 0 1 1 1 0 52\n'
tail='LMI_GPU_QUEUE\n'+''.join(f'{n:016x}\n' for n in [4,4,90,5,100,100,100,2])
tail+='LMI_GPU_MAP_BATCH\n0000000000000007\n0000000000002744\n0000000000000000\nLMI_GPU_ASYNC_DRAINED\nLMI_RAM_ONLY_TIMER_EXPIRED\n'
values=[47,46,47,0,0,123456];checks=0
def block(v):return 'LMI_DPU_PRECLEAN '+' '.join(map(str,v))+'\n'
def check(log,valid=False,exercised=False,matches=False):
    global checks
    checks+=1;result=preclean(log)
    assert result['counts_valid']==valid and result['preclean_exercised']==exercised and result['matches_desktop_frames']==matches,result
    assert result['performance_verified'] is False
good=prefix+block(values)+tail;check(good,True,True,True);check('');check(prefix+tail)
for i in range(6):
    for value in [-1,0,1,46,47,48,(1<<64)-1,1<<64]:
        v=values.copy();v[i]=value
        prepared,pending,consumed,fallback,failed,ticks=v
        valid=all(0<=n<1<<64 for n in v) and 0<consumed<=prepared and pending<=prepared and fallback==failed==0 and ticks>0
        check(prefix+block(v)+tail,valid,valid and pending>0,valid and prepared==47)
for bad in ['-1 46 47 0 0 123456','47 46 47 0 0','47 46 47 0 0 12 trailing','47 46 47 0 0 1.5']:
    check(prefix+'LMI_DPU_PRECLEAN '+bad+'\n'+tail)
check(good+block(values));check(good+'LMI_DPU_PRECLEAN malformed\n')
check(block(values)+prefix+tail);check(prefix+tail+block(values))
check(good.replace('LMI_SWAP_FENCE ','BROKEN_SWAP_FENCE '))
required=['normalized_experiment_qualified','desktop_pipeline_enabled','return_restored',
 'fast_path.counts_valid','fast_path.fast_path_exercised','fast_path.matches_desktop_frames',
 'producer_retirement.counts_valid','producer_retirement.source_release_verified',
 'producer_retirement.producer_wait_exercised','producer_retirement.matches_desktop_frames',
 'async_gpu.exit_gpu_drain_verified','gpu_map_batch.counts_valid','gpu_map_batch.batching_exercised',
 'gpu_queue.counts_valid','gpu_queue.overlap_exercised','gpu_queue.real_completion_drained',
 'preclean.counts_valid','preclean.matches_desktop_frames','preclean.preclean_exercised']
def put(obj,path,value):
    parts=path.split('.')
    for part in parts[:-1]:obj=obj.setdefault(part,{})
    obj[parts[-1]]=value
modeled={}
for path in required:put(modeled,path,True)
put(modeled,'async_gpu.fault_held',False)
assert validate_run(modeled)['passed'];checks+=1
for path in required:
    for bad in [False,None,0,1,'true',[],{}]:
        changed=copy.deepcopy(modeled);put(changed,path,bad)
        result=validate_run(changed);assert result['failed_checks']==[path] and not result['passed'];checks+=1
root=Path(__file__).resolve().parents[1]
log=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v64-desktop-180/checkpoint-63.log').read_text()
old=prior.validate_run(prior.observe(log));new=validate_run(observe(log))
assert not old['passed'] and set(old['failed_checks'])<set(new['failed_checks']);checks+=1
out=root/'out/lmi-display-v65-policy-host';out.mkdir(exist_ok=True)
names=['lmi_display_v65_policy.py','check-lmi-display-v65-policy.py','test-lmi-checkpoints.py']
report=dict(result='PASS',scenarios=checks,inherited_v64_failure_preserved=True,hardware_tested=False,
    performance_verified=False,sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',checks,'v65 counter/integration cases; original v64 failure remains rejected')
