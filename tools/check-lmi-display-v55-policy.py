"""Normalized experimental eligibility must never imply exact bypass pixels."""
from pathlib import Path
import hashlib,json
from lmi_display_v55_policy import observe
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v55-policy-host';out.mkdir(exist_ok=True)
refs=[(0x484aa7cb,0xf874a603),(0x61f329b8,0xd303a7bd),(0x8e26faa5,0x3cd674a0),(0xb4f9e37c,0x06096d79),(0x5b2c3061,0xe9dcbe64)]
rows=[(1,1,0,0,0),(2,1,0,123,0)]
for n,(a,b) in enumerate(refs):
    r=[a,b,b,a]
    rows += [(1000+n*10+k,1,v,v,100) for k,v in enumerate(r)]
    rows += [(1004+n*10+k,1,v^0x484aa7cb,v^0x484aa7cb,100) for k,v in enumerate(r)]
    rows += [(1008+n*10,1,a,b,4 if not n else n-1)]
rows += [(90,1,40,40,0),(91,1,0x484aa7cb,40,0),(9000,1,40,2,0)]
def log(records):
    return '\n'.join(['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_BEGIN live=1']+
        [f'LMI_DPU_PROBE stage={s} ok={o} exp={e:x} got={a:x} ticks={t}' for s,o,e,a,t in records]+
        ['LMI_DPU_EXPERIMENTAL','LMI_DPU_DESKTOP n=120 sub=160 done=159 dt=38400000','LMI_DPU_PROBE_RETURN restored=1'])
checks=0
def check(text,qualified=False,desktop=False):
    global checks
    d=observe(text);checks+=1
    assert d['normalized_experiment_qualified']==qualified,(checks,d['probe_result'])
    assert d['desktop_pipeline_enabled']==desktop
    assert not d['hardware_scaling_verified'] and not d['bypass_pixel_equivalence'] and not d['performance_verified']
    if desktop:assert d['desktop_average_fps']==60
good=log(rows);check(good,True,True)
for i in range(len(rows)):
    check(log(rows[:i]+rows[i+1:]));check(log(rows[:i]+[rows[i]]+rows[i:]))
    if i+1<len(rows):
        bad=rows.copy();bad[i],bad[i+1]=bad[i+1],bad[i];check(log(bad))
    bad=rows.copy();r=list(bad[i]);r[1]=0;bad[i]=tuple(r);check(log(bad))
    if i!=1:
        for field in [2,3]:
            bad=rows.copy();r=list(bad[i]);r[field]^=1;bad[i]=tuple(r);check(log(bad))
for marker in ['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_BEGIN live=1','LMI_DPU_EXPERIMENTAL','LMI_DPU_PROBE_RETURN restored=1']:
    check(good.replace(marker,''));check(good+'\n'+marker)
for suffix in ['LMI_DPU_FALLBACK restored=1','LMI_DPU_REFUSAL','LMI_DPU_PROBE_RETURN restored=0 retained=1','LMI_DPU_DESKTOP enabled=1']:
    check(good+'\n'+suffix)
check(good.replace('LMI_DPU_PROBE stage=1000','noise LMI_DPU_PROBE stage=1000'))
for old,new in [('n=120','n=0'),('sub=160','sub=159'),('done=159','done=161'),('dt=38400000','dt=0')]:
    check(good.replace(old,new),True)
check(good.replace('LMI_DPU_DESKTOP n=120 sub=160 done=159 dt=38400000',''),True)
check(good+'\nLMI_DPU_DESKTOP n=120 sub=160 done=159 dt=38400000',True)
check('')
for v in range(47,55):
    p=root/f'out/lmi-checkpoint-63-ios-probe-test-display-v{v}-desktop-180/checkpoint-63.log'
    if p.exists():check(p.read_text(errors='replace'))
result=dict(result='PASS',checks=checks,hardware_tested=False,bypass_equivalence_never_claimed=True,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in ['lmi_display_v55_policy.py','check-lmi-display-v55-policy.py']})
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
