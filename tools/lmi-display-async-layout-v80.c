#include "lmi-display-async-v80.h"
const uint64_t lmi_async_layout[] = {
    sizeof(struct lmi_fast_stats),sizeof(struct lmi_async_stats),
    offsetof(struct lmi_async_stats,async),
    offsetof(struct lmi_async_context,lock),offsetof(struct lmi_async_context,owner),
    offsetof(struct lmi_async_context,native),offsetof(struct lmi_async_context,ticket),
    offsetof(struct lmi_async_context,pending),offsetof(struct lmi_async_context,attempted),
    offsetof(struct lmi_async_context,started),offsetof(struct lmi_async_context,failed),
    offsetof(struct lmi_async_context,enqueued),offsetof(struct lmi_async_context,submitted),
    offsetof(struct lmi_async_context,completed),offsetof(struct lmi_async_context,waits),
    offsetof(struct lmi_async_context,polls),offsetof(struct lmi_async_context,failures),
    offsetof(struct lmi_async_native_context,probe.pipeline),
    offsetof(struct lmi_async_native_context,compositor),
    offsetof(struct lmi_display_pipeline,state),offsetof(struct lmi_display_pipeline,ticket),
    offsetof(struct lmi_display_pipeline,scanning),
};
