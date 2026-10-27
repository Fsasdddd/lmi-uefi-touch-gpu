/* A650 2D blit replaces the one full-frame CPU copy only. The native show,
 * producer retirement, A/B ownership and DPU scaling/commit remain in place.
 * All GPU access and mapping changes use the real gGPULock. No uncertain DMA
 * may return to the CPU fallback. Persistent mappings/retains are bounded;
 * they stay wired until the existing RAM-run return, just like the backend.
 */
#include "lmi-gpu-frame-v68.h"
#include "lmi-gpu-blit-v68.c"
#include "lmi-gpu-copy-v66.h"
#include "lmi-display-compositor-abi.h"
#include "lmi-display-surface-abi.h"
extern void *IOMallocAligned(size_t,size_t);
extern void bzero(void *,size_t);
extern void *lmi_frame_gpu_lock;
extern void IOLockLock(void *),IOLockUnlock(void *);
extern struct lmi_v66_desk *lmi_frame_backend(void);
extern int lmi_frame_drain(struct lmi_v66_desk *);
extern _Noreturn void lmi_frame_hold(struct lmi_v66_desk *);
extern uint64_t lmi_frame_ticks(void),lmi_frame_physical(uintptr_t);
extern uint64_t redwood_gpu_address(uint64_t);
extern void redwood_gpu_address_free(uint64_t,uint64_t);
extern int lmi_desktop_map(uint64_t,uint64_t,int);
extern void lmi_desktop_mapped(void),lmi_desktop_unmap(uint64_t,uint64_t);
extern void lmi_desktop_to_memory(void *,uint64_t);
extern uint32_t lmi_desktop_submit(const uint64_t *,const uint32_t *,uint32_t);
extern int cache_sync(uint64_t,uint32_t,int);
extern void lmi_frame_retain(const void *),lmi_frame_release(const void *);
extern int lmi_frame_preclean_ready(const struct lmi_preclean_stats *);
extern int lmi_preclean_original_clean(void *,const struct lmi_frame_buffer *);
extern void lmi_frame_emit(const char *,const uint64_t *,unsigned);
_Static_assert(offsetof(struct lmi_gpu_frame_stats,pipeline)==sizeof(struct lmi_preclean_stats),"frozen preclean prefix");
_Static_assert(offsetof(struct lmi_gpu_frame_stats,held)-offsetof(struct lmi_gpu_frame_stats,draws)==13*8,"fourteen statistics");
static struct lmi_gpu_frame_stats *statistics(void)
{return (void *)__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);}
static uintptr_t pointer(const void *p,unsigned at)
{return *(const uintptr_t *)((const unsigned char *)p+at);}
static uint32_t word(const void *p,unsigned at)
{return *(const uint32_t *)((const unsigned char *)p+at);}
static __attribute__((noinline)) _Noreturn void uncertain(struct lmi_gpu_frame_stats *s,struct lmi_v66_desk *d)
{s->credit=0;s->held++;lmi_frame_hold(d);}
void *lmi_gpu_frame_allocate(size_t bytes,size_t alignment)
{
    if(bytes!=sizeof(struct lmi_fast_stats) || alignment!=16)return 0;
    void *p=IOMallocAligned(sizeof(struct lmi_gpu_frame_stats),alignment);
    if(p)bzero(p,sizeof(struct lmi_gpu_frame_stats));
    return p;
}
/* map() may fail after a partially written page-table batch. Commit that
 * batch before unmapping it, and only then return the VA to the allocator.
 * The native backend holds rather than returning on uncertain publication.
 */
static __attribute__((noinline)) int mapping(struct lmi_gpu_frame_stats *s,
    struct lmi_frame_mapping *m,uintptr_t pixels,uint32_t span,int ro,void *surface)
{
    uint64_t address=redwood_gpu_address(span);if(!address)return 0;
    if(surface) {lmi_frame_retain(surface);s->retained++;}
    uint32_t at;
    for(at=0;at<span;at+=4096) {
        uint64_t pa=lmi_frame_physical(pixels+at);
        if(!pa || !lmi_desktop_map(address+at,pa,ro))break;
    }
    lmi_desktop_mapped();
    if(at!=span) {
        lmi_desktop_unmap(address,span);redwood_gpu_address_free(address,span);
        if(surface) {lmi_frame_release(surface);s->released++;}
        return 0;
    }
    *m=(struct lmi_frame_mapping){pixels,address,span,surface};s->map_new++;return 1;
}
static __attribute__((noinline)) struct lmi_frame_mapping *source_mapping(
    struct lmi_gpu_frame_stats *s,void *surface,uint32_t span)
{
    uintptr_t pixels=s->pre.original.source;
    for(unsigned n=0;n<LMI_GPU_FRAME_SOURCES;n++) {
        struct lmi_frame_mapping *m=s->source+n;
        if(m->surface==surface && m->pixels==pixels && m->span==span) {s->map_hits++;return m;}
    }
    unsigned n;
    for(n=0;n<LMI_GPU_FRAME_SOURCES;n++)if(!s->source[n].address)break;
    if(n==LMI_GPU_FRAME_SOURCES) {
        n=s->victim;s->victim=(n+1)%LMI_GPU_FRAME_SOURCES;
        struct lmi_frame_mapping *m=s->source+n;
        lmi_desktop_unmap(m->address,m->span);redwood_gpu_address_free(m->address,m->span);
        lmi_frame_release(m->surface);s->released++;s->evicted++;*m=(struct lmi_frame_mapping){0};
    }
    return mapping(s,s->source+n,pixels,span,1,surface)?s->source+n:0;
}
static __attribute__((noinline)) int command_mapping(struct lmi_gpu_frame_stats *s)
{
    uintptr_t p=s->commands.pixels;
    if(!p) {p=(uintptr_t)IOMallocAligned(8192,4096);if(!p)return 0;s->commands.pixels=p;}
    if(!s->commands.address && !mapping(s,&s->commands,p,LMI_BLIT_COMMAND_BYTES,1,0))return 0;
    return s->state.address || mapping(s,&s->state,p+4096,LMI_BLIT_STATE_BYTES,0,0);
}
static __attribute__((noinline)) int copy(struct lmi_gpu_frame_stats *s,unsigned index,void *surface)
{
    struct lmi_fast_stats *f=&s->pre.original;
    uint32_t span=(f->source_pitch*2436u+4095u)&~4095u;
    uintptr_t base=pointer(surface,LMI_SURF_kpixels);
    uint32_t available=word(surface,LMI_SURF_info+0x1c),fence=word(surface,LMI_SURF_drawn);
    if(!lmi_frame_gpu_lock || !fence || !base || f->source<base || f->source-base>available ||
       span>available-(f->source-base) || (f->source|f->target)&4095)return 0;
    IOLockLock(lmi_frame_gpu_lock);
    struct lmi_v66_desk *d=lmi_frame_backend();int ok=0;
    if(!d || !d->ready || d->failed || d->mapping)goto leave;
    if(!lmi_frame_drain(d))uncertain(s,d);
    /* show() already waited. Recheck under the producer's real GPU lock. */
    if(fence>d->done || word(surface,LMI_SURF_drawn)!=fence)goto leave;
    struct lmi_frame_mapping *target=s->target+index;
    if(target->address && (target->pixels!=f->target || target->span!=LMI_DMA_BUFFER_BYTES))goto leave;
    if(!target->address && !mapping(s,target,f->target,LMI_DMA_BUFFER_BYTES,0,0))goto leave;
    if(!command_mapping(s))goto leave;
    struct lmi_frame_mapping *source=source_mapping(s,surface,span);if(!source)goto leave;
    uint32_t n=lmi_blit_commands((void *)s->commands.pixels,source->address,
        target->address,s->state.address,f->source_pitch);
    if(!n || n>LMI_BLIT_COMMAND_BYTES/4)goto leave;
    bzero((void *)s->state.pixels,LMI_BLIT_STATE_BYTES);
    /* Discard no dirty CPU bytes: publish then invalidate the entire owned
     * destination before its writer changes. Source is GPU-produced and is
     * NEVER CPU-published here, which could overwrite fresh GPU pixels.
     */
    if(!cache_sync(f->target,LMI_DMA_BUFFER_BYTES,1) || !cache_sync(f->target,LMI_DMA_BUFFER_BYTES,0) ||
       !cache_sync(s->commands.pixels,n*4,1) ||
       !cache_sync(s->state.pixels,LMI_BLIT_STATE_BYTES,1) ||
       !cache_sync(s->state.pixels,LMI_BLIT_STATE_BYTES,0))goto leave;
    lmi_desktop_to_memory(0,0);
    uint64_t began=lmi_frame_ticks();
    uint32_t submitted=lmi_desktop_submit(&s->commands.address,&n,1);
    if(!submitted || !lmi_frame_drain(d) || d->done<submitted ||
       !cache_sync(s->state.pixels,LMI_BLIT_STATE_BYTES,0) ||
       !lmi_blit_completed((void *)s->state.pixels) ||
       !cache_sync(f->target,LMI_DMA_BUFFER_BYTES,0))uncertain(s,d);
    s->copy_ticks+=lmi_frame_ticks()-began;
    s->draws++;s->bytes+=f->bytes;
    if(f->source_pitch==4544)s->linear++;else s->strided++;
    s->written=1;s->credit=1;s->completed_target=f->target;ok=1;
leave:
    IOLockUnlock(lmi_frame_gpu_lock);return ok;
}
static __attribute__((noinline)) int eligible(struct lmi_gpu_frame_stats *s,void *self,void *surface)
{
    struct lmi_fast_stats *f=&s->pre.original;struct lmi_display_pipeline *p=s->pipeline;
    if(!p || !f->active || self!=f->self || surface!=f->surface || !surface ||
       p->failed || p->stopping || p->detached || !p->initialized ||
       f->bytes!=4544u*2436u || (f->source_pitch!=4544 && f->source_pitch!=4608) ||
       pointer(self,LMI_FB_fBase)!=f->target || word(self,LMI_FB_fPanelWidth)!=1125 ||
       word(self,LMI_FB_fPanelHeight)!=2436 || word(self,LMI_FB_fRowBytes)!=4544)return -1;
    for(unsigned n=0;n<2;n++)if(p->buffer[n].pixels==f->target && p->buffer[n].bytes==LMI_DMA_BUFFER_BYTES &&
        p->buffer[n].pitch==4544 && p->buffer[n].width==1125 && p->buffer[n].height==2436 &&
        p->state[n]==LMI_WRITING && p->ticket[n] && p->ticket[n]==p->serial && p->scanning!=(int)n)return (int)n;
    return -1;
}
void lmi_gpu_frame_draw(void *self,void *surface,const int32_t *src,const int32_t *dst)
{
    struct lmi_gpu_frame_stats *s=statistics();
    if(s) {
        int n=eligible(s,self,surface);
        if(n>=0 && !s->written && copy(s,(unsigned)n,surface))return;
        s->credit=0;s->fallback++;
    }
    lmi_fast_draw(self,surface,src,dst); /* CPU counters remain CPU copies only. */
}
int lmi_gpu_frame_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *swap,void **surfaces,unsigned *index,uint64_t *ticket)
{
    struct lmi_gpu_frame_stats *s=statistics();
    if(s) {s->credit=0;s->written=0;s->completed_target=0;s->pipeline=p;}
    int result=lmi_preclean_frame(c,p,swap,surfaces,index,ticket);
    if(s && result==1 && s->written)s->frames++;
    if(s)s->credit=0;
    return result;
}
/* Only the early native-clean BL is replaced. The v65 READY/ticket/descriptor
 * checks still run, and its existing one-use DPU credit remains unchanged.
 */
int lmi_gpu_frame_clean(void *context,const struct lmi_frame_buffer *b)
{
    struct lmi_gpu_frame_stats *s=statistics();int credit=s && s->credit;
    if(s)s->credit=0;
    if(credit && b && context==s->pre.context && b->pixels==s->completed_target &&
       b==&s->pre.buffer && lmi_frame_preclean_ready(&s->pre)) {
        __atomic_thread_fence(__ATOMIC_RELEASE);s->skipped_clean++;return 1;
    }
    return lmi_preclean_original_clean(context,b);
}
void lmi_gpu_frame_cleanup(void)
{
    lmi_preclean_cleanup(); /* All presenter CPUs stop before statistics. */
    struct lmi_gpu_frame_stats *s=statistics();
    /* Do not acquire a lock possibly owned by a stopped CPU. Backend's next
     * return hook really drains GPU; allocations and retained surfaces remain
     * owned until the RAM run ends. No unmap/free claim is made here.
     */
    /* The frozen formatter has 256 bytes: at most ten uint64 values per
     * record. Two seven-value records also cover UINT64_MAX safely. */
    if(s) {
        lmi_frame_emit("LMI_GPU_BLIT",&s->draws,7);
        lmi_frame_emit("LMI_GPU_BLIT_LIFETIME",&s->evicted,7);
    }
}
