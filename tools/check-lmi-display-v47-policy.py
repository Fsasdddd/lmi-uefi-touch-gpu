"""Reject unproven hardware pattern/desktop transitions and completion claims."""
from pathlib import Path
import json
from lmi_display_v47_policy import observe
lines=['LMI_DPU_PROBE_BEGIN live=1']
colors=[0x1234,0x5678,0x5678,0x1234]*2
for stage in [1,2,10,11,10,11,3,12,13,12,13,4,7]:
    exp=got=0
    if stage in (10,11,12,13):exp=got=colors.pop(0)
    if stage in (3,4):exp,got=0x1234,0x5678
    if stage==7:exp=got=8
    lines.append(f'LMI_DPU_PROBE stage={stage} ok=1 exp={exp:x} got={got:x} ticks=960')
lines+=['LMI_DPU_DESKTOP enabled=1','LMI_DPU_DESKTOP n=120 sub=128 done=127 dt=38400000',
        'LMI_SMP_OTHER_CORES_OFF','LMI_DPU_DESKTOP n=121 sub=129 done=128 dt=40000000',
        'LMI_DPU_PROBE_RETURN restored=1']
assert observe('\n'.join(lines))['desktop_pipeline_enabled']
negatives=[]
for n in range(len(lines)):negatives.append(lines[:n]+lines[n+1:])
# Losing a periodic statistic alone is tolerated; exact pattern and transition
# evidence, final restoration and at least one genuine desktop sample are required.
negatives=[c for c in negatives if any('LMI_DPU_DESKTOP n=' in x for x in c)]
for n in range(1,14):negatives.append(lines[:n]+[lines[n].replace('ok=1','ok=0')]+lines[n+1:])
for n in (3,4,5,6,8,9,10,11):
    negatives.append(lines[:n]+[lines[n].replace('got=1234','got=1235').replace('got=5678','got=5679')]+lines[n+1:])
# The two independent periodic samples may be dropped without losing the proof.
negatives=[c for c in negatives if c!=lines[:15]+lines[16:] and c!=lines[:17]+lines[18:]]
negatives += [lines+['LMI_DPU_FALLBACK restored=1'],lines+['LMI_DPU_REFUSAL k=1'],
    [x.replace('sub=128','sub=999') for x in lines],
    [x.replace('done=127','done=129') for x in lines],
    [x.replace('dt=40000000','dt=1') for x in lines],
    ['LMI_DPU_DESKTOP enabled=1']+[x for x in lines if x!='LMI_DPU_DESKTOP enabled=1'],
    [x.replace('n=120 sub=128 done=127','n=0 sub=8 done=8').replace('n=121 sub=129 done=128','n=0 sub=8 done=8') for x in lines]]
for n,candidate in enumerate(negatives):
    result=observe('\n'.join(candidate))
    assert not result['desktop_pipeline_enabled'],n
out=Path(__file__).resolve().parents[1]/'out/lmi-display-v47-policy-host'
out.mkdir(exist_ok=True)
(out/'result.json').write_text(json.dumps(dict(result='PASS',positive=1,negative=len(negatives),hardware_tested=False),indent=2)+'\n')
print(f'PASS: one complete and {len(negatives)} rejected desktop traces')
