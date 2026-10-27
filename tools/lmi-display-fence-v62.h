/* Producer retirement remains pending through source drop/kept cleanup.
 * The native framebuffer queue lock protects every field in this journal. */
#ifndef LMI_DISPLAY_FENCE_V62_H
#define LMI_DISPLAY_FENCE_V62_H
#include <stdint.h>
struct lmi_swap_fence {
    uint64_t began,retired,waits,sleeps,timeouts,busy,closed,bad,held,wakes;
    void *owner;
    uint64_t generation;
    uint32_t id,reading;
};
void lmi_fence_show(void *,const unsigned char *,void **);
void lmi_fence_finish(void *);
uint32_t lmi_fence_method(void *,uint32_t,void *,void *,void *,void *);
uint32_t lmi_fence_close(void *);
#endif
