#ifndef LMI_RENDER_WAIT_V75_H
#define LMI_RENDER_WAIT_V75_H
#include "lmi-display-timing-v73.h"
struct lmi_render_stats {
    struct lmi_timing_stats original;
    struct lmi_timing_metric delay;
    uint64_t other;
};
void *lmi_render_allocate(size_t,size_t);
void lmi_render_delay(unsigned,unsigned);
void lmi_render_cleanup(void);
#endif
