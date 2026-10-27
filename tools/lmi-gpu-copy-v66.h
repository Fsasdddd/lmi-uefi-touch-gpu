/* Prefix/layout of the frozen v64 backend; this module allocates no state. */
#ifndef LMI_GPU_COPY_V66_H
#define LMI_GPU_COPY_V66_H
#include <stdint.h>
#include <stddef.h>
struct lmi_v66_desk {
    uint64_t pool;
    volatile uint32_t *gpu,*s,*g;
    uint32_t at,fence,done,failed,ready,mapping;
    uint64_t map_pages,map_batches,overlaps,queue_waits,barriers;
    uint32_t peak;
};
_Static_assert(sizeof(struct lmi_v66_desk)==104,"frozen backend allocation");
_Static_assert(offsetof(struct lmi_v66_desk,at)==32 &&
               offsetof(struct lmi_v66_desk,mapping)==52,"frozen ring state ABI");
int lmi_gpu_copy_start(void);
#endif
