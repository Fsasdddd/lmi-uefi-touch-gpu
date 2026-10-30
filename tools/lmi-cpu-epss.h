/* LMI EPSS only. Caller serializes preparation/apply; all other CPUs must be
 * stopped before restore. No DDR/RPMh, voltage, clock-parent or fuse writes. */
#ifndef LMI_CPU_EPSS_H
#define LMI_CPU_EPSS_H
#include <stddef.h>
#include <stdint.h>
#define LMI_EPSS_DOMAINS 3u
#define LMI_EPSS_ROWS 40u
#define LMI_EPSS_LUT 0x100u
#define LMI_EPSS_PERF 0x320u
#define LMI_EPSS_BASE 0x18591000u
#define LMI_EPSS_SIZE 0x1000u
struct lmi_epss_io {
    void *context;
    uintptr_t (*map)(void *,uint32_t,uint32_t);
    int (*read)(void *,uintptr_t,uint32_t,uint32_t *);
    int (*write)(void *,uintptr_t,uint32_t,uint32_t);
    void (*barrier)(void *);
};
struct lmi_epss_domain {
    uintptr_t base;
    uint32_t lut[LMI_EPSS_ROWS], rows, original, target, khz;
    uint32_t applied_readback, restored_readback;
};
struct lmi_epss_state {
    struct lmi_epss_io io;
    struct lmi_epss_domain domain[LMI_EPSS_DOMAINS];
    uint32_t prepared, dirty, applied, changed, failed_domain;
};
/* Pure parser; max_cores is the DT parameter, not number of online CPUs.
 * Caps are requests in kHz, not measured clock speeds. No boost rows. */
int lmi_epss_select(struct lmi_epss_domain *,uint32_t max_cores,uint32_t cap_khz);
int lmi_epss_prepare(struct lmi_epss_state *,const struct lmi_epss_io *);
int lmi_epss_apply(struct lmi_epss_state *);
int lmi_epss_restore(struct lmi_epss_state *);
#endif
