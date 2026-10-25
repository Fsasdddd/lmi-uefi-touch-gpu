#ifndef LMI_GPU_RUNTIME_H
#define LMI_GPU_RUNTIME_H
/* Stack descriptor valid only during the RAM consumer call. The allocation
 * itself stays wired on active/uncertain outcomes until bounded reboot. */
struct lmi_gpu_live_backing {
    void *owner_context;
    unsigned long long cpu_address;
    unsigned int allocation_bytes;
};
#endif
