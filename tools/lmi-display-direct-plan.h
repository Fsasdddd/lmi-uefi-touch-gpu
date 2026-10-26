/* Eligibility only. No MMIO, mapping or reference ownership is granted here.
 * A native caller must hold the real surface, wait its GPU fence, wire/map
 * every page, and keep backing until verified DPU completion and TLB detach.
 * This module is not integrated into a runtime kernel. */
#ifndef LMI_DISPLAY_DIRECT_PLAN_H
#define LMI_DISPLAY_DIRECT_PLAN_H
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
