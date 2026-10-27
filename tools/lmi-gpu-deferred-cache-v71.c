/* A650 2D blit replaces the one full-frame CPU copy only. The native show,
 * producer retirement, A/B ownership and DPU scaling/commit remain in place.
 * All GPU access and mapping changes use the real gGPULock. No uncertain DMA
 * may return to the CPU fallback. Persistent mappings/retains are bounded;
 * they stay wired until the existing RAM-run return, just like the backend.
 */
#include "lmi-gpu-deferred-cache-v71.h"
#include "lmi-gpu-blit-v68.c"
#include "lmi-gpu-copy-v66.h"
#include "lmi-display-compositor-abi.h"
#include "lmi-display-surface-abi.h"
extern void *IOMallocAligned(size_t,size_t);
extern void bzero(void *,size_t);
extern void *lmi_frame_gpu_lock;
extern void IOLockLock(void *),IOLockUnlock(void *);
extern struct lmi_v66_desk *lmi_frame_backend(void);
extern int lmi_frame_done(uint32_t);
extern int lmi_frame_full_pixels(const unsigned char *,void **,struct lmi_direct_plan *,struct lmi_fast_stats *);
extern void lmi_frame_pause(uint32_t,uint32_t);
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
/* GPU-written pixels need no CPU cache publication for DPU DMA. Transfer
 * both targets back BEFORE a CPU preservation/read/write can run. Invalidation
 * never publishes stale speculative clean CPU lines over newer GPU pixels.
 * One presenter owns this mask; no allocation is freed during the RAM run. */
static __attribute__((noinline)) void cpu_access(struct lmi_gpu_frame_stats *s)
{
    if(!s->gpu_owned_mask)return;
    uint64_t began=lmi_frame_ticks();
    for(unsigned n=0;n<2;n++)if(s->gpu_owned_mask&(1u<<n)) {
        if(!s->target[n].address || !cache_sync(s->target[n].pixels,LMI_DMA_BUFFER_BYTES,0)) {
            IOLockLock(lmi_frame_gpu_lock);uncertain(s,s->pending.backend);
        }
        s->gpu_owned_mask&=~(1u<<n);s->cpu_sync_targets++;
        s->cpu_sync_bytes+=LMI_DMA_BUFFER_BYTES;
    }
    s->cpu_sync_ticks+=lmi_frame_ticks()-began;
}
/* Mirror the frozen fast wrapper's exact admission BEFORE its compositor
 * can read the previous target. Decode via its actual compiled pixels helper;
 * no client pointer or alternate ABI is admitted here. A later mapping/copy
 * refusal transfers ownership in draw() before the CPU fallback writes. */
static __attribute__((noinline)) int full_frame(struct lmi_gpu_frame_stats *s,
    struct lmi_compositor *c,struct lmi_display_pipeline *p,const unsigned char *swap,
    void **surfaces,unsigned *index,uint64_t *ticket)
{
    struct lmi_direct_plan plan;
    if(s->pre.original.active || !c || !c->initialized || !p || !p->initialized ||
       p->failed || p->stopping || p->detached || p->serial==UINT64_MAX || !index || !ticket ||
       !lmi_fast_original_fields(c) || !lmi_frame_full_pixels(swap,surfaces,&plan,&s->pre.original))return 0;
    for(unsigned n=0;n<2;n++)if(p->state[n]==LMI_FREE) {
        const struct lmi_frame_buffer *b=p->buffer+n;
        return b->width==1125 && b->height==2436 && b->pitch==4544 && b->bytes>=4544u*2436u &&
            b->bytes<=UINTPTR_MAX-b->pixels &&
            (plan.pixels+plan.bytes<=b->pixels || b->pixels+b->bytes<=plan.pixels);
    }
    return 0;
}
static void dirty(struct lmi_gpu_frame_stats *s)
{
    if(s->clean_mask)s->dirty_resets++;
    s->clean_mask=0;
}
/* Called before any display clean, fallback writer or source retirement.
 * Another producer may enqueue after our fence while we are unlocked. A real
 * TS completion suffices; waiting for the entire queue would serialize them.
 * Private command/status pages are never reused before this join finishes. */
static __attribute__((noinline)) void finish(struct lmi_gpu_frame_stats *s)
{
    if(!s->pending.fence)return;
    uint32_t fence=s->pending.fence;
    unsigned later=0;
    for(unsigned poll=0;poll<1000;poll++) {
        IOLockLock(lmi_frame_gpu_lock);
        struct lmi_v66_desk *d=lmi_frame_backend();
        if(d!=s->pending.backend || !d || !d->ready || d->failed || d->mapping)
            uncertain(s,s->pending.backend);
        s->wait_polls++;
        if(d->fence>fence)later=1;
        int completed=lmi_frame_done(fence);
        if(d->failed)uncertain(s,d);
        if(completed) {
            if(d->done<fence ||
               !cache_sync(s->state.pixels,LMI_BLIT_STATE_BYTES,0) ||
               !lmi_blit_completed((void *)s->state.pixels))uncertain(s,d);
            s->gpu_owned_mask|=1u<<s->pending.index;s->post_deferred++;
            s->copy_ticks+=lmi_frame_ticks()-s->pending.began;
            s->clean_mask|=1u<<s->pending.index;
            if(s->pending.reused) {s->target_reused++;s->target_bytes_saved+=2ull*LMI_DMA_BUFFER_BYTES;}
            else s->target_prepared++;
            s->target_prepare_ticks+=s->pending.prepare_ticks;
            s->draws++;s->bytes+=s->pending.bytes;
            if(s->pending.pitch==4544)s->linear++;else s->strided++;
            s->written=1;s->credit=1;s->completed_target=s->pending.target;
            s->pending.fence=0;s->finished++;s->later_queued+=later;
            IOLockUnlock(lmi_frame_gpu_lock);return;
        }
        s->busy_polls++;
        IOLockUnlock(lmi_frame_gpu_lock);
        uint64_t began=lmi_frame_ticks();
        if(poll<20)while(lmi_frame_ticks()-began<1920) {}
        else lmi_frame_pause(100,1000);
        s->unlocked_ticks+=lmi_frame_ticks()-began;
    }
    IOLockLock(lmi_frame_gpu_lock);
    uncertain(s,s->pending.backend);
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
    /* show() already waited for THIS source. Mapping changes retain their
     * original real drain; cached private buffers do not need a global idle. */
    if(!lmi_frame_done(fence) || d->failed)uncertain(s,d);
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
    /* Reuse only this exact private target after a successful GPU write with
     * no intervening CPU writer. No compositor preservation/bootstrap/padding writer
     * runs before the qualified draw (the frozen fast wrapper sets latest).
     * CPU fallback, a no-draw swap, failed frame or owner change revokes both
     * bits after transferring ownership for ordinary-frame reads/writes.
     * Source is GPU-produced and must NEVER be CPU-published here.
     */
    unsigned reused=!!(s->clean_mask&(1u<<index));
    uint64_t prepare_began=lmi_frame_ticks();
    if(!reused && (!cache_sync(f->target,LMI_DMA_BUFFER_BYTES,1) ||
                  !cache_sync(f->target,LMI_DMA_BUFFER_BYTES,0)))goto leave;
    uint64_t prepare_ticks=lmi_frame_ticks()-prepare_began;
    if(!cache_sync(s->commands.pixels,n*4,1) ||
       !cache_sync(s->state.pixels,LMI_BLIT_STATE_BYTES,1) ||
       !cache_sync(s->state.pixels,LMI_BLIT_STATE_BYTES,0))goto leave;
    lmi_desktop_to_memory(0,0);
    uint64_t began=lmi_frame_ticks();
    uint32_t submitted=lmi_desktop_submit(&s->commands.address,&n,1);
    if(!submitted || d->failed)uncertain(s,d);
    s->pending.backend=d;s->pending.target=f->target;s->pending.began=began;
    s->pending.prepare_ticks=prepare_ticks;s->pending.index=index;
    s->pending.pitch=f->source_pitch;s->pending.bytes=f->bytes;s->pending.reused=reused;
    s->pending.fence=submitted;s->queued++;ok=1;
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
        finish(s); /* A second/native draw must never race a queued blit. */
        int n=eligible(s,self,surface);
        if(n>=0 && !s->written && copy(s,(unsigned)n,surface))return;
        cpu_access(s);dirty(s);s->credit=0;s->fallback++;
    }
    lmi_fast_draw(self,surface,src,dst); /* CPU counters remain CPU copies only. */
}
int lmi_gpu_frame_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *swap,void **surfaces,unsigned *index,uint64_t *ticket)
{
    struct lmi_gpu_frame_stats *s=statistics();
    if(s) {
        finish(s); /* Never discard a pending source/command dependency. */
        if(s->clean_owner!=p) {cpu_access(s);dirty(s);s->clean_owner=p;}
        if(s->gpu_owned_mask && !full_frame(s,c,p,swap,surfaces,index,ticket))cpu_access(s);
        s->credit=0;s->written=0;s->completed_target=0;s->pipeline=p;
    }
    int result=lmi_preclean_frame(c,p,swap,surfaces,index,ticket);
    if(s)finish(s); /* Failed/no-clean frames still join before source drop. */
    if(s && result==1 && s->written)s->frames++;
    if(s) {
        if(result!=1 || !s->written) {cpu_access(s);dirty(s);}
        /* No early clean credit: ordinary submit may CPU-clean this target. */
        else if(s->credit)cpu_access(s);
        s->credit=0;
    }
    return result;
}
/* Only the early native-clean BL is replaced. The v65 READY/ticket/descriptor
 * checks still run, and its existing one-use DPU credit remains unchanged.
 */
int lmi_gpu_frame_clean(void *context,const struct lmi_frame_buffer *b)
{
    struct lmi_gpu_frame_stats *s=statistics();
    if(s)finish(s); /* READY is not permission to display unfinished GPU DMA. */
    int credit=s && s->credit;
    if(s)s->credit=0;
    if(credit && b && context==s->pre.context && b->pixels==s->completed_target &&
       b==&s->pre.buffer && lmi_frame_preclean_ready(&s->pre)) {
        __atomic_thread_fence(__ATOMIC_RELEASE);s->skipped_clean++;return 1;
    }
    if(s)cpu_access(s);
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
        lmi_frame_emit("LMI_GPU_TARGET_CACHE",&s->target_prepared,5);
        lmi_frame_emit("LMI_GPU_COPY_OVERLAP",&s->queued,6);
        const uint64_t pending=s->pending.fence;
        lmi_frame_emit("LMI_GPU_COPY_PENDING",&pending,1);
        lmi_frame_emit("LMI_GPU_CPU_TRANSFER",&s->post_deferred,4);
        const uint64_t owned=s->gpu_owned_mask;
        lmi_frame_emit("LMI_GPU_CPU_OWNED",&owned,1);
    }
}
