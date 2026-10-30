"""Synthetic v74 records may never bypass v73 GPU/source/DPU admission."""
from pathlib import Path
import hashlib,json,re
import lmi_display_v74_policy as policy
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'out/lmi-display-v74-policy-host';assert not out.exists();out.mkdir()
source=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v73-desktop-180/checkpoint-63.log'
raw=source.read_bytes();log=raw.decode('utf-8');assert policy.prior.validate_run(policy.prior.observe(log))['passed']
assert not policy.validate_run(policy.observe(log))['passed']
line='LMI_DPU_SHORT_WAIT 11 10 1 9600 192000 192000 0\n';fixture=log+'\n'+line
assert policy.validate_run(policy.observe(fixture))['passed'];cases=2;failures=[]
def reject(name,value):
    global cases
    result=policy.validate_run(policy.observe(value));assert not result['passed'],name
    failures.append(dict(case=name,failed_checks=result['failed_checks']));cases+=1
reject('missing',log);reject('duplicate',fixture+line);reject('malformed',fixture.replace(line,line.rstrip()+' x\n'))
for i in range(7):
    fields=line.split();fields[i+1]='-1';reject('negative '+str(i),fixture.replace(line,' '.join(fields)+'\n'))
    fields[i+1]=str(1<<64);reject('overflow '+str(i),fixture.replace(line,' '.join(fields)+'\n'))
for name,values in [('bad sum',[12,10,1,9600,192000,192000,0]),('no spin',[1,0,1,0,192000,192000,0]),
    ('short spin',[11,10,1,9599,192000,192000,0]),('wrong context',[11,10,1,9600,192000,192000,1]),
    ('invalid yield max',[11,10,1,9600,192000,192001,0])]:
    reject(name,fixture.replace(line,'LMI_DPU_SHORT_WAIT '+' '.join(map(str,values))+'\n'))
reject('wrong record order',line+log)
old=re.search(r'(?m)^LMI_GPU_BLIT_LIFETIME .*$',fixture)[0];fields=old.split();fields[-1]='1'
reject('inherited held DMA',fixture.replace(old,' '.join(fields)))
old=re.search(r'(?m)^LMI_TIME_FRAME .*$',fixture)[0];reject('inherited missing timing',fixture.replace(old,''))
assert source.read_bytes()==raw
paths=[Path(__file__),ROOT/'tools/lmi_display_v74_policy.py',source]
report=dict(result='PASS',cases=cases,failures_rejected=failures,synthetic_only=True,prior_admission_preserved=True,
    original_hardware_log_unchanged=True,hardware_tested=False,performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS:',cases,'synthetic v74 admission cases')
