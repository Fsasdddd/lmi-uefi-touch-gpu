/* Mode46: only after strict original GPU13 PAS authentication succeeds.
 * Standard A6xx CP_SET_SECURE_MODE(0), then a distinct GPU-only writeback.
 * No trust-control register fallback; keep every dependency until reboot. */
#include "lmi-gpu-boot-regs.h"
typedef unsigned long long u64;
typedef unsigned int u32;
#define NORMAL __attribute__((noinline,section(".gpu_unsecure")))
#define DIAG __attribute__((noinline,section(".gpu_normal_diag")))
#define DIAG_DATA __attribute__((section(".gpu_normal_diag_data")))
extern u64 io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern int cache_sync(u64,u32,int);
extern int lmi_gpu_cp_complete(volatile u32 *,volatile u32 *,volatile u32 *,u32);
extern void log_line(const char *);
extern void log_hex(u64);
extern void delay(u32,u32);
static const u32 canary __attribute__((section(".gpu_unsecure_data")))=0x65065046;
static const char begin[] __attribute__((section(".gpu_extra")))="LMI_GPU_NORMAL_BEGIN\n";
static const char sp_clock[] __attribute__((section(".gpu_extra")))="LMI_GPU_NORMAL_SP\n";
static const u32 mode[] __attribute__((section(".gpu_extra")))={0x70e60001,0};
u32 NORMAL lmi_gpu_normal_canary(u32 v) {return v^*(volatile const u32 *)&canary;}
static const u32 diag_canary DIAG_DATA=0x65065048;
static const char addr_before[] DIAG_DATA="LMI_GPU_NORMAL_ADDR_BEFORE\n";
static const char addr_after[] DIAG_DATA="LMI_GPU_NORMAL_ADDR_AFTER\n";
static const char clock_policy[] DIAG_DATA="LMI_GPU_NORMAL_CLOCK_POLICY\n";
/* Vendor a6xx_enable_64bit and a650_hwcg_regs: these are observations only.
 * No secure/trust controls or fault-clearing registers are sampled. */
static const u32 diag_words[] DIAG_DATA={
    0x842,0xc01,0x8601,0x8e05,0x9e01,0xbe05,0xa601,0x9601,0xe00,0xae01,0xb601,
    0xae,0xb0,0x11b,0x10b,0x118};
u32 DIAG lmi_gpu_normal_diag_canary(u32 v) {return v^*(volatile const u32 *)&diag_canary;}
/* Vendor a6xx_enable_64bit / upstream hw_init precede secure-mode execution.
 * CP is already configured and must remain 1. Only the ten nonsecure block
 * address controls are added here; SECVID address controls are excluded.
 * There is no queued work: caller has proved idle at RPTR/WPTR13. */
int DIAG lmi_gpu_normal_address_modes(volatile u32 *gpu,volatile u32 *g) {
    volatile u32 *s=(void *)io_map(0x3da0000,0x10000);
    if(!s || rsc_read(gpu+diag_words[0])!=1)return 0;
    log_line(addr_before);
    u32 valid=1;
    for(u32 n=1;n<11;n++) {
        u32 value=rsc_read(gpu+diag_words[n]);
        log_hex(((u64)(0x3d00000+4*diag_words[n])<<32)|value);
        if(value>1)valid=0;
    }
    if(!valid)return 0;
    for(u32 n=1;n<11;n++)rsc_write(gpu+diag_words[n],1);
    delay(100,1000);
    int ready=lmi_gpu_cp_complete(gpu,s,g,13);
    log_line(addr_after);
    for(u32 n=1;n<11;n++) {
        u32 value=rsc_read(gpu+diag_words[n]);
        log_hex(((u64)(0x3d00000+4*diag_words[n])<<32)|value);
        if(value!=1)valid=0;
    }
    return valid && ready;
}
/* a6xx_set_hwcg returns without a SP force write if HWCG is already disabled
 * (RBBM_CLOCK_CNTL==0). Keep that distinct from the enabled HWCG path: a failed
 * SP force readback never falls back. Source-defined SP/GX off/transition bits
 * must stay clear in both paths; completion/fault/fence checks remain intact. */
int DIAG lmi_gpu_normal_sp_clock(volatile u32 *g) {
    u32 fetched=lmi_gpu_normal_diag_canary(0x1badb002);
    log_line("LMI_GPU_NORMAL_DIAG_CANARY\n");log_hex(fetched);
    if(fetched!=0x7eabe04a)return 0;
    volatile u32 *gpu=(void *)io_map(0x3d00000,0x40000);
    if(!gpu || !lmi_gpu_normal_address_modes(gpu,g))return 0;
    u32 clock=rsc_read(gpu+0xae),force=clock!=0;
    if((clock && clock!=0x8aa8aa82) || rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4)&0xd7)return 0;
    volatile u32 *reg=g+BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4;
    u32 before=rsc_read(reg);
    if(force) {rsc_write(reg,before|1);delay(100,1000);}
    u32 after=rsc_read(reg);
    log_line(sp_clock);log_hex(before);log_hex(after);
    u32 actual_clock=rsc_read(gpu+0xae),state=rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4);
    log_line(clock_policy);log_hex(force);log_hex(actual_clock);log_hex(state);
    log_line("LMI_GPU_NORMAL_PREREQ_READONLY\n");
    log_hex(((u64)0x3d7e340<<32)|rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4));
    for(u32 n=0;n<sizeof(diag_words)/sizeof(diag_words[0]);n++)
        log_hex(((u64)(0x3d00000+4*diag_words[n])<<32)|rsc_read(gpu+diag_words[n]));
    if(actual_clock!=clock || state&0xd7)return 0;
    return force?after==(before|1):before==0 && after==0;
}
int NORMAL lmi_gpu_unsecure(u64 pool,u32 bytes,volatile u32 *g) {
    u32 fetched=lmi_gpu_normal_canary(0x1badb002);
    log_line(begin);log_hex(fetched);
    if(fetched!=0x7eabe044 || !pool || pool&4095 || bytes!=81920 || !g)return 0;
    volatile u32 *gpu=(void *)io_map(0x3d00000,0x40000),*s=(void *)io_map(0x3da0000,0x10000);
    if(!gpu || !s || rsc_read(gpu+0x806)!=13 || rsc_read(gpu+0x807)!=13 ||
       rsc_read(gpu+0x808)!=1 || !lmi_gpu_cp_complete(gpu,s,g,13))return 0;
    if(!lmi_gpu_normal_sp_clock(g))return 0;
    volatile u32 *ring=(void *)pool,*scratch=(void *)(pool+65536);
    if(!cache_sync((u64)scratch,128,0) || scratch[0]!=0x650c0de1 || scratch[1])return 0;
    for(u32 n=13;n<19;n++)if(ring[n])return 0;
    const u32 write[]={0x703d8003,0x1010004,0,0x650c0de2};
    log_line("LMI_GPU_NORMAL_PACKET\n");
    for(u32 n=0;n<2;n++) {ring[13+n]=mode[n];log_hex(mode[n]);}
    if(!cache_sync(pool,128,1))return 0;
    rsc_write(gpu+0x807,15);
    if(!lmi_gpu_cp_complete(gpu,s,g,15))return 0;
    log_line("LMI_GPU_NORMAL_WRITE_PACKET\n");
    for(u32 n=0;n<4;n++) {ring[15+n]=write[n];log_hex(write[n]);}
    if(!cache_sync(pool,128,1))return 0;
    rsc_write(gpu+0x807,19);
    if(!lmi_gpu_cp_complete(gpu,s,g,19) || !cache_sync((u64)scratch,128,0))return 0;
    log_line("LMI_GPU_NORMAL_FENCE\n");log_hex(scratch[0]);log_hex(scratch[1]);
    if(scratch[0]!=0x650c0de1 || scratch[1]!=0x650c0de2)return 0;
    log_line("LMI_GPU_NORMAL_VERIFIED_HELD\n");return 1;
}
