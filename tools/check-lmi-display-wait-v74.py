"""Verify bounded spin, original fallback arguments and stop-only records."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v74');a=p.parse_args();assert re.fullmatch(r'v74[a-z]?',a.attempt)
out=ROOT/('out/lmi-display-wait-'+a.attempt+'-host');assert not out.exists();out.mkdir()
source=ROOT/'tools/lmi-display-wait-v74.c';test=ROOT/'tools/check-lmi-display-wait-v74.c'
flags=['clang','-std=c17','-O2','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
    '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'tools')]
def execute(path,name):
    subprocess.run([*flags,str(path),str(test),'-o',str(out/name)],check=True)
    r=subprocess.run([str(out/name)],text=True,capture_output=True)
    (out/(name+'.log')).write_text(r.stdout+r.stderr);return r
r=execute(source,'check');r.check_returncode();assert 'PASS: 16 scenarios' in r.stdout;print(r.stdout,end='')
mutations={
    'budget-disabled':('began-s->original.ended<=LMI_WAIT_BUDGET_TICKS-LMI_WAIT_STEP_TICKS','1'),
    'armed-check-removed':('us==50 && s->original.armed && s->original.owner &&','us==50 && s->original.owner &&'),
    'fallback-argument-changed':('lmi_wait_original_delay(us);','lmi_wait_original_delay(1);'),
    'short-allocation':('IOMallocAligned(sizeof(struct lmi_wait_stats),alignment)','IOMallocAligned(sizeof(struct lmi_timing_stats),alignment)'),
    'stop-removed':('lmi_timing_cleanup(); /* Original verified SMP stop and display restore. */','/* stop removed */'),
}
caught=[];raw=source.read_text()
for name,(old,new) in mutations.items():
    assert old in raw;path=out/(name+'.c');path.write_text(raw.replace(old,new))
    r=execute(path,name);assert r.returncode!=0,('mutation survived',name);caught.append(name)
r=subprocess.run(['clang','--analyze','-std=c17','-I'+str(ROOT/'tools'),str(source),'-Xanalyzer','-analyzer-output=text'],capture_output=True,text=True,check=True)
(out/'static-analysis.log').write_text(r.stdout+r.stderr);assert not r.stdout+r.stderr
paths=[Path(__file__),source,test,ROOT/'tools/lmi-display-wait-v74.h']
report=dict(result='PASS',scenarios=16,mutations_caught=caught,asan_ubsan=True,static_analysis=True,
    frozen_timing_prefix_preserved=True,wall_clock_budget_verified=True,original_delay_arguments_verified=True,
    allocation_and_null_state_verified=True,preemption_and_counter_wrap_modeled=True,stop_before_logging=True,
    hardware_tested=False,performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
