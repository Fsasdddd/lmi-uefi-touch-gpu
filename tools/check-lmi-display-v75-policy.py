"""Reject malformed or unsafe synthetic rendering poll evidence."""
from pathlib import Path
import hashlib,json,re
import lmi_display_v75_policy as policy
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'out/lmi-display-v75-policy-host';assert not out.exists();out.mkdir()
source=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v73-desktop-180/checkpoint-63.log'
raw=source.read_bytes();log=raw.decode('utf-8');assert policy.prior.validate_run(policy.prior.observe(log))['passed']
row='LMI_RENDER_DELAY 2 38400 19200 2 0 0 0 0 0\n';other='LMI_RENDER_DELAY_OTHER 0\n';fixture=log+'\n'+row+other
assert not policy.validate_run(policy.observe(log))['passed'];assert policy.validate_run(policy.observe(fixture))['passed']
cases=2;failures=[]
def reject(name,value):
    global cases
    result=policy.validate_run(policy.observe(value));assert not result['passed'],name
    failures.append(dict(case=name,failed_checks=result['failed_checks']));cases+=1
for row_text in [row,other]:
    reject('missing '+row_text.split()[0],fixture.replace(row_text,''));reject('duplicate '+row_text.split()[0],fixture+row_text)
    reject('malformed '+row_text.split()[0],fixture.replace(row_text,row_text.rstrip()+' x\n'))
    for i in range(1,len(row_text.split())):
        fields=row_text.split();fields[i]='-1';reject('negative '+row_text.split()[0]+' '+str(i),fixture.replace(row_text,' '.join(fields)+'\n'))
        fields[i]=str(1<<64);reject('overflow '+row_text.split()[0]+' '+str(i),fixture.replace(row_text,' '.join(fields)+'\n'))
for name,line in [('bad count','LMI_RENDER_DELAY 3 38400 19200 2 0 0 0 0 0\n'),
    ('bad max','LMI_RENDER_DELAY 2 38400 19201 2 0 0 0 0 0\n'),('empty','LMI_RENDER_DELAY 0 0 0 0 0 0 0 0 0\n')]:reject(name,fixture.replace(row,line))
reject('wrong arguments',fixture.replace(other,'LMI_RENDER_DELAY_OTHER 1\n'))
reject('wrong record order',fixture.replace(row+other,other+row))
old=re.search(r'(?m)^LMI_GPU_BLIT_LIFETIME .*$',fixture)[0];fields=old.split();fields[-1]='1';reject('inherited held DMA',fixture.replace(old,' '.join(fields)))
old=re.search(r'(?m)^LMI_TIME_FRAME .*$',fixture)[0];reject('inherited missing timing',fixture.replace(old,''))
assert source.read_bytes()==raw;paths=[Path(__file__),ROOT/'tools/lmi_display_v75_policy.py',source]
report=dict(result='PASS',cases=cases,failures_rejected=failures,synthetic_only=True,prior_admission_preserved=True,
    original_hardware_log_unchanged=True,hardware_tested=False,performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS:',cases,'synthetic v75 admission cases')
