/* lmi mode27: real GMU kernel stream SID5/mask400 and CB0 stage1.
 * Caller holds confirmed MX/CX votes, 200MHz, CX/AHB/MEMNOC/SNOC, RESET1.
 * All 47 backing pages stay wired throughout attach/detach; no ATS/ATOS.
 * No firmware execution/DMA in this stage. Revoke SMR before TLBI, SCTLR,
 * tables and allocation teardown. Uncertain detach retains all dependencies.
 * CBAR stage1 TYPE remains inert as in the previously tested vendor teardown. */
/* SCTLR uses the architecturally defined ASIDPNE=0. That private-namespace
 * hint affects broadcast maintenance only; local TLBIASID/SYNC is independent.
 * This target is checked exactly, never by masking an ignored hint write. */
typedef unsigned int u32;
typedef unsigned long long u64;
#ifdef LMI_GPU_GMU_BOOT
#include "lmi-gpu-runtime.h"
#endif
extern u64 io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern void log_line(const char *);
extern void log_hex(u64);
extern void delay(u32,u32);
extern int lmi_gpu_ram_consume(int (*)(u64,void *),void *);
static const u32 offsets[] __attribute__((section(".gpu_extra")))={
    0x1800,0x8010,0x8030,0x8020,0x8024,0x8028,0x802c,0x8038,0x803c,
    0x8000,0xc00,0x800,0x1000,0x8058,0x48};
struct route_context {volatile u32 *s,*g;};
static int __attribute__((noinline)) reset_idle(struct route_context *c) {
    return rsc_read(c->g+0x14000/4)==1 && !rsc_read(c->g+0x14070/4);
}
static int __attribute__((section(".gpu_helpers"))) sync_context(volatile u32 *s) {
    rsc_write(s+0x8610/4,1);rsc_write(s+0x87f0/4,0);
    for(u32 n=0;n<1000;n++) {
        if(!(rsc_read(s+0x87f4/4)&1))return 1;
        delay(1,1000);
    }
    return 0;
}
static void __attribute__((section(".gpu_helpers"))) dump(const char *label,volatile u32 *s) {
    log_line(label);
    for(u32 n=0;n<15;n++)log_hex(((u64)(0x3da0000+offsets[n])<<32)|rsc_read(s+offsets[n]/4));
}
/* Consumer convention: 1=attach/detach proved,2=incomplete safely detached,
 * 0=retain backing and ALL parents until bounded reset. */
static int route_consumer(u64 root,void *context) {
#ifdef LMI_GPU_GMU_BOOT
    struct lmi_gpu_live_backing *live=context;
    struct route_context *c=live->owner_context;
#else
    struct route_context *c=context;volatile u32 *s=c->s;
#endif
#ifdef LMI_GPU_GMU_BOOT
    volatile u32 *s=c->s;
#endif
    if(!root || root&4095 || root>>36 || !reset_idle(c) ||
       rsc_read(s+0x20/4)!=0x4c017e06 || rsc_read(s+0x24/4)!=0x20000005 ||
       rsc_read(s+0)&8 || rsc_read(s+0x48/4) || rsc_read(s+0x8058/4))return 2;
    for(u32 n=0;n<6;n++)if(rsc_read(s+(0x800+4*n)/4))return 2;
    u32 saved[13],target[]={1,0x38071,0x803519,(u32)root,(u32)(root>>32)|0x10000,
        0,0,0xf404ff44,0,0xc000e7,0,0x84000005,0x1f300};
    for(u32 n=0;n<13;n++)saved[n]=rsc_read(s+offsets[n]/4);
    if(saved[0] || saved[9]&1 || saved[11] || saved[12])return 2;
    for(u32 n=0;n<13;n++)if(saved[n]!=rsc_read(s+offsets[n]/4))return 2;
    target[10]=(saved[10]&~0x030303ffu)|0x300;
    log_line("LMI_GPU_GMU_ROUTE_ROOT\n");log_hex(root);
    dump("LMI_GPU_GMU_ROUTE_BEFORE\n",s);
    u32 good=1,cbar=0,need_sync=0;
    for(u32 n=0;n<9;n++) {
        rsc_write(s+offsets[n]/4,target[n]);
        if(!n) {
            rsc_write(s+0x1000/4,0x1f300);cbar=rsc_read(s+0x1000/4);
            if(cbar && cbar!=0x1f300)return 0;
            if(!cbar) {good=0;break;}
        }
        if(rsc_read(s+offsets[n]/4)!=target[n]) {good=0;break;}
    }
    if(good) {
        need_sync=1;
        if(!sync_context(s))return 0;
        for(u32 n=9;n<12;n++) {
            if(!reset_idle(c))return 0;
            rsc_write(s+offsets[n]/4,target[n]);
            if(rsc_read(s+offsets[n]/4)!=target[n]) {good=0;break;}
        }
        delay(100,1000);
    }
    dump("LMI_GPU_GMU_ROUTE_ACTUAL\n",s);
    for(u32 n=0;n<13;n++)if(rsc_read(s+offsets[n]/4)!=target[n])good=0;
    if(!reset_idle(c))return 0;
    for(u32 n=1;n<6;n++)if(rsc_read(s+(0x800+4*n)/4))return 0;
    if(rsc_read(s+0x48/4) || rsc_read(s+0x8058/4)!=0x400)good=0;
#ifdef LMI_GPU_GMU_BOOT
    if(good) {
        extern int lmi_gpu_gmu_boot(u64,u64,u32);
        int started=lmi_gpu_gmu_boot(root,live->cpu_address,live->allocation_bytes);
        log_line("LMI_GPU_GMU_BOOT_RESULT\n");log_hex(started);
        if(started==3)return 3;
        if(started==0)return 0;
        good=0;
    }
#endif
    /* No config/backing restoration until the route is proven unpublished. */
    rsc_write(s+0x800/4,saved[11]);
    if(rsc_read(s+0x800/4)!=saved[11])return 0;
    rsc_write(s+0xc00/4,saved[10]);
    if(rsc_read(s+0xc00/4)!=saved[10] || (need_sync && !sync_context(s)))return 0;
    rsc_write(s+0x8000/4,saved[9]);
    if(rsc_read(s+0x8000/4)!=saved[9])return 0;
    for(u32 n=1;n<9;n++)rsc_write(s+offsets[n]/4,saved[n]);
    rsc_write(s+0x1800/4,saved[0]);
    dump("LMI_GPU_GMU_ROUTE_RESTORED\n",s);
    for(u32 n=0;n<12;n++)if(rsc_read(s+offsets[n]/4)!=saved[n])return 0;
    if(rsc_read(s+0x1000/4)!=cbar || rsc_read(s+0x48/4) || rsc_read(s+0x8058/4) || !reset_idle(c))return 0;
    log_line("LMI_GPU_GMU_ROUTE_DETACH_OK\n");
    return good?1:2;
}
int lmi_gpu_gmu_route_probe(void) {
    struct route_context c={(volatile u32 *)io_map(0x3da0000,0x10000),
                            (volatile u32 *)io_map(0x3d6a000,0x30000)};
    if(!c.s || !c.g)return 0;
    int result=lmi_gpu_ram_consume(route_consumer,&c);
#ifdef LMI_GPU_GMU_BOOT
    if(result==3)return 3;
#endif
    return result==0?2:result==1?1:0;
}
