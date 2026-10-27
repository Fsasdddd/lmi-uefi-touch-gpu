"""Adverse evidence cases, never written as device logs."""
from pathlib import Path
import json
from lmi_display_v61_policy import fast_path,qualification_metadata
good='LMI_DPU_PROBE_RETURN restored=1\nLMI_DPU_FAST 40 40 7\nLMI_FRAME_STRIDE 17\nLMI_GPU_ASYNC_DRAINED\nLMI_RAM_ONLY_TIMER_EXPIRED\n'
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
check(good.replace('40 40 7','0 0 7').replace('STRIDE 17','STRIDE 0'),True,False)
for stride in ['-1','41',str(1<<64),'x']:
    check(good.replace('STRIDE 17','STRIDE '+stride))
for counts in [str(1<<64)+' '+str(1<<64)+' 7','40 40 '+str(1<<64)]:
    check(good.replace('40 40 7',counts))
assert fast_path(good)['strided_frames']==17 and fast_path(good)['strided_path_exercised']
assert not fast_path(good.replace('STRIDE 17','STRIDE 0'))['strided_path_exercised']
checks+=2
for fault in ['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD']:
    check(good+fault+'\n')
import itertools
lines=good.splitlines(keepends=True)
for order in itertools.permutations(range(5)):
    check(''.join(lines[v] for v in order),order==(0,1,2,3,4),order==(0,1,2,3,4))
meta='LMI_FRAME_GUARD 24\nLMI_FRAME_META 42 4831838210436 19517574697537 0 1 0 0 0 0 0\n'
assert qualification_metadata(meta)['valid'];checks+=1
for bad in [meta+meta,meta.replace('24','128'),meta.replace('42','-1'),meta.replace('42',str(1<<64)),meta.replace(' 1 0 0',' 1 2 0'),meta.replace('0 0\n','0 truncated\n'),'']:
    assert not qualification_metadata(bad)['valid'];checks+=1
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v61-policy-host';out.mkdir(exist_ok=True)
(out/'result.json').write_text(json.dumps(dict(result='PASS',checks=checks,hardware_tested=False,modeled_logs_not_saved_as_hardware=True),indent=2)+'\n')
print(f'PASS: {checks} fast-path evidence cases')
