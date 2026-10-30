/* Append-only, single-presenter timing. The v71 journal remains byte-exact. */
#ifndef LMI_DISPLAY_TIMING_V73_H
#define LMI_DISPLAY_TIMING_V73_H
#include "lmi-gpu-deferred-cache-v71.h"
enum lmi_timing_kind {
    LMI_TIME_FRAME, LMI_TIME_GAP, LMI_TIME_SOURCE, LMI_TIME_COPY,
    LMI_TIME_DPU_WAIT, LMI_TIME_SUBMIT, LMI_TIME_TOTAL, LMI_TIME_CADENCE,
    LMI_TIME_KINDS
};
/* Six bins: <=1ms, <=4ms, <=1/120s, <=1/60s, <=1/30s, longer.
 * count/sum/max and all six bins fit one frozen formatter record. */
struct lmi_timing_metric {uint64_t count,sum,max,bin[6];};
struct lmi_timing_stats {
    struct lmi_gpu_frame_stats original;
    struct lmi_timing_metric metric[LMI_TIME_KINDS];
    struct lmi_display_pipeline *owner;
    uint64_t began,ended,ticket,last_submit;
    unsigned index,armed,have_last;
    uint64_t frame_ok,frame_other,submit_ok,submit_other,matched,unmatched;
};
void *lmi_timing_allocate(size_t,size_t);
int lmi_timing_frame(struct lmi_compositor *,struct lmi_display_pipeline *,
    const unsigned char *,void **,unsigned *,uint64_t *);
int lmi_timing_submit(struct lmi_display_pipeline *,unsigned,uint64_t,uint64_t);
_Bool lmi_timing_source(void *,uint64_t);
void lmi_timing_cleanup(void);
#endif
