/* Mode33: upstream nonlegacy START, vendor blocking stock-bin DCVS, GPU OOB.
 * Only GMU HFI/interrupt writes; never program PLL, GX GDSC or secure state.
 * Keep OOB and all DMA/parent dependencies held until the bounded reboot. */
#include "lmi-gpu-boot-regs.h"
#include "lmi-gpu-hfi-transfer.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define GX __attribute__((noinline,section(".gpu_gx")))
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern void delay(u32,u32);
extern void log_line(const char *);
extern void log_hex(u64);
int GX lmi_gpu_gx(u64 pool,u32 bytes,volatile u32 *g) {
    const u32 start[]={0x0050010a};
    const struct lmi_hfi_trace st={"LMI_GPU_HFI_START_REQUEST\n","LMI_GPU_HFI_START_REPLY\n","LMI_GPU_HFI_START_ACK_VERIFIED\n"};
    if(!g || !lmi_gpu_hfi_exchange(pool,bytes,g,start,1,228,16,&st))return 0;
    /* Explicit v57 experiment: uploaded speed-bin0 index7 = 670MHz, ARC320.
     * GMU selects its stock voltage dependency; ff leaves BW unchanged. */
    const u32 dcvs[]={0x0060041e,1,7,0xff};
    const struct lmi_hfi_trace dv={"LMI_GPU_HFI_DCVS_REQUEST\n","LMI_GPU_HFI_DCVS_REPLY\n","LMI_GPU_HFI_DCVS_ACK_VERIFIED\n"};
    if(!lmi_gpu_hfi_exchange(pool,bytes,g,dcvs,4,232,20,&dv))return 0;
    u32 before=rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4);
    log_line("LMI_GPU_GX_BEFORE\n");log_hex(before);
    if(rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4) ||
       rsc_read(g+BOOT_GMU_AO_HOST_INTERRUPT_STATUS/4)&0x29 ||
       rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4))return 0;
    log_line("LMI_GPU_GX_OOB_REQUEST\n");log_hex(0x40000000);
    rsc_write(g+BOOT_GMU_HOST2GMU_INTR_SET/4,0x40000000);
    u32 irq=0,ready=0;
    for(u32 n=0;n<1000;n++) {
        irq=rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4);
        if(irq==0x80000000) {ready=1;break;}
        if(irq)break;
        delay(100,1000);
    }
    log_line("LMI_GPU_GX_OOB_REPLY\n");log_hex(irq);
    if(!ready)return 0;
    /* Clear the ACK only. HOST2GMU bit31 would release the keepalive. */
    rsc_write(g+BOOT_GMU_GMU2HOST_INTR_CLR/4,0x80000000);
    u32 after=rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4);
    log_line("LMI_GPU_GX_AFTER\n");log_hex(after);
    if(after&0xc0 || rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4) ||
       rsc_read(g+BOOT_GMU_AO_HOST_INTERRUPT_STATUS/4)&0x29 ||
       rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4))return 0;
    log_line("LMI_GPU_GX_OOB_HELD\n");
#ifdef LMI_GPU_CP_PLAN
    extern int lmi_gpu_cp_plan(volatile u32 *);
    u32 plan=lmi_gpu_cp_plan(g);
    log_line("LMI_GPU_CP_PLAN_RESULT\n");log_hex(plan);
#ifdef LMI_GPU_CORE_MEMORY
    if(plan) {
        extern int lmi_gpu_core_memory(volatile u32 *);
        plan=lmi_gpu_core_memory(g);
        log_line("LMI_GPU_CORE_MEMORY_RESULT\n");log_hex(plan);
    }
#endif
    return plan;
#else
    return 1;
#endif
}
