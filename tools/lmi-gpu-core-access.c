/* Mode39: source-backed, read-only census after retained GX OOB and CB1.
 * No clock/reset/CP writes. A successful census is not GPU execution proof. */
#include "lmi-gpu-boot-regs.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define ACCESS __attribute__((noinline,section(".gpu_cp")))
#define DATA __attribute__((section(".gpu_cp_data")))
extern u64 io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void log_line(const char *);
extern void log_hex(u64);
static const u32 cc_offsets[] DATA={0x100,0x104,0x138,0x1008,0x100c,0x1064,0x1068,0x106c,
    0x1078,0x1088,0x1098,0x109c,0x10a0,0x111c,0x1120,0x1124,0x1508,0x1540,0x5000};
static const u32 gpu_words[] DATA={0,1,0x16,0x17,0x18,0x43,0x45,0x46,0xae,
    0x210,0x213,0x215,0x842,0x8c1,0x8c2,0x8c3,0x98d,0xa00};
static const u32 gmu_offsets[] DATA={0x200,0x14340,0x143b0,0x24c40,0x24c44,0x24c48,
    0x24c4c,0x24c54,0x14648,0x24c14};
static int ACCESS quiet(volatile u32 *g) {
    return !(rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4)&0xc0) &&
        !rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4) &&
        !rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4) &&
        !(rsc_read(g+BOOT_GMU_AO_HOST_INTERRUPT_STATUS/4)&0x29);
}
int ACCESS lmi_gpu_core_access(volatile u32 *g) {
    if(!g || !quiet(g))return 0;
    volatile u32 *cc=(void *)io_map(0x3d90000,0x9000),*gpu=(void *)io_map(0x3d00000,0x40000);
    if(!cc || !gpu)return 0;
    log_line("LMI_GPU_CORE_ACCESS_CC\n");
    for(u32 n=0;n<19;n++)log_hex(((u64)(0x3d90000+cc_offsets[n])<<32)|rsc_read(cc+cc_offsets[n]/4));
    log_line("LMI_GPU_CORE_ACCESS_GPU\n");
    for(u32 n=0;n<18;n++)log_hex(((u64)(0x3d00000+4*gpu_words[n])<<32)|rsc_read(gpu+gpu_words[n]));
    log_line("LMI_GPU_CORE_ACCESS_GMU\n");
    for(u32 n=0;n<10;n++)log_hex(((u64)(0x3d6a000+gmu_offsets[n])<<32)|rsc_read(g+gmu_offsets[n]/4));
    if(!quiet(g))return 0;
    log_line("LMI_GPU_CORE_ACCESS_READONLY_HELD\n");return 1;
}
