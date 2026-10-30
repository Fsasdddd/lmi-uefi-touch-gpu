"""Host checks for transparent timing, ABI, boundaries and stop-only logging."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v73b');args=p.parse_args()
assert re.fullmatch(r'v73[a-z]?',args.attempt)
out=ROOT/('out/lmi-display-timing-'+args.attempt+'-host')
assert not out.exists();out.mkdir()
flags=['clang','-std=c17','-O2','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
       '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'tools')]
production=ROOT/'tools/lmi-display-timing-v73.c'
test=ROOT/'tools/check-lmi-display-timing-v73.c'
subprocess.run([*flags,str(production),str(test),'-o',str(out/'check')],check=True)
r=subprocess.run([str(out/'check')],capture_output=True,text=True)
(out/'check.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr,end='');r.check_returncode()
mutations={
    'changed-submit-time':('p,index,ticket,now);','p,index,ticket,((void)now,began));'),
    'small-allocation':('IOMallocAligned(sizeof(struct lmi_timing_stats),alignment)',
                        'IOMallocAligned(sizeof(struct lmi_gpu_frame_stats),alignment)'),
    'changed-source-timeout':('lmi_timing_original_source(surface,milliseconds)',
                              'lmi_timing_original_source(surface,((void)milliseconds,0))'),
    'wrong-ticket-match':('s->ticket==ticket','s->ticket!=ticket'),
    'logging-before-stop':('lmi_gpu_frame_cleanup(); /* Original verified stop, restore and counters. */','/* stop removed */'),
    'false-submit-success':('return result;\n}\n_Bool','return 1;\n}\n_Bool'),
}
caught=[];raw=production.read_text()
for name,(old,new) in mutations.items():
    assert raw.count(old)==1,(name,old)
    path=out/(name+'.c');path.write_text(raw.replace(old,new))
    subprocess.run([*flags,str(path),str(test),'-o',str(out/name)],check=True)
    r=subprocess.run([str(out/name)],capture_output=True,text=True)
    (out/(name+'.log')).write_text(r.stdout+r.stderr)
    assert r.returncode!=0,('mutation survived',name);caught.append(name)
r=subprocess.run(['clang','--analyze','-std=c17','-I'+str(ROOT/'tools'),str(production),
                  '-Xanalyzer','-analyzer-output=text'],capture_output=True,text=True,check=True)
(out/'static-analysis.log').write_text(r.stdout+r.stderr);assert not r.stdout+r.stderr
paths=[Path(__file__),production,test,ROOT/'tools/lmi-display-timing-v73.h',ROOT/'tools/lmi-gpu-deferred-cache-v71.h']
report=dict(result='PASS',scenarios=16,asan_ubsan=True,static_analysis=True,
    mutations_caught=caught,transparent_call_arguments_and_results=True,original_prefix_preserved=True,
    histogram_boundaries_verified=True,allocation_and_null_state_verified=True,
    stop_before_logging=True,no_hot_path_logging=True,hardware_tested=False,performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
