/* GPU-owned RSCC DRV0 only. Never writes APSS DRV2 or an ARC MMIO address.
 * Caller must hold CM3 RESET1, CX/AHB clocks, and exclude firmware/sequencer
 * execution for the whole transaction. Register protocol: lmi rpmh-rsc.c.
 * Active GPU votes remain until reboot: restoring TCS storage does NOT undo
 * a completed rail vote. No claim of restoring unknown previous rail votes.
 * Mode16 is enabled only after the mode15 census was reviewed.
 * Mode20 selects firmware-defined active ARC TCS1 with shared IRQ bit1. */
#include "lmi-gpu-resources.h"
typedef unsigned long long vote_u64;
#ifdef LMI_GPU_RPMH_ARC_SLOT_PROBE
/* Pinned lmi firmware: 94c4=440e0fd4, 88e8=440e0fb4;
 * ARC command data selected at88ec; triggered at8862..88ac. */
#define VOTE_SLOT 1u
#else
#define VOTE_SLOT 0u
#endif
#define VOTE_IRQ (1u<<VOTE_SLOT)
#define VOTE_STRIDE (VOTE_SLOT*0x2a0/4)

extern void log_line(const char *);
extern void log_hex(vote_u64);
extern void delay(arc_u32,arc_u32);
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
extern vote_u64 io_map(vote_u64,vote_u64);
#endif
static const char timeout_marker[] __attribute__((section(".gpu_extra")))="LMI_GPU_RPMH_TIMEOUT_PAIRS\n";
#ifdef LMI_GPU_RPMH_HOST
extern arc_u32 vote_read(volatile arc_u32 *);
extern void vote_write(volatile arc_u32 *,arc_u32);
#else
static arc_u32 __attribute__((noinline,section(".gpu_helpers"))) vote_read(volatile arc_u32 *p) {
    vote_u64 value;
    __asm__ volatile("ldr %w0, [%1]\n\tuxtw %0, %w0":"=&r"(value):"r"(p):"memory");
    return (arc_u32)value;
}
static void __attribute__((noinline,section(".gpu_helpers"))) vote_write(volatile arc_u32 *p,arc_u32 v) {
    __asm__ volatile("str %w0, [%1]\n\tdsb sy":"+r"(v):"r"(p):"memory");
}
#endif
static void __attribute__((noinline,section(".gpu_helpers"))) vote_field(const char *key,arc_u32 value) {log_line(key);log_hex(value);}
static int __attribute__((noinline,section(".gpu_helpers"))) control(volatile arc_u32 *r,arc_u32 value) {
    vote_write(r+0xd14/4,value);
    for(arc_u32 n=0;n<200;n++) {
        if(vote_read(r+0xd14/4)==value)return 1;
        delay(1,1000);
    }
    return 0;
}
/* 1=completed,0=completed with bad status,2=pending/ownership uncertain. */
static int request(volatile arc_u32 *r,arc_u32 address,arc_u32 selector) {
    volatile arc_u32 *t=r+VOTE_STRIDE;
    if(vote_read(t+0xd18/4)!=1 || vote_read(r+0xd04/4)&VOTE_IRQ)return 2;
    vote_field("LMI_GPU_RPMH_REQUEST_ADDRESS\n",address);
    vote_field("LMI_GPU_RPMH_REQUEST_SELECTOR\n",selector);
    vote_write(t+0xd30/4,0x10108);
    vote_write(t+0xd34/4,address);
    vote_write(t+0xd38/4,selector);
    vote_write(t+0xd10/4,1);vote_write(t+0xd1c/4,1);
    if(!control(t,0x10000))return 3;
    vote_write(t+0xd14/4,0x1010000);
    for(arc_u32 n=0;n<2000;n++) {
        if(vote_read(r+0xd04/4)&VOTE_IRQ) {
            arc_u32 status=vote_read(t+0xd3c/4);
            vote_field("LMI_GPU_RPMH_COMMAND_STATUS\n",status);
            if(vote_read(t+0xd18/4)!=1)return 5;
            if(!control(t,0x10000) || !control(t,0))return 6;
            vote_write(t+0xd1c/4,0);vote_write(t+0xd10/4,0);
            vote_write(r+0xd08/4,VOTE_IRQ);
            if(vote_read(r+0xd04/4)&VOTE_IRQ)return 7;
            return (status&0x10100)==0x10100;
        }
        delay(100,1000);
    }
    /* Two raw pairs: CONTROL:IRQ_STATUS, CMD_STATUS:TCS_IDLE (high:low).
     * Read only, before returning the dependency-retention result. */
    log_line(timeout_marker);
    log_hex(((vote_u64)vote_read(t+0xd14/4)<<32)|vote_read(r+0xd04/4));
    log_hex(((vote_u64)vote_read(t+0xd3c/4)<<32)|vote_read(t+0xd18/4));
    return 4; /* IRQ completion timeout; caller retains clocks until reset. */
}
/* 0=refused or idle failure,1=both votes complete,2=keep clocks/CX until reset.
 * Parent MX must complete BEFORE issuing CX, as the vendor regulator chain.
 * The tested read-only census must show this exact independent DRV layout. */
int lmi_gpu_rscc_min_votes(volatile arc_u32 *r,const struct lmi_arc_resource *cx,
                         const struct lmi_arc_resource *mx) {
    if(!r || !cx || !mx || cx->address!=0x30000 || mx->address!=0x30010 ||
       cx->count!=9 || mx->count!=9 || cx->min_svs_index!=2 ||
       cx->levels[2]!=64 || mx->levels[2]!=128)return 0;
    arc_u32 dependent=0;
    for(arc_u32 n=0;n<mx->count;n++)if(mx->levels[n]>=cx->levels[2]) {dependent=n;break;}
    if(dependent!=2 || vote_read(r+0xc/4)!=0x4000000a ||
       (vote_read(r+0x10/4)&0x10000) || vote_read(r+0x404/4) ||
       (vote_read(r+0xd04/4)&(1u|VOTE_IRQ)))return 0;
    for(arc_u32 slot=0;slot<10;slot++) {
        arc_u32 at=(0xd00+slot*0x2a0)/4;
        if(vote_read(r+at+0x18/4)!=1 || vote_read(r+at+0x14/4) ||
           vote_read(r+at+0x1c/4) || vote_read(r+at+0x10/4))return 0;
    }
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
    volatile arc_u32 *g=(volatile arc_u32 *)io_map(0x3d6a000,0x30000);
    if(!g || vote_read(g+0x14000/4)!=1 || vote_read(g+0x14070/4))return 0;
    arc_u32 original_interface=vote_read(g+0x143a0/4);
    vote_field("LMI_GPU_RPMH_INTERFACE_BEFORE\n",original_interface);
    /* kgsl_gmu.h RPMH_ENABLE_MASK, vendor a6xx_gmu_power_config. No
     * CM3 execution or other active TCS can publish autonomous votes. */
    if(original_interface&~0xf11u)return 0;
#endif
#ifdef LMI_GPU_RSCC_SDE_PROBE
    /* Vendor a6xx_load_rsc_ucode: disable SDE clock gating with STATUS0
     * BIT24. Only after full idle census and while CM3 RESET1. */
    arc_u32 sde=vote_read(r+0x10/4)&0x1000000;
    vote_write(r+0x10/4,vote_read(r+0x10/4)|0x1000000);
    vote_field("LMI_GPU_RPMH_SDE_GATE_DISABLED\n",vote_read(r+0x10/4));
    if(!(vote_read(r+0x10/4)&0x1000000))return 8;
#endif
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
    vote_write(g+0x143a0/4,original_interface|0xf11);
    vote_field("LMI_GPU_RPMH_INTERFACE_ENABLED\n",vote_read(g+0x143a0/4));
    if(vote_read(g+0x143a0/4)!=(original_interface|0xf11))return 9;
#endif
    volatile arc_u32 *t=r+VOTE_STRIDE;
#ifdef LMI_GPU_RPMH_ARC_SLOT_PROBE
    vote_field("LMI_GPU_RPMH_TCS_SLOT\n",VOTE_SLOT);
#endif
    arc_u32 irq=vote_read(r+0xd00/4),saved[3];
    for(arc_u32 i=0;i<3;i++)saved[i]=vote_read(t+(0xd30+4*i)/4);
    vote_write(r+0xd00/4,irq|VOTE_IRQ);
    int result=request(r,mx->address,dependent);
    if(result==1)result=request(r,cx->address,2);
    if(result>=2)return result; /* Never rewrite a potentially pending command. */
    for(arc_u32 i=0;i<3;i++)vote_write(t+(0xd30+4*i)/4,saved[i]);
    vote_write(r+0xd00/4,irq);
    for(arc_u32 i=0;i<3;i++)if(vote_read(t+(0xd30+4*i)/4)!=saved[i])return 2;
    if(vote_read(r+0xd00/4)!=irq || vote_read(t+0xd14/4) ||
       vote_read(t+0xd10/4) || vote_read(t+0xd1c/4) ||
       vote_read(t+0xd18/4)!=1 || (vote_read(r+0xd04/4)&VOTE_IRQ))return 2;
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
    vote_write(g+0x143a0/4,original_interface);
    if(vote_read(g+0x143a0/4)!=original_interface)return 9;
    log_line("LMI_GPU_RPMH_INTERFACE_RESTORED\n");
#endif
#ifdef LMI_GPU_RSCC_SDE_PROBE
    vote_write(r+0x10/4,(vote_read(r+0x10/4)&~0x1000000u)|sde);
    if((vote_read(r+0x10/4)&0x1000000)!=sde)return 8;
    log_line("LMI_GPU_RPMH_SDE_GATE_RESTORED\n");
#endif
    log_line("LMI_GPU_RPMH_GPU_VOTES_RETAINED_UNTIL_RESET\n");
    if(result==1)log_line("LMI_GPU_RPMH_MIN_VOTES_COMPLETE\n");
    return result;
}
