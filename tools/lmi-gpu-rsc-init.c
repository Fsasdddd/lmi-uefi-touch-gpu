/* lmi vendor a6xx_load_rsc_ucode/a6xx_load_pdc_ucode, A650 pdc_in_aop.
 * Mode22 verifies programming and exact restoration only. Mode23 isolates
 * SDE plus the five RSC SRAM words, leaving hidden/PDC registers unchanged.
 * Mode24 adds only the vendor PDC start/enable pair to that verified sequence.
 * Mode25 keeps that state around the source-defined GPU DRV0 vote attempt.
 * Modes22-24 have no TCS request;
 * GMU reset release, PDC sequencer upload or QMP access. Caller holds CX/AHB.
 * Any uncertain restore retains parent clocks/CX until bounded reboot. */
typedef unsigned int u32;
typedef unsigned long long u64;
extern u64 io_map(u64,u64);
extern void log_line(const char *);
extern void log_hex(u64);
#ifdef LMI_GPU_RSC_INIT_HOST
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
#else
u32 __attribute__((noinline,section(".gpu_helpers"))) rsc_read(volatile u32 *p) {
    u64 v;
    __asm__ volatile("ldr %w0, [%1]\n\tuxtw %0, %w0":"=&r"(v):"r"(p):"memory");
    return (u32)v;
}
void __attribute__((noinline,section(".gpu_helpers"))) rsc_write(volatile u32 *p,u32 v) {
    __asm__ volatile("str %w0, [%1]\n\tdsb sy":"+r"(v):"r"(p):"memory");
}
#endif
#ifdef LMI_GPU_GMU_BOOT
#define RSC_CONST __attribute__((section(".gpu_boot_data")))
#define RSC_BOOT_CONST RSC_CONST
#elif defined(LMI_GPU_GMU_ROUTE)
#define RSC_CONST __attribute__((section(".gpu_extra")))
#define RSC_BOOT_CONST
#else
#define RSC_CONST
#define RSC_BOOT_CONST
#endif
static const u32 offsets[] RSC_CONST={0x10,0x2c,0x38,0x34,0x40,0x3c,0x48,0x44,
    0x400,0x20,0x24,0x28,0x600,0x604,0x608,0x60c,0x610,0x4520,0x4500};
static const u32 expected[] RSC_BOOT_CONST={0,1,0,0x82204514,0,0x82204510,0,0x82204520,
    0,0x4520,0x4510,0x4514,0,0,0,0,0,0,0x100};
static const u32 requested[] RSC_BOOT_CONST={0x1000000,1,0,0,0,0,0x80000000,0,
    0,0x4520,0x4510,0x4514,0xeaaae5a0,0xe1a1ebab,0xa2e0a581,
    0xecac82e2,0x20edad,0,0x80000001};
#if defined(LMI_GPU_PDC_ENABLE) && !defined(LMI_GPU_RSC_SEQUENCE)
#error PDC enable probe requires the isolated RSC sequence profile
#endif
#ifdef LMI_GPU_PDC_ENABLE
#define PROGRAM_COUNT 8u
static u32 program_index(u32 i) {return i?i+11:0;}
#elif defined(LMI_GPU_RSC_SEQUENCE)
#define PROGRAM_COUNT 6u
static u32 program_index(u32 i) {return i?i+11:0;}
#else
#define PROGRAM_COUNT 19u
static u32 program_index(u32 i) {return i;}
#endif
static int idle(volatile u32 *r,volatile u32 *g) {
    if(rsc_read(g+0x14000/4)!=1 || rsc_read(g+0x14070/4) ||
       rsc_read(g+0x143a0/4) || rsc_read(g+0x24c1c/4) || rsc_read(g+0x24c20/4) ||
       rsc_read(r+0xc/4)!=0x4000000a || (rsc_read(r+0x10/4)&0x10000) ||
       rsc_read(r+0x404/4) || rsc_read(r+0xd04/4))return 0;
    for(u32 slot=0;slot<10;slot++) {
        u32 at=(0xd00+slot*0x2a0)/4;
        if(rsc_read(r+at+0x18/4)!=1 || rsc_read(r+at+0x14/4) ||
           rsc_read(r+at+0x10/4) || rsc_read(r+at+0x1c/4))return 0;
    }
    return 1;
}
/* 0=refused or programming failed but restored;1=all programmed/restored;
 * 2=state/restore uncertain, retain all parent dependencies until reboot. */
int lmi_gpu_rsc_init(void) {
    volatile u32 *r=(volatile u32 *)io_map(0x3de0000,0x10000);
    volatile u32 *g=(volatile u32 *)io_map(0x3d6a000,0x30000);
    volatile u32 *p=(volatile u32 *)io_map(0xb290000,0x10000);
    if(!r || !g || !p || !idle(r,g))return 0;
    u32 saved[19],actual[19],restored[19],written=0,good=1;
    for(u32 i=0;i<19;i++) {
        saved[i]=rsc_read((i<17?r:p)+offsets[i]/4);
        if(saved[i]!=expected[i])return 0;
    }
    log_line("LMI_GPU_RSC_INIT_BEGIN\n");
    for(u32 i=0;i<PROGRAM_COUNT;i++) {
        u32 index=program_index(i);
        volatile u32 *word=(index<17?r:p)+offsets[index]/4;
        rsc_write(word,requested[index]);written++;
        if(rsc_read(word)!=requested[index]) {good=0;break;}
    }
    for(u32 i=0;i<19;i++)actual[i]=rsc_read((i<17?r:p)+offsets[i]/4);
    const char *markers[]={"LMI_GPU_RSC_INIT_BEFORE\n","LMI_GPU_RSC_INIT_ACTUAL\n","LMI_GPU_RSC_INIT_RESTORED\n"};
    for(u32 pass=0;pass<2;pass++) {
        log_line(markers[pass]);
        for(u32 i=0;i<19;i++) {
            u32 address=(i<17?0x3de0000:0xb290000)+offsets[i];
            log_hex(((u64)address<<32)|(pass==0?saved[i]:actual[i]));
        }
    }
    /* Do not tear down a sequencer if any unexpected actor became active. */
    if(!idle(r,g))return 2;
#ifdef LMI_GPU_RSC_PDC_VOTE
    /* All nineteen values must match the isolated profile BEFORE requesting.
     * Hidden addresses/data remain exactly the cold census, not vendor zero. */
    for(u32 i=0;i<19;i++)if(actual[i]!=((i==0 || i>=12)?requested[i]:expected[i]))good=0;
    if(good) {
        extern int lmi_gpu_arc_min_votes(volatile u32 *);
        log_line("LMI_GPU_RSC_PDC_READY\n");
        int voted=lmi_gpu_arc_min_votes(r);
        log_line("LMI_GPU_RPMH_RESULT\n");log_hex(voted);
        if(voted>=2) {log_line("LMI_GPU_RPMH_KEEP_CLOCKS_UNTIL_RESET\n");return 2;}
        if(voted!=1)good=0;
#ifdef LMI_GPU_GMU_200MHZ
        if(voted==1) {
            extern int lmi_gpu_gmu_200mhz_probe(void);
            int clocked=lmi_gpu_gmu_200mhz_probe();
            log_line("LMI_GPU_GMU_200MHZ_RESULT\n");log_hex(clocked);
#ifdef LMI_GPU_GMU_BOOT
            if(clocked==3)return 3;
#endif
            if(clocked==2)return 2;
            if(clocked!=1)good=0;
        }
#endif
        if(!idle(r,g))return 2;
    }
#endif
    for(u32 i=written;i;i--) {
        u32 index=program_index(i-1);
        rsc_write((index<17?r:p)+offsets[index]/4,saved[index]);
    }
    for(u32 i=0;i<19;i++)restored[i]=rsc_read((i<17?r:p)+offsets[i]/4);
    log_line(markers[2]);
    for(u32 i=0;i<19;i++) {
        u32 address=(i<17?0x3de0000:0xb290000)+offsets[i];
        log_hex(((u64)address<<32)|restored[i]);
    }
    for(u32 i=0;i<19;i++)if(restored[i]!=saved[i])return 2;
    if(!idle(r,g))return 2;
    log_line("LMI_GPU_RSC_INIT_RESTORE_OK\n");
    return good?1:0;
}
