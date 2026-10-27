"""Stop an actual queued copy; no post-stop service lock or backing release."""
from pathlib import Path
import hashlib,json,subprocess
r=Path(__file__).resolve().parents[1];t=r/'tools';host=r/'out/lmi-gpu-overlap-v70-host'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((host/'result.json').read_text());assert report['result']=='PASS'
for n,d in report['sources'].items():assert sha(t/n)==d,n
for n,d in report['generated_sources'].items():assert sha(host/n)==d,n
base=r/'out/lmi-gpu-overlap-v70-stop';base.mkdir(exist_ok=True)
out=base/('attempt-'+str(len(list(base.glob('attempt-*')))+1));out.mkdir()
s=(host/'check.c').read_text().split('int main(void)',1)[0]
s=s.replace('#include <setjmp.h>', '#include <setjmp.h>\nstatic int stop_now;static jmp_buf stop_escape;')
s=s.replace('    if(!s->pending.fence)return;\n    assert(!locked',
'''    if(!s->pending.fence)return;
    if(stop_now) {assert(!locked);lmi_gpu_frame_cleanup();longjmp(stop_escape,1);}
    assert(!locked''')
s+='''int main(void)
{
    struct fixture *f=make_gpu(4608);unsigned n=0;uint64_t ticket=0;stop_now=1;
    if(!setjmp(stop_escape)) {gpu_frame(f,f->surface,&n,&ticket);assert(!"stopped presenter returned");}
    assert(current->stop && !locked && frame_emit_count==5 && stats()->pending.fence);
    assert(stats()->queued==1 && !stats()->finished && !stats()->credit && !stats()->written);
    assert(backend.done<stats()->pending.fence && pending && refs==1 && !unrefs && !unmaps);
    assert(!stats()->pre.original.copies && !stats()->frames);
    /* As in the real return hook: all other CPUs are stopped, so backend
     * drain has exclusive access without taking their possibly owned lock. */
    assert(drain(&backend) && backend.done==backend.fence);
    assert(stats()->pending.fence && refs==1 && !unrefs); /* no fictitious join/release */
    lmi_fast_state->active=0;sp(f->fb,LMI_FB_fBase,(uintptr_t)f->gop);
    sp(f->fb,LMI_FB_fColumn,0x1234);sp(f->fb,LMI_FB_fColumnWeight,0x5678);
    destroy_gpu(f);scenarios++;puts("PASS: queued-copy stop retains backing, takes no service lock and real backend drains after stop");
}
'''
source=out/'check.c';source.write_text(s)
flags=['clang','-std=c17','-O2','-g','-Wall','-Wextra','-Werror','-Wno-unused-function',
       '-D_POSIX_C_SOURCE=200112L','-Wno-misleading-indentation','-DLMI_PRECLEAN_HOST',
       '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(t)]
sources=[source,r/'out/lmi-display-v62-host/original-compositor.c',host/'preclean.c',
         *[t/n for n in ['lmi-display-fast-v62.c','lmi-display-direct-plan-v61.c','lmi-display-pipeline-v51.c','lmi-gpu-overlap-v70.c']]]
c=subprocess.run([*flags,*map(str,sources),'-o',str(out/'check')],capture_output=True,text=True)
(out/'compile.log').write_text(c.stdout+c.stderr);c.check_returncode()
run=subprocess.run([str(out/'check')],capture_output=True,text=True,timeout=30)
(out/'host.log').write_text(run.stdout+run.stderr);print(run.stdout+run.stderr,end='');run.check_returncode()
(base/'result.json').write_text(json.dumps(dict(result='PASS',actual_backend=True,asan_ubsan=True,
    outstanding_copy_stopped=True,backing_retained=True,no_service_lock_after_stop=True,hardware_tested=False,
    attempt=str(out.relative_to(r)),
    inputs={str(p.relative_to(r)):sha(p) for p in [Path(__file__),host/'result.json',*sources]}),indent=2)+'\n')
