/* The v65 journal remains an exact prefix. Only the presenter writes here. */
#ifndef LMI_GPU_FRAME_V67_H
#define LMI_GPU_FRAME_V67_H
#include "lmi-display-preclean-v65.h"
#define LMI_GPU_FRAME_SOURCES 8u
struct lmi_frame_mapping {
    uintptr_t pixels;
    uint64_t address;
    uint32_t span;
    void *surface;
};
struct lmi_gpu_frame_stats {
    struct lmi_preclean_stats pre;
    struct lmi_display_pipeline *pipeline;
    struct lmi_frame_mapping target[2],source[LMI_GPU_FRAME_SOURCES],commands;
    unsigned victim,written,credit;
    uintptr_t completed_target;
    uint64_t draws,frames,bytes,linear,strided,map_hits,map_new,evicted;
    uint64_t retained,released,fallback,skipped_clean,copy_ticks,held;
};
void *lmi_gpu_frame_allocate(size_t,size_t);
int lmi_gpu_frame_frame(struct lmi_compositor *,struct lmi_display_pipeline *,
    const unsigned char *,void **,unsigned *,uint64_t *);
void lmi_gpu_frame_draw(void *,void *,const int32_t *,const int32_t *);
int lmi_gpu_frame_clean(void *,const struct lmi_frame_buffer *);
void lmi_gpu_frame_cleanup(void);
#endif
