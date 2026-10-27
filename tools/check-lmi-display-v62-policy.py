"""Adversarial producer-retirement evidence cases; never hardware evidence."""
from pathlib import Path
import itertools,json
from lmi_display_v62_policy import retirement
good='LMI_DPU_PROBE_RETURN restored=1\nLMI_DPU_FAST 40 40 7\nLMI_FRAME_STRIDE 17\nLMI_SWAP_FENCE 50 50 70 30 0 1 1 1 0 52\nLMI_GPU_ASYNC_DRAINED\nLMI_RAM_ONLY_TIMER_EXPIRED\n'
checks=0
def check(log,valid=False,exercised=False):
    global checks
    checks+=1;r=retirement(log)
    assert r['counts_valid']==valid and r['source_release_verified']==valid and r['producer_wait_exercised']==exercised,(log,r)
    assert not r['direct_surface_dma'] and not r['performance_verified']
check(good,True,True);check('')
for line in good.splitlines(keepends=True):
    check(good.replace(line,''));check(good+line);check(good.replace(line,line.rstrip()+' truncated\n'))
counts='50 50 70 30 0 1 1 1 0 52'
for bad in ['50 49 70 30 0 1 1 1 0 52','49 50 70 30 0 1 1 1 0 52','0 0 70 30 0 1 1 1 0 52',
            '50 50 70 30 0 1 1 1 1 52','50 50 70 30 0 1 1 1 0 49','50 50 2 30 0 1 1 1 0 52',
            '46 46 70 30 0 1 1 1 0 52']:
    check(good.replace(counts,bad))
for n in range(10):
    for bad in ['-1','x',str(1<<64)]:
        fields=counts.split();fields[n]=bad;check(good.replace(counts,' '.join(fields)))
check(good.replace(counts,'50 50 0 0 0 0 0 0 0 50'),True,False)
check(good.replace('40 40 7','40 39 7'))
check(good+'LMI_SWAP_FENCE_HELD\n')
for fault in ['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD']:check(good+fault+'\n')
lines=good.splitlines(keepends=True)
for order in itertools.permutations(range(6)):
    ok=order==(0,1,2,3,4,5);check(''.join(lines[n] for n in order),ok,ok)
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v62-policy-host';out.mkdir(exist_ok=True)
(out/'result.json').write_text(json.dumps(dict(result='PASS',checks=checks,hardware_tested=False,modeled_logs_not_saved_as_hardware=True),indent=2)+'\n')
print(f'PASS: {checks} producer retirement evidence cases')
