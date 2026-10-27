"""Actual v64 backend + native frame wrappers, separate CPU/DMA pixels."""
from pathlib import Path
import hashlib,json,re,subprocess
root=Path(__file__).resolve().parents[1];tools=root/'tools'
out=root/'out/lmi-gpu-deferred-cache-v71-host';out.mkdir(exist_ok=True)
attempt=out/('attempt-'+str(len(list(out.glob('attempt-*')))+1));attempt.mkdir()
prior=root/'out/lmi-display-v62-host'
frozen=json.loads((prior/'result.json').read_text())
for n,d in frozen['sources'].items():assert hashlib.sha256((tools/n).read_bytes()).hexdigest()==d
for n,d in frozen['generated_sources'].items():assert hashlib.sha256((prior/n).read_bytes()).hexdigest()==d
prefix=(prior/'fast-pixel-regression.c').read_text().split('int main(void)',1)[0]
prefix=prefix.replace('void *IOMallocAligned(size_t n,size_t a)', 'static void allocated(void *,size_t);\nvoid *IOMallocAligned(size_t n,size_t a)')
prefix=prefix.replace('return p;}','allocated(p,n);return p;}',1)
prefix=prefix.replace('lmi_fast_draw(self,surfaces[0]', 'lmi_gpu_frame_draw(self,surfaces[0]')
prefix=prefix.replace('lmi_gpu_frame_draw(self,surfaces[0],(const int32_t *)(swap+0x64),(const int32_t *)(swap+0xc4));',
    'if(surfaces[0])lmi_gpu_frame_draw(self,surfaces[0],(const int32_t *)(swap+0x64),(const int32_t *)(swap+0xc4));'
    'else for(unsigned y=0;y<2436;y++)memset((void *)(rp(self,LMI_FB_fBase)+y*4544u),0,1125u*4);')
prefix=prefix.replace('f->draws++;', 'f->draws++;assert(!((struct lmi_gpu_frame_stats *)lmi_fast_state)->clean_mask && !((struct lmi_gpu_frame_stats *)lmi_fast_state)->gpu_owned_mask);')
prefix=prefix.replace('offset+pitch*2436u,4096','(offset+pitch*2436u+4095u)&~4095u,4096')
prefix=prefix.replace('sw(f->surface,LMI_SURF_info+0x1c,offset+pitch*2436u);',
                      'sw(f->surface,LMI_SURF_info+0x1c,(offset+pitch*2436u+4095u)&~4095u);')
prefix=prefix.replace('sw(f->surface,k+0x1c,BYTES);','sw(f->surface,k+0x1c,(BYTES+4095u)&~4095u);')
prefix=prefix.replace('static void show(', 'static void native_tail(void);\nstatic void show(')
prefix=prefix.replace('if(f->stop_after_show)', 'native_tail();if(f->stop_after_show)')
prefix='#include "lmi-gpu-deferred-cache-v71.h"\n#include "lmi-gpu-copy-v66.h"\n'+prefix
original=(prior/'original-compositor.c').read_text()
# Observe real CPU preservation reads/writes without replacing their logic.
original=original.replace('extern void *memcpy(void *,const void *,size_t);',
    'extern void *lmi_test_memcpy(void *,const void *,size_t);\n#define memcpy lmi_test_memcpy')
(out/'original-compositor.c').write_text(original)
fast=(tools/'lmi-display-fast-v62.c').read_text()
fast=fast.replace('static __attribute__((noinline)) int pixels(', 'int lmi_frame_full_pixels(').replace('pixels(swap,','lmi_frame_full_pixels(swap,')
fast=fast.replace('extern void *memcpy(void *,const void *,size_t);',
    'extern void *lmi_test_memcpy(void *,const void *,size_t);\n#define memcpy lmi_test_memcpy')
(out/'fast.c').write_text(fast)
test=out/'check.c';test.write_text(prefix+(tools/'check-lmi-gpu-deferred-cache-v71.c').read_text())
pre=(tools/'lmi-display-preclean-v65.c').read_text()
pre=pre.replace('static int ready(', 'int lmi_frame_preclean_ready(').replace('ready(s)', 'lmi_frame_preclean_ready(s)')
pre=pre.replace('int ok=lmi_preclean_original_clean(s->context,&s->buffer);',
                'extern int lmi_gpu_frame_clean(void *,const struct lmi_frame_buffer *);\n    int ok=lmi_gpu_frame_clean(s->context,&s->buffer);')
(out/'preclean.c').write_text(pre)
flags=['clang','-std=c17','-O2','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-D_POSIX_C_SOURCE=200112L',
       '-Wno-misleading-indentation','-DLMI_PRECLEAN_HOST','-fsanitize=address,undefined',
       '-fno-sanitize-recover=all','-I'+str(tools)]
sources=[test,out/'original-compositor.c',out/'preclean.c',out/'fast.c',*[tools/n for n in
         ['lmi-display-direct-plan-v61.c','lmi-display-pipeline-v51.c']]]
def run(source,label):
    c=subprocess.run([*flags,*map(str,sources),str(source),'-o',str(out/label)],capture_output=True,text=True)
    (attempt/(label+'-compile.log')).write_text(c.stdout+c.stderr)
    if c.returncode:print(c.stdout+c.stderr)
    c.check_returncode()
    result=subprocess.run([str(out/label)],capture_output=True,text=True,timeout=90)
    (attempt/(label+'.log')).write_text(result.stdout+result.stderr)
    return result
production=tools/'lmi-gpu-deferred-cache-v71.c'
result=run(production,'check');print(result.stdout+result.stderr,end='');result.check_returncode()
raw=production.read_text();mutations={
    'missing-preframe-ownership':('if(s->gpu_owned_mask && !full_frame(s,c,p,swap,surfaces,index,ticket))cpu_access(s);','if(0)cpu_access(s);'),
    'missing-fallback-ownership':('cpu_access(s);dirty(s);s->credit=0;s->fallback++;','dirty(s);s->credit=0;s->fallback++;'),
    'eager-post-invalidate':('s->gpu_owned_mask|=1u<<s->pending.index;s->post_deferred++;','cache_sync(s->pending.target,LMI_DMA_BUFFER_BYTES,0);s->gpu_owned_mask|=1u<<s->pending.index;s->post_deferred++;'),
    'publish-stale-cpu-target':('!cache_sync(s->target[n].pixels,LMI_DMA_BUFFER_BYTES,0)','!cache_sync(s->target[n].pixels,LMI_DMA_BUFFER_BYTES,1)'),
    'never-invalidate-dirty-target':('if(!reused && (!cache_sync(', 'if(0 && (!cache_sync('),
    'ignore-completed-cache-epoch':('unsigned reused=!!(s->clean_mask&(1u<<index));', 'unsigned reused=0;'),
    'cpu-writer-keeps-cache-epoch':('cpu_access(s);dirty(s);s->credit=0;s->fallback++;', 'cpu_access(s);s->credit=0;s->fallback++;'),
    'no-draw-or-failure-keeps-cache-epoch':('if(result!=1 || !s->written) {cpu_access(s);dirty(s);}', 'if(0)dirty(s);'),
    'display-before-copy-join':('if(s)finish(s); /* READY', 'if(0)finish(s); /* READY'),
    'failed-frame-without-join':('if(s)finish(s); /* Failed/no-clean', 'if(0)finish(s); /* Failed/no-clean'),
    'wait-whole-queue-again':('int completed=lmi_frame_done(fence);', 'int completed=drain_all(s->pending.backend);'),
    'source-cpu-published':('uint32_t n=lmi_blit_commands(', 'cache_sync(s->pre.original.source,span,1);\n    uint32_t n=lmi_blit_commands('),
    'uncertain-copy-falls-back':('!lmi_blit_completed((void *)s->state.pixels))uncertain(s,d);',
                               '!lmi_blit_completed((void *)s->state.pixels)) {IOLockUnlock(lmi_frame_gpu_lock);return;}'),
    'source-not-retained':('lmi_frame_retain(surface);s->retained++;','s->retained++;'),
    'rollback-not-unmapped':('lmi_desktop_unmap(address,span);redwood_gpu_address_free(address,span);',
                            'redwood_gpu_address_free(address,span);'),
    'credit-reused':('if(s)s->credit=0;\n    if(credit', 'if(s)s->credit=s->credit;\n    if(credit'),
    'credit-ignores-ready':('b==&s->pre.buffer && lmi_frame_preclean_ready(&s->pre)', 'b==&s->pre.buffer'),
    'journal-too-small':('IOMallocAligned(sizeof(struct lmi_gpu_frame_stats),alignment)',
                         'IOMallocAligned(sizeof(struct lmi_preclean_stats),alignment)'),
    'state-read-only':('LMI_BLIT_STATE_BYTES,0,0)', 'LMI_BLIT_STATE_BYTES,1,0)'),
    'missing-marker-check':('!lmi_blit_completed((void *)s->state.pixels)', '0'),
}
caught=[]
for label,(old,new) in mutations.items():
    assert raw.count(old)==1,(label,old)
    if label=='wait-whole-queue-again':new='extern int drain_all(struct lmi_v66_desk *);'+new
    changed=attempt/(label+'.c');changed.write_text(raw.replace(old,new))
    m=run(changed,label);assert m.returncode!=0,('mutation survived',label);caught.append(label)
analysis=subprocess.run(['clang','--analyze','-std=c17','-I'+str(tools),str(production),
                         '-Xanalyzer','-analyzer-output=text'],capture_output=True,text=True,check=True)
(attempt/'static-analysis.log').write_text(analysis.stdout+analysis.stderr);assert not analysis.stdout+analysis.stderr
report=dict(result='PASS',scenarios=int(re.search(r'PASS: (\d+) integrated',result.stdout)[1]),
    actual_v64_backend=True,original_compositor_pipeline=True,separate_cpu_dma_views=True,
    independent_packet_decode=True,state_readback_verified=True,dirty_cacheline_eviction=True,cache_ownership_transitions=True,deferred_cpu_ownership=True,actual_cpu_preservation_observed=True,delayed_gpu_execution=True,copy_fence_join=True,native_tail_submission=True,asan_ubsan=True,mutations_caught=caught,static_analysis=True,
    hardware_tested=False,performance_verified=False,attempt=str(attempt.relative_to(root)),
    sources={n:hashlib.sha256((tools/n).read_bytes()).hexdigest() for n in
             ['lmi-gpu-deferred-cache-v71.c','lmi-gpu-deferred-cache-v71.h','check-lmi-gpu-deferred-cache-v71.c','check-lmi-gpu-deferred-cache-v71.py',
              'lmi-gpu-desktop-v64.c','lmi-display-preclean-v65.c','lmi-gpu-blit-v68.c','lmi-gpu-blit-v68.h']},
    generated_sources={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['check.c','preclean.c','fast.c','original-compositor.c']})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
