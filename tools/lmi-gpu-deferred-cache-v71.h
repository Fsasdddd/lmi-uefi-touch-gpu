/* The v65 journal remains an exact prefix. Only the presenter writes here. */
#ifndef LMI_GPU_DEFERRED_CACHE_V71_H
#define LMI_GPU_DEFERRED_CACHE_V71_H
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
    struct lmi_frame_mapping target[2],source[LMI_GPU_FRAME_SOURCES],commands,state;
    unsigned victim,written,credit;
    uintptr_t completed_target;
    uint64_t draws,frames,bytes,linear,strided,map_hits,map_new,evicted;
    uint64_t retained,released,fallback,skipped_clean,copy_ticks,held;
    /* Private targets have one CPU presenter. A successful post-invalidate
     * leaves no dirty target lines. Ordinary/failed frames revoke both bits. */
    struct lmi_display_pipeline *clean_owner;
    unsigned clean_mask;
    uint64_t target_prepared,target_reused,dirty_resets,target_bytes_saved,target_prepare_ticks;
    struct {
        struct lmi_v66_desk *backend;
        uintptr_t target;
        uint64_t began,prepare_ticks;
        uint32_t fence,index,pitch,bytes,reused;
    } pending;
    uint64_t queued,finished,wait_polls,busy_polls,later_queued,unlocked_ticks;
    unsigned gpu_owned_mask;
    uint64_t post_deferred,cpu_sync_targets,cpu_sync_bytes,cpu_sync_ticks;
};
void *lmi_gpu_frame_allocate(size_t,size_t);
int lmi_gpu_frame_frame(struct lmi_compositor *,struct lmi_display_pipeline *,
    const unsigned char *,void **,unsigned *,uint64_t *);
void lmi_gpu_frame_draw(void *,void *,const int32_t *,const int32_t *);
int lmi_gpu_frame_clean(void *,const struct lmi_frame_buffer *);
void lmi_gpu_frame_cleanup(void);
#endif
