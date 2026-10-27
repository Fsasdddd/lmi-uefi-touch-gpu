"""Malformed map-batch evidence must not qualify; synthetic host cases only."""
from pathlib import Path
import copy,hashlib,itertools,json,re
from lmi_display_v63_policy import map_batch,validate_run

prefix='LMI_DPU_PROBE_RETURN restored=1\nLMI_DPU_FAST 40 40 7\nLMI_FRAME_STRIDE 17\nLMI_SWAP_FENCE 50 50 70 30 0 1 1 1 0 52\n'
record='LMI_GPU_MAP_BATCH\n0000000000000007\n0000000000002744\n0000000000000000\n'
tail='LMI_GPU_ASYNC_DRAINED\nLMI_RAM_ONLY_TIMER_EXPIRED\n'
good=prefix+record+tail;checks=0

def check(log,valid=False,exercised=False):
    global checks
    checks+=1;r=map_batch(log)
    assert r['counts_valid']==valid and r['batching_exercised']==exercised,(log,r)
    assert not r['performance_verified']

check(good,True,True);check('');check(prefix+tail)
check(good.replace('0000000000002744','0000000000000007'),True,False)
for line in good.splitlines(keepends=True):
    check(good.replace(line,'',1))
    unrelated=bool(re.fullmatch(r'[0-9a-f]{16}\n',line))
    check(good+line,unrelated,unrelated)
    check(good.replace(line,line.rstrip()+' malformed\n',1))
for i in range(3):
    for bad in ['-1','1','f'*17,'G'*16,'','0000000000000000']:
        values=record.splitlines();values[i+1]=bad
        changed='\n'.join(values)+'\n'
        valid=i==2 and bad=='0000000000000000'
        check(prefix+changed+tail,valid,valid)
check(good.replace('0000000000002744','0000000000000001'))
check(good.replace('0000000000000000\nLMI_GPU_ASYNC','0000000000000001\nLMI_GPU_ASYNC'))
check(good+'LMI_GPU_MAP_BATCH malformed\n')
check(prefix+record+'0000000000000001\n'+tail)
for fault in ['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD','LMI_SWAP_FENCE_HELD']:
    check(good+fault+'\n')
parts=[prefix,record,*tail.splitlines(keepends=True)]
for order in itertools.permutations(range(4)):
    ok=order==(0,1,2,3)
    check(''.join(parts[i] for i in order),ok,ok)
map_checks=checks
# Model the integration gate independently of the parser. Only exact booleans
# qualify; absent, malformed, and truthy-but-nonboolean evidence must fail.
required=['normalized_experiment_qualified','desktop_pipeline_enabled','return_restored',
    'fast_path.counts_valid','fast_path.fast_path_exercised','fast_path.matches_desktop_frames',
    'producer_retirement.counts_valid','producer_retirement.source_release_verified',
    'producer_retirement.producer_wait_exercised','producer_retirement.matches_desktop_frames',
    'async_gpu.exit_gpu_drain_verified','gpu_map_batch.counts_valid','gpu_map_batch.batching_exercised']
modeled={}
def set_field(obj,path,value,remove=False):
    parts=path.split('.')
    for part in parts[:-1]:obj=obj.setdefault(part,{})
    if remove:obj.pop(parts[-1])
    else:obj[parts[-1]]=value
for path in required:set_field(modeled,path,True)
set_field(modeled,'async_gpu.fault_held',False)
def gate(obj,failed):
    global checks
    checks+=1;r=validate_run(obj)
    assert r['passed']==(not failed) and set(r['failed_checks'])==set(failed),r
    assert r['performance_verified'] is False
gate(modeled,[])
for path in required+['async_gpu.fault_held']:
    for bad in ([False,None,0,1,'true',[],{}] if path in required else [True,None,0,1,'false',[],{}]):
        changed=copy.deepcopy(modeled);set_field(changed,path,bad);gate(changed,[path])
    changed=copy.deepcopy(modeled);set_field(changed,path,None,remove=True);gate(changed,[path])
for parent in ['fast_path','producer_retirement','async_gpu','gpu_map_batch']:
    changed=copy.deepcopy(modeled);changed[parent]=None
    gate(changed,[p for p in required+['async_gpu.fault_held'] if p.startswith(parent+'.')])
gate({},required+['async_gpu.fault_held'])
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v63-policy-host';out.mkdir(exist_ok=True)
(out/'result.json').write_text(json.dumps(dict(result='PASS',checks=checks,hardware_tested=False,
    map_parser_cases=map_checks,integration_gate_cases=checks-map_checks,
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
             [Path(__file__),root/'tools/lmi_display_v63_policy.py']},
    modeled_logs_not_saved_as_hardware=True),indent=2)+'\n')
print(f'PASS: {map_checks} map-batch evidence cases, {checks-map_checks} integration gate cases')
