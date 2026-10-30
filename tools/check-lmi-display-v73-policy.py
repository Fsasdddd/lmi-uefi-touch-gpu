"""Synthetic timing admission fixtures; original hardware logs remain intact."""
from pathlib import Path
import hashlib,json,re
import lmi_display_v73_policy as policy
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'out/lmi-display-v73-policy-host';assert not out.exists();out.mkdir()
source=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v72-desktop-180-retry/checkpoint-63.log'
raw=source.read_bytes();log=raw.decode('utf-8')
assert policy.prior.validate_run(policy.prior.observe(log))['passed']
assert not policy.validate_run(policy.observe(log))['passed']
def row(name,durations):
    bins=[0]*6
    for n in durations:
        k=next((i for i,edge in enumerate([19200,76800,160000,320000,640000]) if n<=edge),5)
        bins[k]+=1
    return 'LMI_TIME_'+name+' '+' '.join(map(str,[len(durations),sum(durations),max(durations,default=0),*bins]))+'\n'
rows=[row(name,durations) for name,durations in [
    ('FRAME',[20000,30000]),('GAP',[10000]),('SOURCE',[4000,4000]),('COPY',[3000,3000]),
    ('DPU_WAIT',[15000,15000]),('SUBMIT',[200,200]),('TOTAL',[35200,45200]),('CADENCE',[40000])]]
rows+=['LMI_TIME_COUNTS 2 0 2 0 2 0\n']
fixture=log+'\n'+''.join(rows)
good=policy.observe(fixture);assert policy.validate_run(good)['passed']
assert good['display_timing']['metrics']['dpu_wait']['mean_us']==15000/19.2
assert good['display_timing']['measured_animation_fps'] is None
cases=2;failures=[]
def reject(name,value):
    global cases
    result=policy.validate_run(policy.observe(value));assert not result['passed'],name
    failures.append(dict(case=name,failed_checks=result['failed_checks']));cases+=1
for row_text in rows:
    name=row_text.split()[0]
    reject(name+' missing',fixture.replace(row_text,''))
    reject(name+' duplicate',fixture+row_text)
    reject(name+' malformed',fixture.replace(row_text,row_text.rstrip()+' x\n'))
    fields=row_text.split();fields[1]='-1'
    reject(name+' negative',fixture.replace(row_text,' '.join(fields)+'\n'))
    fields[1]=str(1<<64)
    reject(name+' overflow',fixture.replace(row_text,' '.join(fields)+'\n'))
for n in range(8):
    fields=rows[n].split();fields[4]=str(int(fields[4])+1)
    reject(policy.TAGS[n]+' bin count',fixture.replace(rows[n],' '.join(fields)+'\n'))
    fields=rows[n].split();fields[3]=str(1<<63)
    reject(policy.TAGS[n]+' impossible max',fixture.replace(rows[n],' '.join(fields)+'\n'))
reject('wrong counter sum',fixture.replace(rows[-1],'LMI_TIME_COUNTS 3 0 2 0 2 0\n'))
reject('wrong matching sum',fixture.replace(rows[-1],'LMI_TIME_COUNTS 2 0 2 0 1 1\n'))
reject('wrong cadence count',fixture.replace(rows[-1],'LMI_TIME_COUNTS 2 0 1 1 2 0\n'))
reject('record order',fixture.replace(rows[0]+rows[1],rows[1]+rows[0]))
# Timings cannot admit evidence rejected by inherited source/DPU/GPU rules.
line=re.search(r'(?m)^LMI_GPU_BLIT_LIFETIME .*$',fixture)[0]
fields=line.split();fields[-1]='1'
reject('unchanged held-DMA admission',fixture.replace(line,' '.join(fields)))
assert source.read_bytes()==raw
report=dict(result='PASS',cases=cases,failures_rejected=failures,synthetic_only=True,
    original_hardware_log_unchanged=True,prior_admission_preserved=True,
    hardware_tested=False,performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__),ROOT/'tools/lmi_display_v73_policy.py',source]})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',cases,'synthetic timing admission cases; original log unchanged')
