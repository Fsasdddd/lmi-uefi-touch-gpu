"""Strict boot-copy evidence and inherited admission; modeled logs stay in memory."""
from pathlib import Path
import copy,hashlib,json,runpy,traceback
import lmi_display_v65_policy as prior
from lmi_display_v66_policy import copy_probe,observe,validate_run

root=Path(__file__).resolve().parents[1]
prefix='LMI_GPU_DESKTOP_READY\n'
tail='LMI_GPU_DESKTOP_RESULT\n0000000000000001\nLMI_GPU_ASYNC_DRAINED\n'
values=[1020,90,0x660c0de6,0x660c0de7,0,123456];checks=0

def block(v):return 'LMI_CP_COPY '+' '.join(map(str,v))+'\n'
def check(log,valid=False,fresh=False,ordered=False):
    global checks
    checks+=1;result=copy_probe(log)
    assert (result['counts_valid'],result['fresh_completion_verified'],result['before_service_result'])==(valid,fresh,ordered),result
    assert result['desktop_gpu_copy'] is result['performance_verified'] is False

good=prefix+block(values)+tail
check(good,True,True,True);check('');check(prefix+tail)
for i in range(6):
    for value in [-1,0,1,89,90,1020,0x660c0de6,0x660c0de7,(1<<64)-1,1<<64]:
        v=values.copy();v[i]=value
        valid=all(0<=n<1<<64 for n in v) and v[0]==1020 and v[1]==90 and v[4]==0 and v[5]>0
        fresh=valid and v[2:4]==values[2:4]
        check(prefix+block(v)+tail,valid,fresh,valid)
for bad in ['-1 90 1 2 0 1','1020 90 1 2 0','1020 90 1 2 0 1 trailing',
            '1020 90 1 2 0 1.5','1020 90 1 2 0 1 2']:
    check(prefix+'LMI_CP_COPY '+bad+'\n'+tail)
check(good+block(values));check(good+'LMI_CP_COPY malformed\n')
for bad in [block(values)+prefix+tail,prefix+tail+block(values),
            good.replace(prefix,''),good+prefix,good+tail,
            good.replace('0000000000000001','0000000000000000')]:
    check(bad,True,True,False)

# Read the prior checker to reuse its complete inherited flag list rather than
# weakening or duplicating the definition. It does not execute main code.
import ast
tree=ast.parse((root/'tools/check-lmi-display-v65-policy.py').read_text())
required=next(ast.literal_eval(n.value) for n in tree.body
              if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='required' for t in n.targets))
required+=['copy_probe.counts_valid','copy_probe.fresh_completion_verified','copy_probe.before_service_result']
def put(obj,path,value):
    parts=path.split('.')
    for part in parts[:-1]:obj=obj.setdefault(part,{})
    obj[parts[-1]]=value
modeled={}
for path in required:put(modeled,path,True)
put(modeled,'async_gpu.fault_held',False)
assert validate_run(modeled)['passed'];checks+=1
for path in required:
    for bad in [False,None,0,1,'true',[],{}]:
        changed=copy.deepcopy(modeled);put(changed,path,bad)
        result=validate_run(changed)
        assert result['failed_checks']==[path] and result['passed'] is False;checks+=1
for log in ['',(root/'out/lmi-checkpoint-63-ios-probe-test-display-v65-desktop-180/checkpoint-63.log').read_text()]:
    old=prior.validate_run(prior.observe(log));new=validate_run(observe(log))
    assert set(old['failed_checks'])<set(new['failed_checks'])
    assert all('copy_probe.'+n in new['failed_checks'] for n in ['counts_valid','fresh_completion_verified','before_service_result'])
    checks+=1

# The frozen legacy verifier still rejects the actual v65 HFI-frequency row.
# This is a preserved failure, not a modeled replacement for a hardware run.
ns=runpy.run_path(str(root/'tools/verify-lmi-gpu-desktop.py'))
legacy_log=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v65-desktop-180/checkpoint-63.log').read_text()
try:
    ns['verify'](legacy_log,(root/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes(),None)
except AssertionError as error:
    rejected=traceback.extract_tb(error.__traceback__)[-1]
    assert Path(rejected.filename).name=='verify-lmi-gpu-gx.py' and rejected.lineno==11
    checks+=1
else:raise AssertionError('frozen legacy failure was unexpectedly accepted')

out=root/'out/lmi-display-v66-policy-host';out.mkdir(exist_ok=True)
names=['lmi_display_v66_policy.py','check-lmi-display-v66-policy.py','test-lmi-checkpoints.py']
report=dict(result='PASS',scenarios=checks,required_flags=len(required),
    inherited_v65_checks_preserved=True,old_run_without_copy_rejected=True,legacy_failure_preserved=True,
    legacy_rejection_file=Path(rejected.filename).name,legacy_rejection_line=rejected.lineno,
    synthetic_logs_in_memory_only=True,hardware_tested=False,performance_verified=False,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',checks,'v66 log/admission cases; original legacy failure remains rejected')
