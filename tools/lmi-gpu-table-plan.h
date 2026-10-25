#ifndef LMI_GPU_TABLE_PLAN_H
#define LMI_GPU_TABLE_PLAN_H
#include "lmi-gpu-resources.h"
struct lmi_gpu_perf_table {arc_u32 hdr,gx_count,cx_count,gx[16][3],cx[4][2];};
int lmi_gpu_prepare_perf(const void *,arc_u32,struct lmi_gpu_perf_table *);
#endif
