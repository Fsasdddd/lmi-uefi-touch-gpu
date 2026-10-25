/* Mode36: source-defined SQE start, upstream A6xx ME_INIT and owned writeback.
 * No secure mode packet or secure/APSS/global reset register access.
 * SQE, ring, translations, OOB and all parents remain held on every outcome. */
#include "lmi-gpu-boot-regs.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define CP __attribute__((noinline,section(".gpu_cp")))
#define DATA __attribute__((section(".gpu_cp_data")))
#ifdef LMI_GPU_CP_CONFIG_READY
#define FINISH __attribute__((noinline,section(".gpu_cp_finish")))
#else
#define FINISH CP
#endif
extern u64 io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern int cache_sync(u64,u32,int);
extern void delay(u32,u32);
extern void log_line(const char *);
extern void log_hex(u64);
static const struct setting {u32 word,value;} settings[] DATA={
    {0x842,1},{0x8c2,0x02000140},{0x8c1,0x8040362c},{0x8c3,128},{0x98d,1},{0x844,0x6e},
    {0x830,0x1008000},{0x831,0},{0x800,0x1000000},{0x801,0},{0x802,0x0800020c}};
static const u32 status[] DATA={0x210,0x201,0x806,0x807,0x808,0x821,0x823,0x824};
int FINISH lmi_gpu_cp_complete(volatile u32 *gpu,volatile u32 *s,volatile u32 *g,u32 target) {
    u32 ready=0;
    for(u32 n=0;n<1000;n++) {
        if(rsc_read(s+0x9058/4)!=0x400 || rsc_read(s+0x48/4) || rsc_read(gpu+0x821) ||
           rsc_read(gpu+0x823) || rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4))break;
        if(rsc_read(gpu+0x806)==target && !(rsc_read(gpu+0x210)&~1u)) {ready=1;break;}
        delay(100,1000);
    }
    log_line("LMI_GPU_CP_STATUS\n");log_hex(target);
    for(u32 n=0;n<8;n++)log_hex(((u64)(0x3d00000+status[n]*4)<<32)|rsc_read(gpu+status[n]));
    const u32 faults[]={0x9058,0x9060,0x9064,0x9068,0x48};
    for(u32 n=0;n<5;n++)log_hex(((u64)(0x3da0000+faults[n])<<32)|rsc_read(s+faults[n]/4));
    return ready;
}
int CP lmi_gpu_cp(u64 pool,u32 bytes,volatile u32 *g) {
    volatile u32 *s=(void *)io_map(0x3da0000,0x10000),*gpu=(void *)io_map(0x3d00000,0x40000);
    if(!pool || pool&4095 || bytes!=81920 || !s || !gpu || !g ||
       rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4)&0xc0 || rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4) ||
       rsc_read(s+0x804/4)!=0x84010000 || rsc_read(s+0x9000/4)!=0xc000e7 ||
       rsc_read(s+0x9058/4)!=0x400 || rsc_read(s+0x48/4) ||
       rsc_read(gpu+0x806) || rsc_read(gpu+0x807) || rsc_read(gpu+0x808) ||
       rsc_read(gpu+0x821) || rsc_read(gpu+0x823) || rsc_read(gpu+0x16) || rsc_read(gpu+0x17))return 0;
#ifdef LMI_GPU_CP_FENCE
    /* Source-defined GMU ALLOW mode. ROQ lies inside the configured fence
     * range; do not assume OOB completion removed a boot-time clamp. */
    log_line("LMI_GPU_CP_AHB_FENCE_BEFORE\n");log_hex(rsc_read(g+BOOT_GMU_AO_AHB_FENCE_CTRL/4));
    rsc_write(g+BOOT_GMU_AO_AHB_FENCE_CTRL/4,0);
    u32 fence=rsc_read(g+BOOT_GMU_AO_AHB_FENCE_CTRL/4);
    log_line("LMI_GPU_CP_AHB_FENCE_ALLOW\n");log_hex(fence);
    if(fence)return 0;
#endif
#ifdef LMI_GPU_CP_SP_CLOCK
    /* Vendor a6xx_hwcg_set enables bit0 before CP register programming.
     * Isolate that prerequisite, preserving all other clock-control bits. */
    u32 clock=rsc_read(g+BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4);
    log_line("LMI_GPU_CP_SP_CLOCK_BEFORE\n");log_hex(clock);
    rsc_write(g+BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4,clock|1);
    u32 after=rsc_read(g+BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4);
    log_line("LMI_GPU_CP_SP_CLOCK_ENABLED\n");log_hex(after);
    if(after!=(clock|1))return 0;
#endif
    volatile u32 *ring=(void *)pool,*scratch=(void *)(pool+16*4096);
    const u32 init[]={0x70c80008,0x2f,3,0x20000000,0,0,0,0,0};
    log_line("LMI_GPU_CP_INIT_PACKET\n");
    for(u32 n=0;n<9;n++) {if(ring[n])return 0;ring[n]=init[n];log_hex(init[n]);}
    if(!cache_sync(pool,128,1) || !cache_sync((u64)scratch,128,0) || scratch[0])return 0;
    log_line("LMI_GPU_CP_CONFIG\n");
    for(u32 n=0;n<11;n++) {
#if defined(LMI_GPU_CP_CONFIG_PLAN) || defined(LMI_GPU_CP_CONFIG_READY)
        if(rsc_read(gpu+0x808) || rsc_read(gpu+0x807) || rsc_read(gpu+0x821) || rsc_read(gpu+0x823) ||
           rsc_read(s+0x9058/4)!=0x400 || rsc_read(s+0x48/4) || rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4))return 0;
#endif
        rsc_write(gpu+settings[n].word,settings[n].value);
        u32 value=rsc_read(gpu+settings[n].word);
        log_hex(((u64)(0x3d00000+settings[n].word*4)<<32)|value);
#if !defined(LMI_GPU_CP_CONFIG_PLAN) && !defined(LMI_GPU_CP_CONFIG_READY)
        if(value!=settings[n].value)return 0;
#endif
    }
#if defined(LMI_GPU_CP_CONFIG_PLAN) || defined(LMI_GPU_CP_CONFIG_READY)
    /* Read the entire inert configuration after the mode41 settling interval.
     * PLAN only observes; READY requires all eleven exact values before SQE.
     * This is one bounded sample, not a retry loop or a CP execution proof. */
    delay(100,1000);
    u32 matches=0;
    log_line("LMI_GPU_CP_CONFIG_DELAYED\n");
    for(u32 n=0;n<11;n++) {
        u32 value=rsc_read(gpu+settings[n].word);
        log_hex(((u64)(0x3d00000+settings[n].word*4)<<32)|value);
        if(value==settings[n].value)matches|=1u<<n;
    }
    log_line("LMI_GPU_CP_CONFIG_MATCH_MASK\n");log_hex(matches);
    if(rsc_read(gpu+0x808) || rsc_read(gpu+0x806) || rsc_read(gpu+0x807) || rsc_read(gpu+0x821) ||
       rsc_read(gpu+0x823) || rsc_read(s+0x9058/4)!=0x400 || rsc_read(s+0x48/4) ||
       rsc_read(g+BOOT_GMU_AHB_FENCE_STATUS/4))return 0;
    log_line("LMI_GPU_CP_CONFIG_STOPPED\n");
    for(u32 n=0x806;n<=0x808;n++)log_hex(rsc_read(gpu+n));
#ifdef LMI_GPU_CP_CONFIG_PLAN
    log_line("LMI_GPU_CP_CONFIG_STOPPED_HELD\n");return 1;
#else
    if(matches!=0x7ff)return 0;
    log_line("LMI_GPU_CP_CONFIG_READY\n");
#endif
#endif
    log_line("LMI_GPU_CP_SQE_START\n");rsc_write(gpu+0x808,1);
    rsc_write(gpu+0x807,9);
    if(!lmi_gpu_cp_complete(gpu,s,g,9))return 0;
    log_line("LMI_GPU_CP_INIT_VERIFIED\n");
    const u32 write[]={0x703d8003,0x1010000,0,0x650c0de1};
    log_line("LMI_GPU_CP_WRITE_PACKET\n");
    for(u32 n=0;n<4;n++) {ring[9+n]=write[n];log_hex(write[n]);}
    if(!cache_sync(pool,128,1))return 0;
    rsc_write(gpu+0x807,13);
    if(!lmi_gpu_cp_complete(gpu,s,g,13) || !cache_sync((u64)scratch,128,0))return 0;
    log_line("LMI_GPU_CP_FENCE\n");log_hex(scratch[0]);
    if(scratch[0]!=0x650c0de1)return 0;
    log_line("LMI_GPU_CP_FENCE_VERIFIED_HELD\n");return 1;
}
