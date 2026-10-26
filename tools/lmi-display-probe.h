#ifndef LMI_DISPLAY_PROBE_H
#define LMI_DISPLAY_PROBE_H
#include "lmi-display-dma.h"
struct lmi_display_probe {
    struct lmi_display_dma dma;
    struct lmi_display_pipeline pipeline;
    void *opaque;
    int (*stopping)(void *);
    void (*report)(void *,unsigned stage,int ok,uint32_t expected,uint32_t actual,uint64_t ticks);
    uint32_t reference[2];
    unsigned stage,frames;
    int verified,restore_ok,keep_active;
};
/* Single caller; no other producer may access this owner. Normal cleanup runs
 * after its only writer has returned. Timer cleanup needs native SMP stop. */
LMI_PIPE_CODE int lmi_display_probe_run(struct lmi_display_probe *);
LMI_PIPE_CODE int lmi_display_probe_pattern(struct lmi_display_probe *,unsigned buffer,int scaled,unsigned seed);
#endif
