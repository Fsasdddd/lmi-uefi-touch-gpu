/* Move PoC maintenance into the interval during which the OTHER owned frame
 * may still be scanning. READY means all compositor/row writers have joined.
 * This is still CPU copying, not GPU blitting or direct source scanout.
 * One native presenter owns this journal and pipeline. Shutdown first stops
 * every other CPU, exactly as before; it does not call clean() concurrently.
 */
#include "lmi-display-preclean-v65.h"
_Static_assert(sizeof(struct lmi_fast_stats)==280,"frozen native journal allocation");
_Static_assert(offsetof(struct lmi_preclean_stats,owner)==280,"native journal prefix");
_Static_assert(offsetof(struct lmi_preclean_stats,clean_ticks)-offsetof(struct lmi_preclean_stats,prepared)==40,
               "six fixed-ABI statistics values");
extern void *IOMallocAligned(size_t,size_t);
extern void bzero(void *,size_t);
extern int lmi_preclean_original_clean(void *,const struct lmi_frame_buffer *);
extern void lmi_preclean_emit(const char *,const uint64_t *,unsigned);
#ifdef LMI_PRECLEAN_HOST
extern uint64_t lmi_preclean_ticks(void);
#else
static uint64_t lmi_preclean_ticks(void)
{uint64_t n;__asm__ volatile("isb\nmrs %0, cntvct_el0":"=r"(n)::"memory");return n;}
#endif
static struct lmi_preclean_stats *statistics(void)
{return (void *)__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);}
static int equal(const struct lmi_frame_buffer *a,const struct lmi_frame_buffer *b)
{
    return a->pixels==b->pixels && a->bytes==b->bytes && a->iova==b->iova &&
        a->pitch==b->pitch && a->width==b->width && a->height==b->height;
}
static int ready(const struct lmi_preclean_stats *s)
{
    const struct lmi_display_pipeline *p=s->owner;
    if(!p || !p->initialized || p->failed || p->stopping || p->detached || s->index>=2 ||
       p->context!=s->context || p->ops.clean!=lmi_preclean_clean ||
       p->state[s->index]!=LMI_READY || !s->ticket || p->ticket[s->index]!=s->ticket ||
       p->serial!=s->ticket || !equal(p->buffer+s->index,&s->buffer))return 0;
    /* Same identity/adapter readiness requirements as the frozen clean ABI.
     * This memory is the actual lmi DMA owner, never a client/GPU address. */
    const struct lmi_display_dma *d=s->context;
    return d && d->prepared && !d->restoring && !d->restored &&
        equal(d->buffer+s->index,&s->buffer) && s->buffer.bytes==LMI_DMA_BUFFER_BYTES &&
        s->buffer.pitch==4544 && s->buffer.width==1125 && s->buffer.height==2436;
}
void *lmi_preclean_allocate(size_t bytes,size_t alignment)
{
    /* The builder pins the sole journal allocation call, not the allocator.
     * Other allocations, every old field offset and the old bzero stay intact. */
    if(bytes!=sizeof(struct lmi_fast_stats) || alignment!=16)return 0;
    void *p=IOMallocAligned(sizeof(struct lmi_preclean_stats),alignment);
    if(p)bzero(p,sizeof(struct lmi_preclean_stats));
    return p;
}
int lmi_preclean_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *swap,void **surfaces,unsigned *index,uint64_t *ticket)
{
    struct lmi_preclean_stats *s=statistics();
    /* No clean credit survives a new composition, including failed/slow ones. */
    if(s)s->armed=0;
    int result=lmi_fast_frame(c,p,swap,surfaces,index,ticket);
    s=statistics();
    if(result!=1 || !s || !p || !index || !ticket || *index>=2 || !c ||
       c->io.stopping(c->io.opaque) ||
       (p->ops.clean!=lmi_preclean_original_clean && p->ops.clean!=lmi_preclean_clean))return result;
    s->owner=p;s->context=p->context;s->index=*index;s->ticket=*ticket;s->buffer=p->buffer[*index];
    p->ops.clean=lmi_preclean_clean;
    if(!ready(s))return result; /* Ordinary submit will still perform the real clean. */
    uint64_t began=lmi_preclean_ticks();
    int ok=lmi_preclean_original_clean(s->context,&s->buffer);
    s->clean_ticks+=lmi_preclean_ticks()-began;
    if(!ok) {s->failed++;return result;}
    s->prepared++;
    /* This counts a pending software scan, not proof of simultaneous bus DMA. */
    if(p->scanning>=0 && p->scanning!=(int)*index)s->pending++;
    if(ready(s) && !c->io.stopping(c->io.opaque))s->armed=1;
    return result;
}
int lmi_preclean_clean(void *context,const struct lmi_frame_buffer *buffer)
{
    struct lmi_preclean_stats *s=statistics();
    int credit=s && s->armed;
    if(s)s->armed=0; /* Single use even if validation or the following START fails. */
    if(credit && buffer && context==s->context && ready(s) && s->owner->scanning<0 &&
       equal(buffer,&s->buffer)) {
        __atomic_thread_fence(__ATOMIC_RELEASE);s->consumed++;return 1;
    }
    if(s)s->fallback++;
    return lmi_preclean_original_clean(context,buffer);
}
void lmi_preclean_cleanup(void)
{
    lmi_fast_cleanup(); /* Includes original verified SMP stop and DPU restore. */
    struct lmi_preclean_stats *s=statistics();
    if(s)lmi_preclean_emit("LMI_DPU_PRECLEAN",&s->prepared,6);
}
