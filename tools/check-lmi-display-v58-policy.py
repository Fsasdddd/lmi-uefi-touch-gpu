"""Adverse exit-log cases; modeled text is never saved as hardware evidence."""
from pathlib import Path
import json
from lmi_display_v58_policy import asynchronous
root=Path(__file__).resolve().parents[1]
good='LMI_DPU_PROBE_RETURN restored=1\nLMI_GPU_ASYNC_DRAINED\nLMI_RAM_ONLY_TIMER_EXPIRED\n'
checks=0
def check(log,ok=False):
    global checks
    checks+=1;r=asynchronous(log)
    assert r['exit_gpu_drain_verified']==ok
    assert not r['submission_overlap_measured'] and not r['performance_verified']
check(good,True);check('')
for line in good.splitlines(keepends=True):
    check(good.replace(line,''));check(good+line)
    check(good.replace(line,line.replace('\n',' truncated\n')))
for v in ['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD']:
    for pos in range(4):
        lines=good.splitlines(keepends=True);lines.insert(pos,v+'\n');check(''.join(lines))
lines=good.splitlines(keepends=True)
import itertools
for order in itertools.permutations(range(3)):
    check(''.join(lines[v] for v in order),order==(0,1,2))
out=root/'out/lmi-display-v58-policy-host';out.mkdir(exist_ok=True)
(out/'result.json').write_text(json.dumps(dict(result='PASS',checks=checks,hardware_tested=False,model_not_saved_as_hardware=True),indent=2)+'\n')
print(f'PASS: {checks} exit-log cases')
