/* One-copy full-frame path. All DMA addresses and ownership stay unchanged. */
#ifndef LMI_DISPLAY_FAST_V62_H
#define LMI_DISPLAY_FAST_V62_H
#include "lmi-display-compositor.h"
#include "lmi-display-fence-v62.h"
#include "lmi-display-direct-plan-v61.h"
struct lmi_fast_stats {
    uint64_t frames,slow,copies;
    void *self,*surface;
    uintptr_t source,target;
    uint32_t bytes,source_pitch;
    int active;
    uint64_t reasons,metadata[10],strided;
    unsigned sampled;
    struct lmi_swap_fence fence;
};
extern struct lmi_fast_stats *lmi_fast_state;
int lmi_fast_original_fields(const struct lmi_compositor *);
int lmi_fast_original_frame(struct lmi_compositor *,struct lmi_display_pipeline *,const unsigned char *,void **,unsigned *,uint64_t *);
void lmi_fast_original_draw(void *,void *,const int32_t *,const int32_t *);
void lmi_fast_original_cleanup(void);
int lmi_fast_frame(struct lmi_compositor *,struct lmi_display_pipeline *,const unsigned char *,void **,unsigned *,uint64_t *);
void lmi_fast_draw(void *,void *,const int32_t *,const int32_t *);
void lmi_fast_cleanup(void);
#endif
