"""Adverse evidence cases, never written as device logs."""
from pathlib import Path
import json
from lmi_display_v59_policy import fast_path
good='LMI_DPU_PROBE_RETURN restored=1\nLMI_DPU_FAST 40 40 7\nLMI_GPU_ASYNC_DRAINED\nLMI_RAM_ONLY_TIMER_EXPIRED\n'
checks=0
def check(log,valid=False,hit=False):
    global checks
    checks+=1;r=fast_path(log)
    assert r['counts_valid']==valid and r['fast_path_exercised']==hit
    assert not r['direct_surface_dma'] and not r['performance_verified']
check(good,True,True);check('')
for line in good.splitlines(keepends=True):
    check(good.replace(line,''));check(good+line);check(good.replace(line,line.rstrip()+' truncated\n'))
for counts in ['40 39 7','40 41 7','-1 40 7','0 0 0','40 x 7']:
    check(good.replace('40 40 7',counts))
check(good.replace('40 40 7','0 0 7'),True,False)
for fault in ['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD']:
    check(good+fault+'\n')
import itertools
lines=good.splitlines(keepends=True)
for order in itertools.permutations(range(4)):
    check(''.join(lines[v] for v in order),order==(0,1,2,3),order==(0,1,2,3))
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v59-policy-host';out.mkdir(exist_ok=True)
(out/'result.json').write_text(json.dumps(dict(result='PASS',checks=checks,hardware_tested=False,modeled_logs_not_saved_as_hardware=True),indent=2)+'\n')
print(f'PASS: {checks} fast-path evidence cases')
