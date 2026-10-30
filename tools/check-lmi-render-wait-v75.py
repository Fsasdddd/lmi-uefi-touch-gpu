"""Check argument preservation and concurrent delay statistics with sanitizers."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v75');a=p.parse_args();assert re.fullmatch(r'v75[a-z]?',a.attempt)
out=ROOT/('out/lmi-render-wait-'+a.attempt+'-host');assert not out.exists();out.mkdir()
source=ROOT/'tools/lmi-render-wait-v75.c';test=ROOT/'tools/check-lmi-render-wait-v75.c'
flags=['clang','-std=c17','-O2','-g','-pthread','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
    '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'tools')]
def execute(path,name):
    subprocess.run([*flags,str(path),str(test),'-o',str(out/name)],check=True)
    r=subprocess.run([str(out/name)],text=True,capture_output=True);(out/(name+'.log')).write_text(r.stdout+r.stderr);return r
r=execute(source,'check');r.check_returncode();assert 'PASS: 16 scenarios' in r.stdout;print(r.stdout,end='')
raw=source.read_text();mutations={
    'changed-interval':('lmi_render_original_delay(interval,scale);','lmi_render_original_delay(interval+1,scale);'),
    'changed-scale':('lmi_render_original_delay(interval,scale);','lmi_render_original_delay(interval,scale+1);'),
    'short-allocation':('IOMallocAligned(sizeof(struct lmi_render_stats),alignment)','IOMallocAligned(sizeof(struct lmi_timing_stats),alignment)'),
    'wrong-histogram':('elapsed<=19200?0:','elapsed<=19200?1:'),
    'stop-removed':('lmi_timing_cleanup(); /* Verified SMP stop before reading all writers. */','/* stop removed */'),
}
caught=[]
for name,(old,new) in mutations.items():
    assert raw.count(old)==1;path=out/(name+'.c');path.write_text(raw.replace(old,new));r=execute(path,name)
    assert r.returncode!=0,('mutation survived',name);caught.append(name)
r=subprocess.run(['clang','--analyze','-std=c17','-I'+str(ROOT/'tools'),str(source),'-Xanalyzer','-analyzer-output=text'],capture_output=True,text=True,check=True)
(out/'static-analysis.log').write_text(r.stdout+r.stderr);assert not r.stdout+r.stderr
# Race check uses the actual production counters and four real pthreads.
tsan_flags=[f for f in flags if not f.startswith('-fsanitize=') and f!='-fno-sanitize-recover=all']
subprocess.run([*tsan_flags,'-fsanitize=thread',str(source),str(test),'-o',str(out/'race-check')],check=True)
r=subprocess.run([str(out/'race-check')],text=True,capture_output=True)
(out/'race-check.log').write_text(r.stdout+r.stderr);r.check_returncode()
paths=[Path(__file__),source,test,ROOT/'tools/lmi-render-wait-v75.h']
report=dict(result='PASS',scenarios=16,mutations_caught=caught,asan_ubsan=True,tsan=True,concurrent_writers=4,
    static_analysis=True,frozen_timing_prefix_preserved=True,original_delay_arguments_verified=True,
    allocation_and_null_state_verified=True,histogram_boundaries_and_wrap_verified=True,stop_before_logging=True,
    hardware_tested=False,performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
