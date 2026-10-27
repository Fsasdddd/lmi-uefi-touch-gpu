"""Derive a new cache-ownership regression harness without touching v68."""
from pathlib import Path
root=Path(__file__).resolve().parents[1];t=root/'tools'
def write(n,s):
    p=t/n;assert not p.exists(),p;p.write_text(s)
c=(t/'check-lmi-gpu-frame-v68.c').read_text().replace('"lmi-gpu-frame-v68.h"','"lmi-gpu-cache-v69.h"')
c=c.replace('unsigned char *dma,*expected;','unsigned char *dma,*expected,*clean;')
c=c.replace('    memory[i].pa=i?',
'''    memory[i].clean=malloc(bytes);assert(memory[i].clean);memcpy(memory[i].clean,p,bytes);
    memory[i].pa=i?''')
c=c.replace('static uint32_t fetch(','''/* Evict dirty CPU cachelines AFTER the 2D write, as may happen on real
 * noncoherent hardware. Clean cached reads must not overwrite GPU memory. */
static void evict_dirty(uint64_t dst)
{
    uint64_t pa=page[dst>>12]+(dst&4095);
    for(unsigned i=0;i<memory_count;i++)if(pa==memory[i].pa) {
        assert(memory[i].size>=BYTES);
        for(size_t at=0;at<BYTES;at+=64) {
            if(memcmp((void *)(memory[i].cpu+at),memory[i].clean+at,64)) {
                memcpy(memory[i].dma+at,(void *)(memory[i].cpu+at),64);
                memcpy(memory[i].clean+at,(void *)(memory[i].cpu+at),64);
            }
        }
        return;
    }
    assert(!"target physical allocation missing");
}
static uint32_t fetch(''')
c=c.replace('                        flushed=1;', '                        evict_dirty(dst);flushed=1;')
c=c.replace('''    if(publish)memcpy(memory[i].dma+at,(void *)(uintptr_t)p,n);else memcpy((void *)(uintptr_t)p,memory[i].dma+at,n);
    return 1;''','''    if(publish)memcpy(memory[i].dma+at,(void *)(uintptr_t)p,n);else memcpy((void *)(uintptr_t)p,memory[i].dma+at,n);
    memcpy(memory[i].clean+at,(void *)(uintptr_t)p,n);
    return 1;''')
c=c.replace('''{assert(current->stop && !locked && n==7 && p);assert(!strcmp(tag,frame_emit_count?"LMI_GPU_BLIT_LIFETIME":"LMI_GPU_BLIT"));frame_emit_count++;}''',
'''{assert(current->stop && !locked && p);assert(n==(frame_emit_count==2?5u:7u));
 assert(!strcmp(tag,frame_emit_count==2?"LMI_GPU_TARGET_CACHE":frame_emit_count?"LMI_GPU_BLIT_LIFETIME":"LMI_GPU_BLIT"));frame_emit_count++;}''')
c=c.replace('free(memory[i].expected);','free(memory[i].expected);free(memory[i].clean);')
c=c.replace('frame_emit_count==2 && refs==1', 'frame_emit_count==3 && refs==1')
at=c.index('    printf("PASS:')
extra='''    /* Repeated reuse must remove two actual full-target cache traversals,
     * while keeping the completion-side invalidation and equal CPU/DMA pixels. */
    struct fixture *cache=make_gpu(4544);
    for(unsigned i=0;i<8;i++) {
        assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    }
    assert(stats()->target_prepared==1 && stats()->target_reused==7 && stats()->clean_mask==1);
    assert(stats()->target_bytes_saved==14ull*LMI_DMA_BUFFER_BYTES && stats()->target_prepare_ticks>0);
    /* An aborted no-draw bottom-layer clear leaves dirty CPU lines. The next
     * GPU full frame must publish/invalidate them before its new writer. */
    cache->bad_join=1;
    assert(gpu_frame(cache,0,&n,&ticket)==-1 && !stats()->clean_mask);
    assert(lmi_pipeline_cancel_frame(&cache->p,n,ticket)==1);
    cache->bad_join=0;sw(cache->fb,LMI_FB_fHelpersBusy,0);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    assert(stats()->target_prepared==2 && stats()->dirty_resets==1);destroy_gpu(cache);scenarios++;
    /* Both buffers retain separate clean state; using B cannot grant A credit. */
    cache=make_gpu(4608);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1 && lmi_pipeline_submit(&cache->p,n,ticket,0)==1);
    assert(gpu_frame(cache,cache->surface,&m,&ticket)==1 && m!=n && stats()->target_prepared==2 && stats()->clean_mask==3);
    cache->p.state[n]=LMI_FREE;cache->p.scanning=-1;finish(cache,m,ticket);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    assert(stats()->target_prepared==2 && stats()->target_reused==1);destroy_gpu(cache);scenarios++;
    /* CPU partial fallback revokes ownership BEFORE the native row writer,
     * including failure before READY/preclean. Real cacheline eviction above
     * detects stale CPU writes overwriting the following GPU full frame. */
    cache=make_gpu(4544);assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);finish(cache,n,ticket);
    sw(cache->swap,0x64,3);sw(cache->swap,0x68,4);sw(cache->swap,0x6c,2);sw(cache->swap,0x70,2);
    cache->bad_join=1;assert(gpu_frame(cache,cache->surface,&n,&ticket)==-1 && !stats()->clean_mask);
    assert(lmi_pipeline_cancel_frame(&cache->p,n,ticket)==1);
    cache->bad_join=0;sw(cache->fb,LMI_FB_fHelpersBusy,0);
    sw(cache->swap,0x64,0);sw(cache->swap,0x68,0);sw(cache->swap,0x6c,0);sw(cache->swap,0x70,0);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    assert(stats()->target_prepared==2);destroy_gpu(cache);scenarios++;
    /* A failed frame after a completed GPU draw grants neither a cache epoch
     * nor display-clean credit to its successor. */
    cache=make_gpu(4544);cache->bad_join=1;
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==-1 && !stats()->clean_mask && !stats()->credit);
    assert(lmi_pipeline_cancel_frame(&cache->p,n,ticket)==1);
    cache->bad_join=0;sw(cache->fb,LMI_FB_fHelpersBusy,0);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    assert(stats()->target_prepared==2 && !stats()->target_reused);destroy_gpu(cache);scenarios++;
'''
c=c[:at]+extra+c[at:]
write('check-lmi-gpu-cache-v69.c',c)
p=(t/'check-lmi-gpu-frame-v68.py').read_text().replace('lmi-gpu-frame-v68','lmi-gpu-cache-v69')
p=p.replace("prefix=prefix.replace('lmi_fast_draw(self,surfaces[0]', 'lmi_gpu_frame_draw(self,surfaces[0]')",'''prefix=prefix.replace('lmi_fast_draw(self,surfaces[0]', 'lmi_gpu_frame_draw(self,surfaces[0]')
prefix=prefix.replace('lmi_gpu_frame_draw(self,surfaces[0],(const int32_t *)(swap+0x64),(const int32_t *)(swap+0xc4));',
    'if(surfaces[0])lmi_gpu_frame_draw(self,surfaces[0],(const int32_t *)(swap+0x64),(const int32_t *)(swap+0xc4));'
    'else for(unsigned y=0;y<2436;y++)memset((void *)(rp(self,LMI_FB_fBase)+y*4544u),0,1125u*4);')
prefix=prefix.replace('f->draws++;', 'f->draws++;assert(!((struct lmi_gpu_frame_stats *)lmi_fast_state)->clean_mask);')''')
p=p.replace("    'source-cpu-published':",'''    'never-invalidate-dirty-target':('if(!reused && (!cache_sync(', 'if(0 && (!cache_sync('),
    'ignore-completed-cache-epoch':('unsigned reused=!!(s->clean_mask&(1u<<index));', 'unsigned reused=0;'),
    'cpu-writer-keeps-cache-epoch':('dirty(s);s->credit=0;s->fallback++;', 's->credit=0;s->fallback++;'),
    'no-draw-or-failure-keeps-cache-epoch':('if(result!=1 || !s->written)dirty(s);', 'if(0)dirty(s);'),
    'source-cpu-published':''')
p=p.replace("independent_packet_decode=True,state_readback_verified=True,asan_ubsan=True", "independent_packet_decode=True,state_readback_verified=True,dirty_cacheline_eviction=True,cache_ownership_transitions=True,asan_ubsan=True")
write('check-lmi-gpu-cache-v69.py',p)
