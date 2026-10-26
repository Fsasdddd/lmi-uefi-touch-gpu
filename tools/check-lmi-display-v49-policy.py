"""Host-only regression for complete evidence versus retained diagnostics."""
from pathlib import Path
import hashlib,json
from lmi_display_v49_policy import observe

root=Path(__file__).resolve().parents[1]
lines=['LMI_DPU_PROBE_BEGIN live=1']
colors=[0x1234,0x5678,0x5678,0x1234]*2
for stage in [1,2,10,11,10,11,3,12,13,12,13,4,7]:
    exp=got=0
    if stage in (10,11,12,13):exp=got=colors.pop(0)
    if stage in (3,4):exp,got=0x1234,0x5678
    if stage==7:exp=got=8
    lines.append(f'LMI_DPU_PROBE stage={stage} ok=1 exp={exp:x} got={got:x} ticks=960')
snapshot='LMI_DPU_PROBE stage=100 ok=1 exp=8 got=2 ticks=0'
lines+=['LMI_DPU_DESKTOP enabled=1',
    'LMI_DPU_DESKTOP n=120 sub=128 done=127 dt=38400000',
    'LMI_SMP_OTHER_CORES_OFF',snapshot,
    'LMI_DPU_DESKTOP n=121 sub=129 done=128 dt=40000000',
    'LMI_DPU_PROBE_RETURN restored=1']
positive=observe('\n'.join(lines))
assert positive['desktop_pipeline_enabled'] and positive['final_snapshot_valid']
negatives=[]
for n,line in enumerate(lines):
    if not line.startswith('LMI_DPU_DESKTOP n='):
        negatives.append(lines[:n]+lines[n+1:])
for n,line in enumerate(lines):
    if 'ok=1' in line:negatives.append(lines[:n]+[line.replace('ok=1','ok=0')]+lines[n+1:])
    if 'got=1234' in line or 'got=5678' in line:
        negatives.append(lines[:n]+[line.replace('got=1234','got=1235').replace('got=5678','got=5679')]+lines[n+1:])
for old,new in [('stage=100','stage=102'),('exp=8','exp=0'),('got=2','got=1'),('ticks=0','ticks=42')]:
    negatives.append([line.replace(old,new) if line==snapshot else line for line in lines])
without=[line for line in lines if line!=snapshot]
negatives += [lines+[snapshot], [snapshot]+without,without+[snapshot],
    lines+['LMI_DPU_FALLBACK restored=1'],lines+['LMI_DPU_REFUSAL'],
    [line.replace('sub=128','sub=999') for line in lines],
    [line.replace('done=127','done=129') for line in lines],
    [line.replace('dt=40000000','dt=1') for line in lines],
    ['LMI_SMP_OTHER_CORES_OFF',snapshot,'LMI_DPU_PROBE_RETURN restored=1']]
for n,candidate in enumerate(negatives):
    result=observe('\n'.join(candidate))
    assert not result['desktop_pipeline_enabled'],n
    assert result['performance_verified'] is False
refusal='LMI_DPU_PROBE stage=102 ok=0 exp=0 got=1 ticks='+str((0x1084000<<32)|0x127)
diagnostic=observe('\n'.join(['LMI_SMP_OTHER_CORES_OFF',refusal,'LMI_DPU_PROBE_RETURN restored=1']))
assert diagnostic['final_snapshots']==[dict(first_failure_stage=2,verified=False,probe_frames=0,
    final_route=1,refusal_key='0x1084000',refusal_value='0x127')]
assert not diagnostic['dma_verified'] and not diagnostic['desktop_pipeline_enabled']
real=observe((root/'out/lmi-checkpoint-63-ios-probe-test-display-v47-desktop-180/checkpoint-63.log').read_text())
assert real['probe_result']=='NOT_VERIFIED' and not real['desktop_pipeline_enabled']
v48=observe((root/'out/lmi-checkpoint-63-ios-probe-test-display-v48-desktop-180/checkpoint-63.log').read_text())
assert not v48['desktop_pipeline_enabled'] and v48['final_snapshots'][0]['first_failure_stage']==2
assert v48['final_snapshots'][0]['refusal_key']=='0x1084000' and v48['final_snapshots'][0]['refusal_value']=='0x127'
out=root/'out/lmi-display-v49-policy-host';out.mkdir(exist_ok=True)
report=dict(result='PASS',positive=1,negative=len(negatives),retained_refusal_decoded=True,
    real_v47_not_promoted=True,hardware_tested=False,
    sources={name:hashlib.sha256((root/'tools'/name).read_bytes()).hexdigest()
        for name in ('lmi_display_v49_policy.py','check-lmi-display-v49-policy.py')})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
