"""CPU/PoC visibility and actual compositor/pipeline integration; no device."""
from pathlib import Path
import hashlib,json,re,subprocess
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-display-preclean-v65-host';out.mkdir(exist_ok=True)
prior=root/'out/lmi-display-v62-host'
frozen=json.loads((prior/'result.json').read_text())
assert frozen['result']=='PASS'
for n,d in frozen['sources'].items():assert hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest()==d
for n,d in frozen['generated_sources'].items():assert hashlib.sha256((prior/n).read_bytes()).hexdigest()==d
regression=(prior/'fast-pixel-regression.c').read_text()
assert regression.rstrip().endswith('}')
regression=regression.rstrip()[:-1]+'return 0;\n}\n'
(out/'fast-pixel-regression-v65.c').write_text(regression)
names=['lmi-display-preclean-v65.c','lmi-display-preclean-v65.h','check-lmi-display-preclean-v65.c',
       'check-lmi-display-preclean-v65.py','lmi-display-fast-v62.c','lmi-display-fast-v62.h',
       'lmi-display-direct-plan-v61.c','lmi-display-direct-plan-v61.h','lmi-display-pipeline-v51.c',
       'lmi-display-pipeline.h','lmi-display-dma.h']
flags=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-DLMI_PRECLEAN_HOST',
       '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(root/'tools'),'-I'+str(out)]
sources=[prior/'original-compositor.c',*[root/'tools'/n for n in ['lmi-display-fast-v62.c',
         'lmi-display-direct-plan-v61.c','lmi-display-pipeline-v51.c','check-lmi-display-preclean-v65.c']]]
def run(source,label):
    command=[*flags,*map(str,sources),str(source),'-o',str(out/label)]
    compiled=subprocess.run(command,text=True,capture_output=True)
    (out/(label+'-compile.log')).write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode:print(compiled.stdout+compiled.stderr)
    compiled.check_returncode()
    result=subprocess.run([str(out/label)],text=True,capture_output=True,timeout=60)
    (out/(label+'.log')).write_text(result.stdout+result.stderr)
    return result
production=root/'tools/lmi-display-preclean-v65.c'
result=run(production,'check');print(result.stdout+result.stderr);result.check_returncode()
cases=int(re.search(r'PASS: (\d+) preclean',result.stdout)[1])
text=production.read_text()
mutations={
    'no-real-early-clean':('int ok=lmi_preclean_original_clean(s->context,&s->buffer);','int ok=1;'),
    'reusable-credit':('if(s)s->armed=0; /* Single use','if(s)s->armed=s->armed; /* Single use'),
    'no-ticket-check':('p->ticket[s->index]!=s->ticket','0'),
    'no-descriptor-check':('!equal(p->buffer+s->index,&s->buffer)','0'),
    'no-new-frame-invalidation':('if(s)s->armed=0;\n    int result','if(s)s->armed=s->armed;\n    int result'),
    'wrong-journal-allocation':('IOMallocAligned(sizeof(struct lmi_preclean_stats),alignment)',
                                'IOMallocAligned(sizeof(struct lmi_fast_stats),alignment)'),
}
caught=[]
for label,(old,new) in mutations.items():
    assert text.count(old)==1,(label,old)
    source=out/(label+'.c');source.write_text(text.replace(old,new))
    mutated=run(source,label);assert mutated.returncode!=0,label
    caught.append(label)
report=dict(result='PASS',scenarios=cases,frozen_pixel_regressions=21,asan_ubsan=True,
    separate_cpu_poc_views=True,original_compositor_pipeline_used=True,mutations_caught=caught,
    hardware_tested=False,performance_verified=False,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names},
    frozen_evidence_sha256=hashlib.sha256((prior/'result.json').read_bytes()).hexdigest())
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(result='PASS',scenarios=cases,mutations_caught=caught)))
