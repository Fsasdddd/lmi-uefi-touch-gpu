"""Derive independent deferred-cache tests from the pinned v70 harness."""
from pathlib import Path
r=Path(__file__).resolve().parents[1];t=r/'tools'
def write(n,s):
    p=t/n;assert not p.exists(),p;p.write_text(s)
c=(t/'check-lmi-gpu-overlap-v70.c').read_text().replace('"lmi-gpu-overlap-v70.h"','"lmi-gpu-deferred-cache-v71.h"')
# Pixel comparisons consume DMA bytes, as DPU does. Only actual CPU path
# transitions may make the cached CPU view equal to the current GPU pixels.
c=c.replace('''        assert(!memcmp((void *)(f->p.buffer[n].pixels+y*4544),memory[si].expected+y*f->source_pitch,4544));
''','')
c=c.replace('uint32_t expected=((uint32_t *)f->p.buffer[n].pixels)[2];',
            'uint32_t expected=((uint32_t *)memory[region(f->p.buffer[n].pixels,1)].dma)[2];')
c=c.replace('memcpy(saved,(void *)both->p.buffer[n].pixels,BYTES);','memcpy(saved,memory[region(both->p.buffer[n].pixels,1)].dma,BYTES);')
c=c.replace('!memcmp(saved,(void *)both->p.buffer[n].pixels,BYTES)','!memcmp(saved,memory[region(both->p.buffer[n].pixels,1)].dma,BYTES)')
c=c.replace('"LMI_GPU_COPY_PENDING"};','"LMI_GPU_COPY_PENDING","LMI_GPU_CPU_TRANSFER","LMI_GPU_CPU_OWNED"};')
c=c.replace('counts[]={7,7,5,6,1};assert(frame_emit_count<5','counts[]={7,7,5,6,1,4,1};assert(frame_emit_count<7')
c=c.replace('frame_emit_count==5','frame_emit_count==7')
c=c.replace('while keeping the completion-side invalidation and equal CPU/DMA pixels.',
            'while leaving continuous GPU targets owned by DMA and CPU views stale.')
c=c.replace('assert(stats()->target_prepared==1 && stats()->target_reused==7 && stats()->clean_mask==1);',
'''assert(stats()->target_prepared==1 && stats()->target_reused==7 && stats()->clean_mask==1);
    assert(stats()->post_deferred==8 && !stats()->cpu_sync_targets && stats()->gpu_owned_mask==1);
    assert(memcmp((void *)cache->p.buffer[n].pixels,memory[region(cache->p.buffer[n].pixels,1)].dma,BYTES));''')
c=c.replace('gpu_frame(cache,cache->surface,&n,&ticket)==-1 && !stats()->clean_mask && !stats()->credit',
            'gpu_frame(cache,cache->surface,&n,&ticket)==-1 && !stats()->clean_mask && !stats()->credit && !stats()->gpu_owned_mask')
at=c.index('    printf("PASS:')
c=c[:at]+'''    /* A full-frame admission can still fall back after source-fence/map
     * refusal. Ownership must transfer BEFORE the CPU draw writes. */
    cache=make_gpu(4544);assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);finish(cache,n,ticket);
    sw(cache->surface,LMI_SURF_drawn,0);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1 && stats()->pre.original.copies==1);
    assert(stats()->cpu_sync_targets==1 && !stats()->gpu_owned_mask);finish(cache,n,ticket);destroy_gpu(cache);scenarios++;
    /* A partial frame needs both the newest prior GPU composition AND the
     * old target's CPU view before original compositor preservation begins. */
    cache=make_gpu(4608);assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);
    assert(lmi_pipeline_submit(&cache->p,n,ticket,0)==1);
    assert(gpu_frame(cache,cache->surface,&m,&ticket)==1 && n!=m && stats()->gpu_owned_mask==3);
    cache->p.state[n]=LMI_FREE;cache->p.scanning=-1;finish(cache,m,ticket);
    sw(cache->swap,0x64,3);sw(cache->swap,0x68,4);sw(cache->swap,0x6c,2);sw(cache->swap,0x70,2);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1 && stats()->cpu_sync_targets==2 && !stats()->gpu_owned_mask);
    finish(cache,n,ticket);destroy_gpu(cache);scenarios++;
    /* Refuse failed CPU ownership transfer; no stale CPU fallback or DPU. */
    cache=make_gpu(4544);assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);finish(cache,n,ticket);
    sw(cache->swap,0x64,3);sw(cache->swap,0x68,4);sw(cache->swap,0x6c,2);sw(cache->swap,0x70,2);fault=13;
    if(!setjmp(escape)) {gpu_frame(cache,cache->surface,&n,&ticket);assert(!"CPU ownership failure returned");}
    assert(stats()->held==1 && stats()->gpu_owned_mask && !stats()->pre.original.copies);
    lmi_fast_state->active=0;sp(cache->fb,LMI_FB_fBase,(uintptr_t)cache->gop);
    sp(cache->fb,LMI_FB_fColumn,0x1234);sp(cache->fb,LMI_FB_fColumnWeight,0x5678);locked=0;
    destroy_gpu(cache);scenarios++;
'''+c[at:]
c=c.replace('    if(fault==4 && publish', '''    struct lmi_gpu_frame_stats *owned=(void *)lmi_fast_state;
    for(unsigned target=0;target<2;target++)if(p==owned->target[target].pixels && n>=LMI_DMA_BUFFER_BYTES && (owned->gpu_owned_mask&(1u<<target))) {
        assert(!publish);if(fault==13)return 0;
    }
    if(fault==4 && publish''')
at=c.index('/* Called only by test')
c=c[:at]+'''void *lmi_test_memcpy(void *dst,const void *src,size_t bytes)
{
    struct lmi_gpu_frame_stats *s=stats();
    for(unsigned n=0;n<2;n++)if(s->target[n].address) {
        uintptr_t start=s->target[n].pixels,end=start+LMI_DMA_BUFFER_BYTES;
        uintptr_t from=(uintptr_t)src,to=(uintptr_t)dst;
        if((from<end && start<from+bytes) || (to<end && start<to+bytes))assert(!(s->gpu_owned_mask&(1u<<n)));
    }
    return memcpy(dst,src,bytes);
}
'''+c[at:]
write('check-lmi-gpu-deferred-cache-v71.c',c)
p=(t/'check-lmi-gpu-overlap-v70.py').read_text().replace('lmi-gpu-overlap-v70','lmi-gpu-deferred-cache-v71')
p=p.replace("assert(!((struct lmi_gpu_frame_stats *)lmi_fast_state)->clean_mask);'", "assert(!((struct lmi_gpu_frame_stats *)lmi_fast_state)->clean_mask && !((struct lmi_gpu_frame_stats *)lmi_fast_state)->gpu_owned_mask);'")
at=p.index("test=out/'check.c'")
p=p[:at]+'''original=(prior/'original-compositor.c').read_text()
# Observe real CPU preservation reads/writes without replacing their logic.
original=original.replace('extern void *memcpy(void *,const void *,size_t);',
    'extern void *lmi_test_memcpy(void *,const void *,size_t);\\n#define memcpy lmi_test_memcpy')
(out/'original-compositor.c').write_text(original)
fast=(tools/'lmi-display-fast-v62.c').read_text()
fast=fast.replace('static __attribute__((noinline)) int pixels(', 'int lmi_frame_full_pixels(').replace('pixels(swap,','lmi_frame_full_pixels(swap,')
fast=fast.replace('extern void *memcpy(void *,const void *,size_t);',
    'extern void *lmi_test_memcpy(void *,const void *,size_t);\\n#define memcpy lmi_test_memcpy')
(out/'fast.c').write_text(fast)
'''+p[at:]
p=p.replace("sources=[test,prior/'original-compositor.c',out/'preclean.c',*[tools/n for n in\n         ['lmi-display-fast-v62.c','lmi-display-direct-plan-v61.c','lmi-display-pipeline-v51.c']]]",
"sources=[test,out/'original-compositor.c',out/'preclean.c',out/'fast.c',*[tools/n for n in\n         ['lmi-display-direct-plan-v61.c','lmi-display-pipeline-v51.c']]]")
# Preserve all old safety mutations except the eager invalidate, which is the
# operation intentionally deferred. Add mutations of each new transition.
old="'missing-post-invalidate':('!cache_sync(s->pending.target,LMI_DMA_BUFFER_BYTES,0))uncertain(s,d);','0)uncertain(s,d);'),"
assert old in p;p=p.replace(old,"""'missing-preframe-ownership':('if(s->gpu_owned_mask && !full_frame(s,c,p,swap,surfaces,index,ticket))cpu_access(s);','if(0)cpu_access(s);'),
    'missing-fallback-ownership':('cpu_access(s);dirty(s);s->credit=0;s->fallback++;','dirty(s);s->credit=0;s->fallback++;'),
    'eager-post-invalidate':('s->gpu_owned_mask|=1u<<s->pending.index;s->post_deferred++;','cache_sync(s->pending.target,LMI_DMA_BUFFER_BYTES,0);s->gpu_owned_mask|=1u<<s->pending.index;s->post_deferred++;'),
    'publish-stale-cpu-target':('!cache_sync(s->target[n].pixels,LMI_DMA_BUFFER_BYTES,0)','!cache_sync(s->target[n].pixels,LMI_DMA_BUFFER_BYTES,1)'),""")
p=p.replace("'if(result!=1 || !s->written)dirty(s);'", "'if(result!=1 || !s->written) {cpu_access(s);dirty(s);}'")
p=p.replace("'uncertain-copy-falls-back':('!cache_sync(s->pending.target,LMI_DMA_BUFFER_BYTES,0))uncertain(s,d);',\n                               '!cache_sync(s->pending.target,LMI_DMA_BUFFER_BYTES,0)) {IOLockUnlock(lmi_frame_gpu_lock);return;}'),",
"'uncertain-copy-falls-back':('!lmi_blit_completed((void *)s->state.pixels))uncertain(s,d);',\n                               '!lmi_blit_completed((void *)s->state.pixels)) {IOLockUnlock(lmi_frame_gpu_lock);return;}'),")
p=p.replace("'dirty(s);s->credit=0;s->fallback++;', 's->credit=0;s->fallback++;'", "'cpu_access(s);dirty(s);s->credit=0;s->fallback++;', 'cpu_access(s);s->credit=0;s->fallback++;'")
p=p.replace("cache_ownership_transitions=True,delayed_gpu_execution=True", "cache_ownership_transitions=True,deferred_cpu_ownership=True,actual_cpu_preservation_observed=True,delayed_gpu_execution=True")
p=p.replace("['check.c','preclean.c']", "['check.c','preclean.c','fast.c','original-compositor.c']")
write('check-lmi-gpu-deferred-cache-v71.py',p)
