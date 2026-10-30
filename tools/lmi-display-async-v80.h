/* The compositor/GPU/timing journals retain their exact compiled prefixes. */
#ifndef LMI_DISPLAY_ASYNC_V80_H
#define LMI_DISPLAY_ASYNC_V80_H
#include "lmi-display-probe.h"
#include "lmi-display-timing-v73.h"
struct lmi_async_native_state {
    struct lmi_display_probe *probe;
    unsigned stopping,restoring,attempted,done;
};
struct lmi_async_native_context {
    struct lmi_display_probe probe;
    volatile uint32_t *map[2];
    struct lmi_compositor compositor;
    uint64_t began,cost;
    char trace[64][128];
    unsigned trace_count;
};
struct lmi_async_context {
    void *lock,*owner;
    struct lmi_async_native_context *native;
    uint64_t ticket;
    int pending;
    unsigned attempted,started,failed;
    uint64_t enqueued,submitted,completed,waits,polls,failures;
};
struct lmi_async_stats {
    struct lmi_timing_stats prior;
    struct lmi_async_context async;
};
extern volatile struct lmi_async_native_state lmi_async_native_state;
void *lmi_async_allocate(size_t,size_t);
void lmi_async_show(void *,const unsigned char *,void **);
void lmi_async_cleanup(void);
#endif
