"""Identity CRC comparisons must never substitute for bypass pixel proof."""
from pathlib import Path
import hashlib,json
from lmi_display_v54_policy import observe
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v54-policy-host';out.mkdir(exist_ok=True)
def trace(matches,identity_bias):
    rows=[(1,1,0,0,0),(2,1,0,0x12345678,0)];bitmap=0
    for v in range(8):
        for k in range(5):
            a,b=0x12345678+k,0x87654321+k;base=1000+v*100+k*20
            bref=[a,b,b,a];refs=[n^identity_bias for n in bref]
            rows.extend((base+n,1,r,r,10+n) for n,r in enumerate(bref))
            rows.extend((base+4+n,1,r,r,20+n) for n,r in enumerate(refs))
            same=(v,k) in matches
            rows.extend((base+8+n,int(same),r,r if same else r^0x100,30+n) for n,r in enumerate(refs))
            rows.append((base+12,int(same),refs[0],refs[1],v+1))
            if same:bitmap|=1<<(v*5+k)
    return rows+[(90,1,480,480,bitmap),(5,1,0,0,0),(9000,0,480,1,0)]
def log(rows):
    return '\n'.join(['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_BEGIN live=1']+
        [f'LMI_DPU_PROBE stage={s} ok={o} exp={e:x} got={a:x} ticks={t}' for s,o,e,a,t in rows]+
        ['LMI_DPU_PROBE_RETURN restored=1'])
checks=0
def check(text,complete=False,geometry=(),exact=()):
    global checks
    d=observe(text);checks+=1
    assert d['diagnostic_complete']==complete,(checks,d['probe_result'])
    assert d['geometry_matching_variants']==list(geometry) and d['bypass_matching_variants']==list(exact)
    assert not d['matching_variants'] and not d['hardware_scaling_verified'] and not d['desktop_pipeline_enabled']
    if complete:assert d['submitted_frames']==d['completed_frames']==480
    return d
all_pairs={(v,k) for v in range(8) for k in range(5)}
check(log(trace(set(),0)),True)
d=check(log(trace(all_pairs,0)),True,range(8),range(8));assert d['probe_samples'][-3]['ticks']==(1<<40)-1
d=check(log(trace(all_pairs,0x20)),True,range(8));assert not any(r['identity_matches_bypass'] for r in d['pattern_results'])
check(log(trace({(7,k) for k in range(5)},0x20)),True,(7,))
rows=trace(all_pairs,0x20);good=log(rows)
for i in range(len(rows)):
    check(log(rows[:i]+rows[i+1:]));check(log(rows[:i]+[rows[i]]+rows[i:]))
for i in range(len(rows)-1):
    bad=rows.copy();bad[i],bad[i+1]=bad[i+1],bad[i];check(log(bad))
for i in [2,6,10,14,522,523,524]:
    for field in [1,2,3,4]:
        if field==4 and i not in [14,522,523]:continue
        bad=rows.copy();r=list(bad[i]);r[field]^=1;bad[i]=tuple(r);check(log(bad))
for marker in ['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_BEGIN live=1','LMI_DPU_PROBE_RETURN restored=1']:
    check(good.replace(marker,''));check(good+'\n'+marker)
check(good.replace('LMI_DPU_PROBE stage=1000','prefix LMI_DPU_PROBE stage=1000'))
check(good+'\nnoise LMI_DPU_PROBE stage=1000 ok=1 exp=1 got=1 ticks=1')
check(good.replace('LMI_SMP_OTHER_CORES_OFF\n','')+'\nLMI_SMP_OTHER_CORES_OFF')
for extra in ['LMI_DPU_PROBE_RETURN restored=0 retained=1','LMI_DPU_REFUSAL','LMI_DPU_DESKTOP enabled=1']:
    check(good+'\n'+extra)
check('')
for v in range(47,54):
    p=root/f'out/lmi-checkpoint-63-ios-probe-test-display-v{v}-desktop-180/checkpoint-63.log'
    if p.exists():check(p.read_text(errors='replace'))
result=dict(result='PASS',checks=checks,hardware_tested=False,identity_not_promoted_to_bypass_proof=True,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in
             ['lmi_display_v54_policy.py','check-lmi-display-v54-policy.py']})
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
