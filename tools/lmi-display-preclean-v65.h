/* The existing journal is the exact prefix; native fence/copy code is intact. */
#ifndef LMI_DISPLAY_PRECLEAN_V65_H
#define LMI_DISPLAY_PRECLEAN_V65_H
#include "lmi-display-fast-v62.h"
#include "lmi-display-dma.h"
struct lmi_preclean_stats {
    struct lmi_fast_stats original;
    struct lmi_display_pipeline *owner;
    void *context;
    struct lmi_frame_buffer buffer;
    uint64_t ticket;
    unsigned index,armed;
    uint64_t prepared,pending,consumed,fallback,failed,clean_ticks;
};
void *lmi_preclean_allocate(size_t,size_t);
int lmi_preclean_frame(struct lmi_compositor *,struct lmi_display_pipeline *,
    const unsigned char *,void **,unsigned *,uint64_t *);
int lmi_preclean_clean(void *,const struct lmi_frame_buffer *);
void lmi_preclean_cleanup(void);
#endif
