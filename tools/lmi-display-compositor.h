/* Bridge the frozen compositor to logical-sized owned frames. All row workers
 * must have joined before the original show callback returns. Single presenter. */
#ifndef LMI_DISPLAY_COMPOSITOR_H
#define LMI_DISPLAY_COMPOSITOR_H
#include "lmi-display-pipeline.h"
struct lmi_compositor_services {
    void *opaque;
    int (*ready)(void *,void *surface);
    int (*stopping)(void *);
    void (*show)(void *,void *self,const unsigned char *,void **);
};
struct lmi_compositor {
    void *self;
    uintptr_t original_base,original_column,original_weight;
    struct lmi_compositor_services io;
    uint32_t columns[1125];
    uint16_t weights[1125];
    int initialized,latest;
    uint64_t frames;
};
LMI_PIPE_CODE int lmi_compositor_init(struct lmi_compositor *,void *,const struct lmi_compositor_services *);
/* 1: consumed exactly once and published; 0: no swap consumed, safe fallback;
 * -1: consumed but incomplete/changed state, never invoke show on this swap again. */
LMI_PIPE_CODE int lmi_compositor_frame(struct lmi_compositor *,struct lmi_display_pipeline *,
    const unsigned char *,void **,unsigned *index,uint64_t *ticket);
#endif
