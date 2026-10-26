"""Check complete batch evidence and reject partial or contradictory traces."""
from pathlib import Path
import copy, hashlib, json
from lmi_display_v53_policy import observe

root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-display-v53-policy-host';out.mkdir(exist_ok=True)

def trace(matches):
    rows=[(1,1,0,0,0),(2,1,0,0x12345678,0)]
    bitmap=0
    for variant in range(8):
        for kind in range(4):
            a,b=0x12345678+kind,0x87654321+kind
            base=1000+variant*100+kind*10
            refs=[a,b,b,a]
            rows.extend((base+n,1,r,r,100+n) for n,r in enumerate(refs))
            same=(variant,kind) in matches
            rows.extend((base+4+n,int(same),r,r if same else r^0x100,200+n) for n,r in enumerate(refs))
            rows.append((base+8,int(same),a,b,variant+1))
            if same:bitmap|=1<<(variant*4+kind)
    return rows+[(90,1,256,256,bitmap),(5,1,0,0,0),(9000,0,256,1,0)]

def log(rows):
    return '\n'.join(['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_BEGIN live=1']+
        [f'LMI_DPU_PROBE stage={s} ok={ok} exp={e:x} got={a:x} ticks={t}' for s,ok,e,a,t in rows]+
        ['LMI_DPU_PROBE_RETURN restored=1'])

checks=0
def check(text,complete=False,matching=()):
    global checks
    result=observe(text);checks+=1
    assert result['diagnostic_complete']==complete,(checks,result['probe_result'])
    assert result['matching_variants']==list(matching)
    assert not result['desktop_pipeline_enabled'] and not result['hardware_scaling_verified']
    if complete:assert result['submitted_frames']==result['completed_frames']==256

all_pairs={(v,k) for v in range(8) for k in range(4)}
for matches,expected in [(set(),()),(all_pairs,range(8)),
                         ({(3,k) for k in range(4)}|{(2,0)},(3,)),
                         ({(v,0) for v in range(8)},())]:
    check(log(trace(matches)),True,expected)
rows=trace(all_pairs);good=log(rows)
for i in range(len(rows)):
    check(log(rows[:i]+rows[i+1:]))
    check(log(rows[:i]+[rows[i]]+rows[i:]))
for i in range(len(rows)-1):
    bad=copy.copy(rows);bad[i],bad[i+1]=bad[i+1],bad[i];check(log(bad))
for i in [2,6,10,74,290,291,292]:
    for field in [1,2,3,4]:
        # Ignore timing-only fields for frame records, which need not be fixed.
        if field==4 and i not in [10,290,291]:continue
        bad=copy.copy(rows);r=list(bad[i]);r[field]^=1;bad[i]=tuple(r);check(log(bad))
for marker in ['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_BEGIN live=1','LMI_DPU_PROBE_RETURN restored=1']:
    check(good.replace(marker,''));check(good+'\n'+marker)
check(good.replace('LMI_DPU_PROBE stage=1000','prefix LMI_DPU_PROBE stage=1000'))
check(good+'\nnoise LMI_DPU_PROBE stage=1000 ok=1 exp=1 got=1 ticks=1')
check(good.replace('LMI_SMP_OTHER_CORES_OFF\n','')+'\nLMI_SMP_OTHER_CORES_OFF')
for extra in ['LMI_DPU_PROBE_RETURN restored=0 retained=1','LMI_DPU_REFUSAL','LMI_DPU_DESKTOP enabled=1']:
    check(good+'\n'+extra)
check('');check('LMI_DPU_PROBE stage=9000 ok=0 exp=100 got=1 ticks=0')
historical=[]
for version in range(47,53):
    path=root/f'out/lmi-checkpoint-63-ios-probe-test-display-v{version}-desktop-180/checkpoint-63.log'
    if path.exists():check(path.read_text(errors='replace'));historical.append(version)
result=dict(result='PASS',checks=checks,historical_versions_rejected=historical,hardware_tested=False,
            sources={name:hashlib.sha256((root/'tools'/name).read_bytes()).hexdigest() for name in
                     ['lmi_display_v53_policy.py','check-lmi-display-v53-policy.py']})
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
