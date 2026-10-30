/* One presenter, append-only extension of the frozen v73 timing journal. */
#ifndef LMI_DISPLAY_WAIT_V74_H
#define LMI_DISPLAY_WAIT_V74_H
#include "lmi-display-timing-v73.h"
#define LMI_WAIT_STEP_TICKS 960ull       /* 50 us at the verified 19.2 MHz */
#define LMI_WAIT_BUDGET_TICKS 160000ull  /* <= 1/120 s from frame return */
struct lmi_wait_stats {
    struct lmi_timing_stats original;
    uint64_t calls,spun,yielded,spin_ticks,yield_ticks,yield_max,other;
};
void *lmi_wait_allocate(size_t,size_t);
void lmi_wait_delay(unsigned);
void lmi_wait_cleanup(void);
#endif
