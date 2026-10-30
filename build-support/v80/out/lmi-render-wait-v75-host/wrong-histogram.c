/* Native gpuWait keeps its real fence, deadline and lock bracket. Its poll
 * interval is changed separately at the exact MOV instruction, 200 -> 50us.
 * This wrapper preserves both original delay arguments. Multiple GPU clients
 * can be sleeping concurrently while gGPULock is released, so every appended
 * metric uses atomics. No display pipeline field is changed here.
 */
#include "lmi-render-wait-v75.h"
extern void *IOMallocAligned(size_t,size_t);
extern void bzero(void *,size_t);
extern uint64_t lmi_frame_ticks(void);
extern void lmi_frame_emit(const char *,const uint64_t *,unsigned);
extern void lmi_render_original_delay(unsigned,unsigned);
_Static_assert(offsetof(struct lmi_render_stats,delay)==sizeof(struct lmi_timing_stats),"frozen timing prefix");
static struct lmi_render_stats *statistics(void)
{return (void *)__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);}
void *lmi_render_allocate(size_t bytes,size_t alignment)
{
    if(bytes!=sizeof(struct lmi_fast_stats) || alignment!=16)return 0;
    void *p=IOMallocAligned(sizeof(struct lmi_render_stats),alignment);
    if(p)bzero(p,sizeof(struct lmi_render_stats));
    return p;
}
void lmi_render_delay(unsigned interval,unsigned scale)
{
    uint64_t began=lmi_frame_ticks();
    lmi_render_original_delay(interval,scale);
    uint64_t elapsed=lmi_frame_ticks()-began;
    struct lmi_render_stats *s=statistics();
    if(!s)return;
    struct lmi_timing_metric *m=&s->delay;
    unsigned bin=elapsed<=19200?1:elapsed<=76800?1:elapsed<=160000?2:
        elapsed<=320000?3:elapsed<=640000?4:5;
    __atomic_fetch_add(&m->count,1,__ATOMIC_RELAXED);
    __atomic_fetch_add(&m->sum,elapsed,__ATOMIC_RELAXED);
    __atomic_fetch_add(&m->bin[bin],1,__ATOMIC_RELAXED);
    uint64_t maximum=__atomic_load_n(&m->max,__ATOMIC_RELAXED);
    while(maximum<elapsed && !__atomic_compare_exchange_n(&m->max,&maximum,elapsed,1,__ATOMIC_RELAXED,__ATOMIC_RELAXED)) {}
    if(interval!=50 || scale!=1000)__atomic_fetch_add(&s->other,1,__ATOMIC_RELAXED);
}
void lmi_render_cleanup(void)
{
    lmi_timing_cleanup(); /* Verified SMP stop before reading all writers. */
    struct lmi_render_stats *s=statistics();
    if(s) {
        lmi_frame_emit("LMI_RENDER_DELAY",&s->delay.count,9);
        lmi_frame_emit("LMI_RENDER_DELAY_OTHER",&s->other,1);
    }
}
