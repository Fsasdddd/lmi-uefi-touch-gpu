"""Reject incomplete/mismatched spatial probe evidence; no device access."""
import json
from pathlib import Path
from lmi_display_v44_policy import observe

stages=[1,2,10,11,10,11,3,12,13,12,13,4,5,6]
lines=['LMI_DPU_PROBE_BEGIN automatic=1 desktop_pipeline=0']
colors=[0x1234,0x5678,0x5678,0x1234]*2
for stage in stages:
    expected=actual=0
    if stage in (10,11,12,13):expected=actual=colors.pop(0)
    if stage in (3,4):expected,actual=0x1234,0x5678
    if stage in (5,6):expected=actual=8
    lines.append(f'LMI_DPU_PROBE stage={stage} ok=1 expected={expected:x} actual={actual:x} ticks=960')
lines+=['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_RETURN restored=1']
assert observe('\n'.join(lines))['dma_verified']
negatives=[]
for n in range(len(lines)):negatives.append(lines[:n]+lines[n+1:])
for n in range(1,15):negatives.append(lines[:n]+[lines[n].replace('ok=1','ok=0')]+lines[n+1:])
for n in (3,4,5,6,8,9,10,11):
    negatives.append(lines[:n]+[lines[n].replace('actual=1234','actual=1235').replace('actual=5678','actual=5679')]+lines[n+1:])
negatives.append(lines[:-2]+list(reversed(lines[-2:])))
negatives.append(lines+['LMI_DPU_PROBE_RETURN restored=0 retained=1'])
negatives.append(lines+['LMI_DPU_PROBE_REFUSED native-service-preflight'])
negatives.append(lines+['LMI_DPU_PROBE_STATE flags=0'])
negatives.append(lines+['LMI_DPU_PROBE stage=garbled'])
negatives.append(lines+[lines[4]])
negatives.append([s.replace('actual=8 ','actual=7 ') for s in lines])
for candidate in negatives:
    result=observe('\n'.join(candidate))
    assert not result['dma_verified'] and not result['hardware_scaling_verified']
out=Path(__file__).resolve().parents[1]/'out/lmi-display-v44-policy-host'
out.mkdir(exist_ok=True)
(out/'result.json').write_text(json.dumps(dict(result='PASS',positive=1,negative=len(negatives),
    hardware_tested=False),indent=2)+'\n')
print(f'PASS: one complete and {len(negatives)} rejected probe traces')
