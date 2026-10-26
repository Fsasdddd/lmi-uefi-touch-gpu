/* Hardware adapter for the measured lmi display path. The native entry point
 * supplies wired owned memory, short IRQ-masked transactions and MMIO access.
 * No clocks, streams, CBAR/CBA2R, panel or global SMMU registers are written.
 */
#ifndef LMI_DISPLAY_DMA_H
#define LMI_DISPLAY_DMA_H
#include "lmi-display-pipeline.h"
struct lmi_dma_services {
    void *opaque;
    uint32_t (*read)(void *,unsigned space,uint32_t offset);
    void (*write)(void *,unsigned space,uint32_t offset,uint32_t value);
    int (*enter)(void *,uint64_t *flags);
    void (*leave)(void *,uint64_t flags);
    /* Return exclusive, wired, writable RAM, disjoint from the caller/context.
     * It must remain wired until restore has returned 1. No allocator reuse. */
    uintptr_t (*allocate)(void *,size_t,size_t);
    uint64_t (*physical)(void *,uintptr_t);
    void (*clean)(void *,uintptr_t,size_t);
    /* Monotonic 19.2 MHz counter; pause may not hold the enter/leave gate. */
    uint64_t (*ticks)(void *);
    void (*pause)(void *,unsigned us);
};
#define LMI_DMA_TABLE_BYTES (32u*4096u)
#define LMI_DMA_BUFFER_BYTES ((4544u*2436u+16383u)&~16383u)
struct lmi_display_dma {
    struct lmi_dma_services io;
    struct lmi_frame_buffer buffer[2];
    uintptr_t tables;
    uint64_t physical[32];
    uint64_t owned_pages[8192]; /* reject physical aliases, including table pages */
    unsigned pages;
    uint32_t cb_saved[9],scale_saved[25];
    uint32_t saved_source,saved_flush,saved_sync,saved_auto,saved_misr;
    uint32_t baseline,first,current_source;
    int journal,manual,mapped,mapping_ready,source_owned,misr_owned,scaled,pending;
    int allocated,baseline_valid,prepared,restoring,restored;
};
LMI_PIPE_CODE int lmi_dma_prepare(struct lmi_display_dma *);
LMI_PIPE_CODE int lmi_dma_set_scaling(struct lmi_display_dma *,int enabled);
LMI_PIPE_CODE int lmi_dma_validate(void *,const struct lmi_frame_buffer[2]);
LMI_PIPE_CODE int lmi_dma_clean(void *,const struct lmi_frame_buffer *);
LMI_PIPE_CODE int lmi_dma_start(void *,const struct lmi_frame_buffer *,uint32_t *);
LMI_PIPE_CODE int lmi_dma_sample(void *,struct lmi_display_completion *);
LMI_PIPE_CODE int lmi_dma_restore(void *);
LMI_PIPE_CODE uint32_t lmi_dma_signature(struct lmi_display_dma *);
#endif
