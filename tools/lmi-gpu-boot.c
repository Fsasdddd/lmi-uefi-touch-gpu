/* Source-defined lmi A650 GMU cold boot. No CPU/GX/APSS/secure register writes.
 * Requires live SID5 stage1, verified 47-page backing and 200MHz/MX/CX scope.
 * 2=refused before writes;0=state modified/uncertain, retain everything;
 * 3=FW_INIT+HFI response verified, intentionally remain active until reboot. */
#include "lmi-gpu-boot-regs.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define BOOT_CODE __attribute__((noinline,section(".gpu_boot")))
#define BOOT_DATA __attribute__((section(".gpu_boot_data")))
_Static_assert(BOOT_GMU_CM3_SYSRESET==0x14000 && BOOT_GMU_CM3_FW_INIT_RESULT==0x14070 &&
               BOOT_GMU_RPMH_CTRL==0x143a0,"GMU offsets must match the previously verified mapping");
extern u64 io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern void delay(u32,u32);
extern void log_line(const char *);
extern void log_hex(u64);
extern const unsigned char *image_file(const char *,const char *,u64 *,int *);
extern u32 lmi_gpu_firmware_crc(const unsigned char *,u32);
static const u32 canary BOOT_DATA=0x650bad21;
u32 BOOT_CODE lmi_gpu_exec_canary(u32 input) {return input^*(volatile const u32 *)&canary;}
static const struct block {u32 off,size,file;} blocks[] BOOT_DATA={
    {0x3000,192,160},{0x3200,320,368},{0x3400,14092,704},
    {0x7000,3776,37732},{0xafdc,24,41524}};
static const struct setting {u32 off,value;} settings[] BOOT_DATA={
    {BOOT_GMU_GENERAL_7,1},{BOOT_GMU_CM3_FW_INIT_RESULT,0},
    {BOOT_GMU_CM3_BOOT_CONFIG,2},{BOOT_GMU_HFI_QTBL_ADDR,0x60001000},
    {BOOT_GMU_HFI_QTBL_INFO,1},{BOOT_GMU_AHB_FENCE_RANGE_0,0x80a008a0},
    {BOOT_GMU_HFI_SFR_ADDR,LMI_GMU_CHIPID},{BOOT_GPU_GMU_CX_GMU_PWR_COL_CP_MSG,0x60000000},
    {BOOT_GMU_SYS_BUS_CONFIG,1},{BOOT_GMU_ICACHE_CONFIG,1},{BOOT_GMU_DCACHE_CONFIG,1},
    {BOOT_GMU_PWR_COL_INTER_FRAME_CTRL,0x9c40400},{BOOT_GMU_RPMH_CTRL,0xf11},
    {BOOT_GPU_GMU_CX_GMU_PWR_COL_CP_RESP,0}};
static const u32 status[] BOOT_DATA={BOOT_GMU_CM3_SYSRESET,BOOT_GMU_CM3_FW_INIT_RESULT,
    BOOT_GMU_CM3_FW_BUSY,BOOT_GMU_HFI_CTRL_STATUS,BOOT_GMU_HFI_VERSION_INFO,
    BOOT_GMU_AO_HOST_INTERRUPT_STATUS,BOOT_GMU_AHB_FENCE_STATUS,
    BOOT_GPU_GMU_CX_GMU_RPMH_POWER_STATE,0xafdc,0xafe0};
#ifdef LMI_GPU_FAL_VETO
static const char fal_marker[] __attribute__((section(".gpu_cp_data")))="LMI_GPU_GMU_FAL_VETO\n";
static int __attribute__((noinline,section(".gpu_cp"))) fal_veto(volatile u32 *g) {
    u32 before=rsc_read(g+BOOT_GPU_GMU_CX_GMU_CX_FAL_INTF/4);
    /* A650 and A650v2 set veto_fal10 in the pinned vendor core definition.
     * a6xx_gmu_fw_start writes this before TCM upload and CM3 release. */
    rsc_write(g+BOOT_GPU_GMU_CX_GMU_CX_FAL_INTF/4,1);
    u32 after=rsc_read(g+BOOT_GPU_GMU_CX_GMU_CX_FAL_INTF/4);
    log_line(fal_marker);log_hex(before);log_hex(after);
    return after==1;
}
#endif
/* The existing main RX replacement has room for the status reader. Keeping
 * this diagnostic there leaves the separately audited boot padding bounded. */
static void __attribute__((noinline,section(".text.gpu_boot_status"))) dump(volatile u32 *g,volatile u32 *s) {
    log_line("LMI_GPU_GMU_BOOT_STATUS\n");
    for(u32 n=0;n<10;n++)log_hex(((u64)(0x3d6a000+status[n])<<32)|rsc_read(g+status[n]/4));
    const u32 faults[]={0x8058,0x8060,0x8064,0x48};
    for(u32 n=0;n<4;n++)log_hex(((u64)(0x3da0000+faults[n])<<32)|rsc_read(s+faults[n]/4));
}
static int BOOT_CODE poll(volatile u32 *word,u32 mask,u32 expected) {
    for(u32 n=0;n<1000;n++) {
        if((rsc_read(word)&mask)==expected)return 1;
        delay(100,1000);
    }
    return 0;
}
int BOOT_CODE lmi_gpu_gmu_boot(u64 root,u64 pool,u32 bytes) {
    u32 fetched=lmi_gpu_exec_canary(0x1badb002);
    log_line("LMI_GPU_EXEC_CANARY\n");log_hex(fetched);
    if(fetched!=0x7ea61d23)return 2;
    volatile u32 *g=(volatile u32 *)io_map(0x3d6a000,0x30000);
    volatile u32 *s=(volatile u32 *)io_map(0x3da0000,0x10000);
    u64 size=0;int disk=-1;
    const unsigned char *fw=image_file("fw","a650_gmu.bin",&size,&disk);
    if(!g || !s || !pool || pool&4095 || bytes<47*4096 || bytes>47*4096+16383 ||
       !root || root&4095 || root>>36 || !fw || size!=41548 || lmi_gpu_firmware_crc(fw,41548)!=0x5c66275c ||
       rsc_read(g+BOOT_GMU_CM3_SYSRESET/4)!=1 || rsc_read(g+BOOT_GMU_CM3_FW_INIT_RESULT/4) ||
       rsc_read(g+BOOT_GMU_HFI_CTRL_STATUS/4) || rsc_read(g+BOOT_GMU_HFI_CTRL_INIT/4) ||
       rsc_read(s+0x8000/4)!=0xc000e7 || rsc_read(s+0x800/4)!=0x84000005 ||
       (rsc_read(s+0xc00/4)&0x030303ff)!=0x300 || rsc_read(s+0x8058/4)!=0x400 || rsc_read(s+0x48/4) ||
       rsc_read(s+0x8020/4)!=(u32)root || rsc_read(s+0x8024/4)!=((u32)(root>>32)|0x10000))return 2;
    log_line("LMI_GPU_GMU_BOOT_BEGIN\n");
#ifdef LMI_GPU_FAL_VETO
    if(!fal_veto(g))return 0;
#endif
    /* Vendor cold boot enables TCM retention before the AHB upload. */
    rsc_write(g+BOOT_GMU_GENERAL_7/4,1);
    if(rsc_read(g+BOOT_GMU_GENERAL_7/4)!=1)return 0;
    for(u32 n=0;n<5;n++) {
        const struct block *b=&blocks[n];const u32 *payload=(const u32 *)(fw+b->file);
        for(u32 k=0;k<b->size/4;k++)rsc_write(g+b->off/4+k,payload[k]);
    }
    u32 mismatches=0;
    for(u32 n=0;n<5;n++) {
        const struct block *b=&blocks[n];const u32 *payload=(const u32 *)(fw+b->file);
        for(u32 k=0;k<b->size/4;k++)mismatches+=rsc_read(g+b->off/4+k)!=payload[k];
    }
    log_line("LMI_GPU_GMU_BOOT_TCM_MISMATCHES\n");log_hex(mismatches);
    if(mismatches || rsc_read(g+0xafe0/4)!=0x20010008)return 0;
    log_line("LMI_GPU_GMU_BOOT_CONFIG\n");
    for(u32 n=0;n<14;n++) {
        rsc_write(g+settings[n].off/4,settings[n].value);
        u32 actual=rsc_read(g+settings[n].off/4);
        log_hex(((u64)(0x3d6a000+settings[n].off)<<32)|actual);
        if(actual!=settings[n].value)return 0;
    }
    if(rsc_read(g+BOOT_GMU_CM3_SYSRESET/4)!=1)return 0;
    log_line("LMI_GPU_GMU_BOOT_RELEASE\n");
    rsc_write(g+BOOT_GMU_CM3_SYSRESET/4,0);
    u32 ready=poll(g+BOOT_GMU_CM3_FW_INIT_RESULT/4,0x1ff,0x100);
    log_line("LMI_GPU_GMU_BOOT_FW_READY\n");log_hex(ready);
    if(ready) {
        rsc_write(g+BOOT_GMU_HFI_CTRL_INIT/4,1);
        ready=poll(g+BOOT_GMU_HFI_CTRL_STATUS/4,1,1);
        log_line("LMI_GPU_GMU_BOOT_HFI_READY\n");log_hex(ready);
    }
#ifdef LMI_GPU_HFI_IO
    if(ready) {
        extern int lmi_gpu_hfi_version(u64,u32,volatile u32 *);
        ready=lmi_gpu_hfi_version(pool,bytes,g);
        log_line("LMI_GPU_HFI_IO_RESULT\n");log_hex(ready);
    }
#endif
#ifdef LMI_GPU_TABLE_PLAN
    if(ready) {
        extern int lmi_gpu_table_plan(void);
        ready=lmi_gpu_table_plan();
        log_line("LMI_GPU_TABLE_PLAN_RESULT\n");log_hex(ready);
    }
#endif
#ifdef LMI_GPU_HFI_PERF
    if(ready) {
        extern int lmi_gpu_hfi_perf(u64,u32,volatile u32 *);
        ready=lmi_gpu_hfi_perf(pool,bytes,g);
        log_line("LMI_GPU_HFI_PERF_RESULT\n");log_hex(ready);
    }
#endif
#ifdef LMI_GPU_HFI_CORE
    if(ready) {
        extern int lmi_gpu_hfi_core(u64,u32,volatile u32 *);
        ready=lmi_gpu_hfi_core(pool,bytes,g);
        log_line("LMI_GPU_HFI_CORE_RESULT\n");log_hex(ready);
    }
#endif
#ifdef LMI_GPU_GX
    if(ready) {
        extern int lmi_gpu_gx(u64,u32,volatile u32 *);
        ready=lmi_gpu_gx(pool,bytes,g);
        log_line("LMI_GPU_GX_RESULT\n");log_hex(ready);
    }
#endif
    dump(g,s);
    if(!ready || rsc_read(g+BOOT_GMU_CM3_SYSRESET/4) ||
       rsc_read(s+0x8058/4)!=0x400 || rsc_read(s+0x48/4))return 0;
    log_line("LMI_GPU_GMU_BOOT_ACTIVE_HELD\n");
    return 3;
}
