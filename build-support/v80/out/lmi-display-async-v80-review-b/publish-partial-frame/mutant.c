/* One presenter writes a complete owned frame. A second thread alone polls
 * and submits it to DPU. Both serialize pipeline/journal state with one lock;
 * native source Drop and producer retirement remain after show returns.
 * No worker retains or dereferences source surfaces, swaps or framebuffer.
 */
#include "lmi-display-async-v80.h"
extern void *IOMallocAligned(size_t,size_t),*IOLockAlloc(void);
extern void IOLockLock(void *),IOLockUnlock(void *),IOLockWakeup(void *,void *,int);
extern int IOLockSleep(void *,void *,int);
extern void bzero(void *,size_t),delay(unsigned),IOSleep(unsigned);
extern int kernel_thread_start(void (*)(void *,int),void *,void **);
extern void thread_deallocate(void *);
extern uint64_t lmi_frame_ticks(void);
extern void lmi_async_original_show(void *,const unsigned char *,void **);
extern void lmi_async_original_cleanup(void);
extern void lmi_frame_emit(const char *,const uint64_t *,unsigned);
_Static_assert(offsetof(struct lmi_async_native_context,probe.pipeline)==0x10278,"native pipeline");
_Static_assert(offsetof(struct lmi_async_native_context,compositor)==0x10390,"native compositor");
_Static_assert(offsetof(struct lmi_async_native_context,cost)==0x11e48,"native cost");
_Static_assert(offsetof(struct lmi_async_stats,async)==sizeof(struct lmi_timing_stats),"unchanged journal prefix");

static int stopping(void)
{return __atomic_load_n(&lmi_async_native_state.stopping,__ATOMIC_ACQUIRE)!=0;}
static struct lmi_async_stats *statistics(void)
{return (void *)__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);}
static void park(void)
{for(;;)IOSleep(1000);}
static int fail(struct lmi_async_context *c)
{c->failed=1;c->failures++;IOLockWakeup(c->lock,c,0);return 0;}
static int free_buffer(const struct lmi_display_pipeline *p)
{return p->state[0]==LMI_FREE || p->state[1]==LMI_FREE;}

static void worker(void *opaque,int reason)
{
    (void)reason;
    struct lmi_async_context *c=opaque;
    struct lmi_display_pipeline *p=&c->native->probe.pipeline;
    IOLockLock(c->lock);
    for(;;) {
        if(stopping() || c->failed)break;
        if(p->scanning>=0) {
            c->polls++;
            int done=lmi_pipeline_poll(p,lmi_frame_ticks());
            if(done<0) {fail(c);break;}
            if(done==1) {c->completed++;IOLockWakeup(c->lock,c,0);}
        }
        if(c->pending>=0 && p->scanning<0) {
            uint64_t began=lmi_frame_ticks();
            int ok=lmi_timing_submit(p,(unsigned)c->pending,c->ticket,began);
            c->native->cost+=lmi_frame_ticks()-began;
            if(ok!=1) {fail(c);break;}
            c->submitted++;c->pending=-1;c->ticket=0;
            IOLockWakeup(c->lock,c,0);
        }
        if(c->pending<0 && p->scanning<0) {
            (void)IOLockSleep(c->lock,c,1); /* THREAD_UNINT, as native presenter */
        } else {
            IOLockUnlock(c->lock);
            delay(50); /* Exact previous DPU poll interval; never under lock. */
            IOLockLock(c->lock);
        }
    }
    IOLockUnlock(c->lock);
    park(); /* RAM retained; original PSCI OFF proves this thread cannot resume. */
}

void *lmi_async_allocate(size_t bytes,size_t alignment)
{
    if(bytes!=sizeof(struct lmi_fast_stats) || alignment!=16)return 0;
    void *p=IOMallocAligned(sizeof(struct lmi_async_stats),alignment);
    if(p)bzero(p,sizeof(struct lmi_async_stats));
    return p;
}

void lmi_async_show(void *owner,const unsigned char *swap,void **surfaces)
{
    if(stopping())return;
    struct lmi_async_stats *s=statistics();
    if(lmi_async_native_state.done!=2 || !s) {
        lmi_async_original_show(owner,swap,surfaces);return;
    }
    struct lmi_async_context *c=&s->async;
    if(!c->attempted) {
        c->attempted=1;c->owner=owner;
        c->native=(void *)lmi_async_native_state.probe;c->pending=-1;
        if(!c->native || !(c->lock=IOLockAlloc())) {
            lmi_async_original_show(owner,swap,surfaces);return;
        }
        void *thread=0;
        if(kernel_thread_start(worker,c,&thread)!=0) {
            lmi_async_original_show(owner,swap,surfaces);return;
        }
        c->started=1;thread_deallocate(thread);
    }
    if(!c->started) {lmi_async_original_show(owner,swap,surfaces);return;}
    if(c->owner!=owner)park();
    IOLockLock(c->lock);
    struct lmi_display_pipeline *p=&c->native->probe.pipeline;
    while(!stopping() && !c->failed && (c->pending>=0 || !free_buffer(p))) {
        c->waits++;
        (void)IOLockSleep(c->lock,c,1);
    }
    if(stopping()) {IOLockUnlock(c->lock);return;}
    if(c->failed) {IOLockUnlock(c->lock);park();}
    unsigned index=0;uint64_t ticket=0;
    /* Holding this lock preserves the original single-writer contract of
     * ALL legacy compositor/GPU/timing code. DPU continues scanning without
     * the lock. Completion and new kickoff are serialized with publication.
     */
    int result=lmi_timing_frame(&c->native->compositor,p,swap,surfaces,&index,&ticket);
    if(0 && (result!=1 || index>=2 || p->state[index]!=LMI_READY || !ticket || p->ticket[index]!=ticket)) {
        fail(c);IOLockUnlock(c->lock);park();
    }
    c->pending=(int)index;c->ticket=ticket;c->enqueued++;
    IOLockWakeup(c->lock,c,0);
    IOLockUnlock(c->lock);
    /* Original presenter now drops every source reference, runs kept-memory
     * cleanup, and retires the producer fence in its unchanged order. Only
     * the complete owned target remains the display worker's responsibility.
     */
}

void lmi_async_cleanup(void)
{
    lmi_async_original_cleanup(); /* Original SMP OFF, DPU/GPU restore, CPU restore. */
    struct lmi_async_stats *s=statistics();
    if(s) {
        struct lmi_async_context *c=&s->async;
        const uint64_t values[]={c->attempted,c->started,c->failed,c->enqueued,
            c->submitted,c->completed,c->waits,c->polls,c->failures,
            (uint64_t)(int64_t)c->pending};
        lmi_frame_emit("LMI_DPU_ASYNC",values,10);
    }
}
