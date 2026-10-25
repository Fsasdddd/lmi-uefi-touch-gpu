/* Mode34 read-only GX/CP and candidate CB1 census. No CP or SMMU writes. */
#include "lmi-gpu-boot-regs.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define PLAN __attribute__((noinline,section(".gpu_cp_plan")))
#define DATA __attribute__((section(".gpu_cp_plan_data")))
extern u64 io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void log_line(const char *);
extern void log_hex(u64);
static const u32 cp[] DATA={0x210,0x213,0x201,0x800,0x801,0x802,0x804,0x805,0x806,0x807,0x808,0x821,0x823,0x824,0x825,0x830,0x831};
static const u32 cb[] DATA={0x1804,0x1004,0x9000,0x9010,0x9030,0x9020,0x9024,0x9028,0x902c,0x9038,0x903c,0x9058,0x48};
int PLAN lmi_gpu_cp_plan(volatile u32 *g) {
    volatile u32 *s=(void *)io_map(0x3da0000,0x10000),*gpu=(void *)io_map(0x3d00000,0x40000);
    if(!s || !gpu || rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4)&0xc0 ||
       rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4) || rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4) ||
       rsc_read(s+0x20/4)!=0x4c017e06 || rsc_read(s+0x24/4)!=0x20000005 ||
       rsc_read(s+0x800/4)!=0x84000005)return 0;
    log_line("LMI_GPU_CP_PLAN_REGISTERS\n");
    for(u32 n=0;n<17;n++)log_hex(((u64)(0x3d00000+4*cp[n])<<32)|rsc_read(gpu+cp[n]));
    log_line("LMI_GPU_CP_PLAN_STREAMS\n");
    for(u32 n=0;n<6;n++) {
        log_hex(((u64)(0x3da0800+4*n)<<32)|rsc_read(s+0x800/4+n));
        log_hex(((u64)(0x3da0c00+4*n)<<32)|rsc_read(s+0xc00/4+n));
    }
    log_line("LMI_GPU_CP_PLAN_CB1\n");
    for(u32 n=0;n<13;n++)log_hex(((u64)(0x3da0000+cb[n])<<32)|rsc_read(s+cb[n]/4));
    if(rsc_read(s+0x9000/4)&1 || rsc_read(s+0x9058/4) || rsc_read(s+0x48/4))return 0;
    for(u32 n=1;n<6;n++)if(rsc_read(s+0x800/4+n))return 0;
    if(rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4)&0xc0 ||
       rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4))return 0;
    log_line("LMI_GPU_CP_PLAN_IDLE_CB1\n");return 1;
}
