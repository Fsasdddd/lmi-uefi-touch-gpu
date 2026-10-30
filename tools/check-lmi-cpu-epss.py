"""Run the production EPSS module under ASan/UBSan and inject IO failures."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--attempt',default='a');a=p.parse_args()
assert re.fullmatch('[a-z]',a.attempt)
out=ROOT/('out/lmi-cpu-epss/host-'+a.attempt);assert not out.exists();out.mkdir()
source=ROOT/'tools/lmi-cpu-epss.c';test=ROOT/'tools/check-lmi-cpu-epss.c'
flags=['clang','-std=c17','-O2','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
       '-fno-sanitize-recover=all','-I'+str(ROOT/'tools')]
def run(path,name):
    subprocess.run([*flags,str(path),str(test),'-o',str(out/name)],check=True)
    r=subprocess.run([str(out/name)],text=True,capture_output=True)
    (out/(name+'.log')).write_text(r.stdout+r.stderr);return r
r=run(source,'check');r.check_returncode();match=re.search(r'PASS: (\d+) scenarios; (\d+) distinct',r.stdout);assert match
print(r.stdout,end='')
text=source.read_text();caught=[]
mutations={
    'ignore-core-count':('cc==max_cores && freq<=cap','cc!=0 && freq<=cap'),
    'ignore-cap':('freq<=cap && freq>best','freq>best'),
    'stop-on-frequency-only':('freq==previous && cc==previous_cc','freq==previous && (previous_cc|cc)<=7'),
    'forget-dirty-before-write':('__atomic_fetch_or(&s->dirty,bit,__ATOMIC_RELEASE);','/* missing journal */'),
    'skip-rollback':('(void)lmi_epss_restore(s);return 0;','return 0;'),
    'clear-dirty-on-restore-failure':('if(wrote && read && got==d->original)','if(wrote || read || got==d->original)'),
    'accept-request-mismatch':('!wrote || !read || got!=d->target','!wrote || !read'),
    'restore-target-instead':('LMI_EPSS_PERF,d->original);','LMI_EPSS_PERF,d->target);'),
}
for name,(old,new) in mutations.items():
    assert text.count(old)==1,name
    path=out/(name+'.c');path.write_text(text.replace(old,new));r=run(path,name)
    assert r.returncode!=0,('mutation survived',name);caught.append(name)
r=subprocess.run(['clang','--analyze','-std=c17','-I'+str(ROOT/'tools'),str(source),
                  '-Xanalyzer','-analyzer-output=text'],capture_output=True,text=True,check=True)
(out/'static-analysis.log').write_text(r.stdout+r.stderr);assert not r.stdout+r.stderr
paths=[Path(__file__),source,test,ROOT/'tools/lmi-cpu-epss.h',ROOT/'out/lmi-cpu-epss/board-profile-b/profile.json']
report=dict(result='PASS',scenarios=int(match[1]),fallible_points=int(match[2]),write_failure_models=2,
    mutations_caught=caught,asan_ubsan=True,static_analysis=True,all_io_fault_points=True,
    request_readback_and_exact_restore_verified=True,no_ddr_access=True,
    lifecycle='Caller serialized; restore only after other CPUs stopped. Not a concurrent hardware simulation.',
    hardware_tested=False,measured_cpu_frequency=None,performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(caught),'mutations caught; ASan/UBSan and static analysis clean')
