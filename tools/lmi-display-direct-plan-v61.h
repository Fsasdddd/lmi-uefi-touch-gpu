/* CPU-copy eligibility only. A presenter must retain the surface and wait
 * for its GPU fence before reading. No source is mapped for DPU here. */
#ifndef LMI_DISPLAY_DIRECT_PLAN_V61_H
#define LMI_DISPLAY_DIRECT_PLAN_V61_H
#include <stdint.h>
#include <stddef.h>
struct lmi_direct_surface_view {
    uintptr_t allocation;
    uint32_t sid,allocation_bytes,offset,width,height,pitch,format,planes;
    uint16_t element_bytes;
    unsigned client_backed;
};
struct lmi_direct_plan {
    uintptr_t pixels;
    uint32_t sid,pitch,bytes;
};
int lmi_direct_plan(const unsigned char *,size_t,const struct lmi_direct_surface_view[4],struct lmi_direct_plan *);
#endif
