/* Measure missing outer DPU wait and producer gaps without changing any
 * ownership transition, fence, delay, queue depth or display register.
 * The native framebuffer lock serializes this one presenter. Cleanup first
 * uses the original verified SMP stop; no locks or frees follow that stop.
 */
#include "lmi-display-timing-v73.h"
extern void *IOMallocAligned(size_t,size_t);
extern void bzero(void *,size_t);
extern uint64_t lmi_frame_ticks(void);
extern void lmi_frame_emit(const char *,const uint64_t *,unsigned);
extern _Bool lmi_timing_original_source(void *,uint64_t);
extern int lmi_timing_original_submit(struct lmi_display_pipeline *,unsigned,uint64_t,uint64_t);
_Static_assert(offsetof(struct lmi_timing_stats,metric)==sizeof(struct lmi_gpu_frame_stats),"frozen GPU prefix");
_Static_assert(sizeof(struct lmi_timing_metric)==9*8,"nine formatter arguments");
_Static_assert(offsetof(struct lmi_timing_stats,unmatched)-offsetof(struct lmi_timing_stats,frame_ok)==5*8,"six counters");
static struct lmi_timing_stats *statistics(void)
{return (void *)__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);}
static __attribute__((noinline)) void sample(struct lmi_timing_metric *m,uint64_t ticks)
{
    unsigned n=ticks<=19200?0:ticks<=76800?1:ticks<=160000?2:
        ticks<=320000?3:ticks<=640000?4:5;
    m->count++;m->sum+=ticks;if(ticks>m->max)m->max=ticks;m->bin[n]++;
}
void *lmi_timing_allocate(size_t bytes,size_t alignment)
{
    if(bytes!=sizeof(struct lmi_fast_stats) || alignment!=16)return 0;
    void *p=IOMallocAligned(sizeof(struct lmi_timing_stats),alignment);
    if(p)bzero(p,sizeof(struct lmi_timing_stats));
    return p;
}
int lmi_timing_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *swap,void **surfaces,unsigned *index,uint64_t *ticket)
{
    uint64_t began=lmi_frame_ticks();
    struct lmi_timing_stats *s=statistics();
    uint64_t copy_before=s?s->original.copy_ticks:0;
    if(s) {
        if(s->have_last)sample(&s->metric[LMI_TIME_GAP],began-s->last_submit);
        s->armed=0;
    }
    int result=lmi_gpu_frame_frame(c,p,swap,surfaces,index,ticket);
    uint64_t ended=lmi_frame_ticks();
    s=statistics(); /* The original first frame may allocate the journal. */
    if(s) {
        sample(&s->metric[LMI_TIME_FRAME],ended-began);
        if(s->original.copy_ticks!=copy_before)
            sample(&s->metric[LMI_TIME_COPY],s->original.copy_ticks-copy_before);
        if(result==1 && p && index && ticket && *index<2 && *ticket) {
            s->frame_ok++;s->began=began;s->ended=ended;s->owner=p;
            s->index=*index;s->ticket=*ticket;s->armed=1;
        } else s->frame_other++;
    }
    return result;
}
int lmi_timing_submit(struct lmi_display_pipeline *p,unsigned index,uint64_t ticket,uint64_t now)
{
    uint64_t began=lmi_frame_ticks();
    struct lmi_timing_stats *s=statistics();
    int matched=s && s->armed && s->owner==p && s->index==index && s->ticket==ticket;
    if(s) {
        if(matched) {s->matched++;sample(&s->metric[LMI_TIME_DPU_WAIT],began-s->ended);}
        else s->unmatched++;
        s->armed=0;
    }
    /* Preserve the caller's original timestamp; instrumentation must not
     * alter timeout accounting or turn a refused submission into success. */
    int result=lmi_timing_original_submit(p,index,ticket,now);
    uint64_t ended=lmi_frame_ticks();
    if(s) {
        sample(&s->metric[LMI_TIME_SUBMIT],ended-began);
        if(matched)sample(&s->metric[LMI_TIME_TOTAL],ended-s->began);
        if(result==1) {
            s->submit_ok++;
            if(s->have_last)sample(&s->metric[LMI_TIME_CADENCE],ended-s->last_submit);
            s->last_submit=ended;s->have_last=1;
        } else s->submit_other++;
    }
    return result;
}
_Bool lmi_timing_source(void *surface,uint64_t milliseconds)
{
    uint64_t began=lmi_frame_ticks();
    _Bool result=lmi_timing_original_source(surface,milliseconds);
    uint64_t ended=lmi_frame_ticks();
    struct lmi_timing_stats *s=statistics();
    if(s)sample(&s->metric[LMI_TIME_SOURCE],ended-began);
    return result;
}
void lmi_timing_cleanup(void)
{
    lmi_gpu_frame_cleanup(); /* Original verified stop, restore and counters. */
    struct lmi_timing_stats *s=statistics();
    if(!s)return;
    lmi_frame_emit("LMI_TIME_FRAME",&s->metric[LMI_TIME_FRAME].count,9);
    lmi_frame_emit("LMI_TIME_GAP",&s->metric[LMI_TIME_GAP].count,9);
    lmi_frame_emit("LMI_TIME_SOURCE",&s->metric[LMI_TIME_SOURCE].count,9);
    lmi_frame_emit("LMI_TIME_COPY",&s->metric[LMI_TIME_COPY].count,9);
    lmi_frame_emit("LMI_TIME_DPU_WAIT",&s->metric[LMI_TIME_DPU_WAIT].count,9);
    lmi_frame_emit("LMI_TIME_SUBMIT",&s->metric[LMI_TIME_SUBMIT].count,9);
    lmi_frame_emit("LMI_TIME_TOTAL",&s->metric[LMI_TIME_TOTAL].count,9);
    lmi_frame_emit("LMI_TIME_CADENCE",&s->metric[LMI_TIME_CADENCE].count,9);
    lmi_frame_emit("LMI_TIME_COUNTS",&s->frame_ok,6);
}
