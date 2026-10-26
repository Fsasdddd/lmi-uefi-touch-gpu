/* Two owned complete-frame buffers. No GOP tail, allocation, MMIO or locks here.
 * Caller serializes state transitions; CPU pixel writes may run outside that
 * lock while the other buffer is scanned. Never call start on a partial frame.
 * The hardware adapter must own/validate DMA mappings and journal restoration.
 */
#ifndef LMI_DISPLAY_PIPELINE_H
#define LMI_DISPLAY_PIPELINE_H
#include <stdint.h>
#include <stddef.h>
#ifdef LMI_PIPELINE_NATIVE
#define LMI_PIPE_CODE __attribute__((section("__TEXT_EXEC,__lmi_dpu"),noinline,used))
#define LMI_PIPE_LOCAL __attribute__((section("__TEXT_EXEC,__lmi_dpu")))
#else
#define LMI_PIPE_CODE
#define LMI_PIPE_LOCAL
#endif
enum lmi_buffer_state { LMI_FREE, LMI_WRITING, LMI_READY, LMI_SCANNING, LMI_HELD };
struct lmi_frame_buffer {
    uintptr_t pixels;
    uint64_t bytes;
    uint32_t iova, pitch, width, height;
};
struct lmi_display_completion {
    uint32_t status, frame, line, source, fault;
};
struct lmi_display_ops {
    /* Validate BOTH mappings, guards, cache attributes and exclusive ownership.
     * No hardware starts before this succeeds. Buffers stay owned until detach. */
    int (*validate)(void *,const struct lmi_frame_buffer[2]);
    int (*clean)(void *,const struct lmi_frame_buffer *);
    /* 1=armed and started, 0=no writes/no transfer, -1=uncertain. This operation
     * must clear stale DONE before sampling *first and then issue FLUSH/START.
     * It must inspect/read back the exact owned register set and fault state. */
    int (*start)(void *,const struct lmi_frame_buffer *,uint32_t *first);
    int (*sample)(void *,struct lmi_display_completion *);
    /* After all presenter CPUs are quiescent: bounded drain, restore original
     * source/geometry/manual state, flush, verify, then detach DMA mappings.
     * Return 1 only when BOTH buffers are provably no longer read by hardware. */
    int (*restore_detach)(void *);
};
struct lmi_display_pipeline {
    struct lmi_frame_buffer buffer[2];
    enum lmi_buffer_state state[2];
    uint64_t ticket[2],serial,submitted,completed,started_at,timeout;
    uint32_t first_frame,output_height,done_bit;
    int initialized,scanning,stopping,failed,detached;
    void *context;
    struct lmi_display_ops ops;
};
LMI_PIPE_CODE int lmi_pipeline_init(struct lmi_display_pipeline *,const struct lmi_frame_buffer[2],
    const struct lmi_display_ops *,void *,uint32_t,uint32_t,uint64_t);
LMI_PIPE_CODE int lmi_pipeline_acquire(struct lmi_display_pipeline *,uint64_t *ticket);
LMI_PIPE_CODE int lmi_pipeline_complete_frame(struct lmi_display_pipeline *,unsigned,uint64_t);
LMI_PIPE_CODE int lmi_pipeline_cancel_frame(struct lmi_display_pipeline *,unsigned,uint64_t);
LMI_PIPE_CODE int lmi_pipeline_submit(struct lmi_display_pipeline *,unsigned,uint64_t,uint64_t);
LMI_PIPE_CODE int lmi_pipeline_poll(struct lmi_display_pipeline *,uint64_t);
LMI_PIPE_CODE void lmi_pipeline_stop(struct lmi_display_pipeline *);
LMI_PIPE_CODE int lmi_pipeline_detach_after_cpu_stop(struct lmi_display_pipeline *);

/* A register PROGRAM, not MMIO. Candidate measured lmi QSEED 0x3000 bilinear BGRA parameters
 * require native/scaled spatial MISR comparison before desktop enablement.
 * Vendor sde_hw_util.c pins phase/size/preload layout and opmode masks.
 * This single-VIG plan pins the lmi v43 measured 0x3000 version and 5/3 preload; DT alone reported lite. */
struct lmi_scale_write {uint32_t offset,value;};
struct lmi_qseed_plan {struct lmi_scale_write write[32];unsigned count;};
LMI_PIPE_CODE int lmi_qseed_configure_plan(struct lmi_qseed_plan *,uint32_t version,uint32_t pitch);
#endif
