/* Replace only native desktop_show's delay(50). Polling, DPU completion,
 * source retirement, GPU joins and the original timeout remain untouched.
 * Short waits avoid a scheduler round trip; after a bounded wall-clock
 * window the original yielding delay runs. Interrupts/preemption stay as-is.
 */
#include "lmi-display-wait-v74.h"
extern void *IOMallocAligned(size_t,size_t);
extern void bzero(void *,size_t);
extern uint64_t lmi_frame_ticks(void);
extern void lmi_frame_emit(const char *,const uint64_t *,unsigned);
extern void lmi_wait_original_delay(unsigned);
_Static_assert(offsetof(struct lmi_wait_stats,calls)==sizeof(struct lmi_timing_stats),"frozen timing prefix");
_Static_assert(offsetof(struct lmi_wait_stats,other)-offsetof(struct lmi_wait_stats,calls)==6*8,"seven counters");
static struct lmi_wait_stats *statistics(void)
{return (void *)__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);}
void *lmi_wait_allocate(size_t bytes,size_t alignment)
{
    if(bytes!=sizeof(struct lmi_fast_stats) || alignment!=16)return 0;
    void *p=IOMallocAligned(sizeof(struct lmi_wait_stats),alignment);
    if(p)bzero(p,sizeof(struct lmi_wait_stats));
    return p;
}
void lmi_wait_delay(unsigned us)
{
    struct lmi_wait_stats *s=statistics();
    if(!s) {lmi_wait_original_delay(1);return;}
    uint64_t began=lmi_frame_ticks();s->calls++;
    /* Unsigned subtraction also rejects a future/invalid frame timestamp.
     * Budget is elapsed wall time, including preemption and MMIO sampling;
     * it cannot restart on each delay or extend the native DPU timeout. */
    if(us==50 && s->original.armed && s->original.owner &&
       began-s->original.ended<=LMI_WAIT_BUDGET_TICKS-LMI_WAIT_STEP_TICKS) {
        s->spun++;
        while(lmi_frame_ticks()-began<LMI_WAIT_STEP_TICKS) {}
        s->spin_ticks+=lmi_frame_ticks()-began;
    } else {
        if(us!=50 || !s->original.armed || !s->original.owner)s->other++;
        s->yielded++;
        lmi_wait_original_delay(1);
        uint64_t elapsed=lmi_frame_ticks()-began;
        s->yield_ticks+=elapsed;
        if(elapsed>s->yield_max)s->yield_max=elapsed;
    }
}
void lmi_wait_cleanup(void)
{
    lmi_timing_cleanup(); /* Original verified SMP stop and display restore. */
    struct lmi_wait_stats *s=statistics();
    if(s)lmi_frame_emit("LMI_DPU_SHORT_WAIT",&s->calls,7);
}
