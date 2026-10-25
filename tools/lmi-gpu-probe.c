/* lmi SM8250/A650 initial inventory. Mode1 has no MMIO writes.
 * Mode2 briefly opens cold CX power and restores its original collapse bit.
 * Mode3 additionally tests crystal-source clock votes and restores them.
 * Mode4 additionally reads CM3 reset and AO counter; no GMU register writes.
 * Mode5 loads volatile TCM and reads it back, with CM3 held in RESET.
 * Mode6 reads SMMU GR0 with reversible bus clocks; no TCM/SMMU writes.
 * No storage writes or firmware execution in any mode.
 * Only GCC, corrected speed fuse, GPUCC while its register clock runs.
 * Never touch dark GX/SMMU or enable the redwood-specific driver.
 */
typedef unsigned int u32;
typedef unsigned long long u64;
extern u64 io_map(u64,u64);
extern int boot_arg(const char *,void *,int);
extern void log_line(const char *);
extern void log_hex(u64);
extern void delay(u32,u32);
extern const unsigned char *image_file(const char *,const char *,u64 *,int *);
extern void *alloc_data(u64);
extern void free_data(void *,u64);
static void field(const char *s,u64 n) { log_line(s);log_hex(n); }
#ifdef LMI_GPU_GMU_ROUTE
#define REFUSED(label,reason) field("LMI_GPU_REFUSED\n",reason)
#else
#define REFUSED(label,reason) log_line(label)
#endif
static int clock_on(u32 value) {
    return !(value&(1u<<31)) || (value&0xf0000000u)==0x20000000u;
}
/* Keep trapped 32-bit MMIO loads independent of their address register.
 * Explicit UXTW also removes stale upper bits from emulated load results. */
static u32 __attribute__((noinline)) smmu_rd32(volatile u32 *address) {
    u64 value;
    __asm__ volatile("ldr %w0, [%1]\n\tuxtw %0, %w0"
        : "=&r"(value) : "r"(address) : "memory");
    return (u32)value;
}
#ifdef LMI_GPU_CONTEXT_PROBE
static void __attribute__((noinline)) smmu_wr32(volatile u32 *address,u32 value) {
    __asm__ volatile("str %w0, [%1]" : "+r"(value) : "r"(address) : "memory");
    __asm__ volatile("dsb sy"::: "memory");
}
/* No streams, translation enable, real table addresses or firmware execution. */
struct kmem_result {int status;u64 address;};
extern struct kmem_result kmem_alloc_tagged(u64,u64,u64,u32,u64,void *);
extern void kmem_free3(u64,u64,u64);
extern u64 pa_of(u64);
extern void clean_cache(u64,u32,int);
extern u64 kernel_map_value,xnu_page_size,g_phys_base,g_phys_size;
extern void *memset(void *,int,u64);
static void cb0_context_probe(volatile u32 *s,u32 table_probe) {
    const u32 offsets[]={0x1800,0x1000,0x8010,0x8030,0x8020,0x8024,0x8028,0x802c,0x8038,0x803c};
    u32 requested[]={1,0x1f300,0x38011,0x803519,0,0,0,0,0xf404ff44,0};
    u32 saved[10],actual[10],restored[10];
    u64 pool=0,root=0;
    if((smmu_rd32(&s[0x8000/4])&1)||smmu_rd32(&s[0x48/4])||
       smmu_rd32(&s[0x8058/4])||smmu_rd32(&s[0x1800/4])) {
        log_line("LMI_GPU_CB0_CONTEXT_REFUSED\n");return;
    }
    for(u32 i=0;i<6;i++)if(smmu_rd32(&s[(0x800+4*i)/4])&(1u<<31)) {
        log_line("LMI_GPU_CB0_CONTEXT_REFUSED\n");return;
    }
    for(u32 i=0;i<10;i++)saved[i]=smmu_rd32(&s[offsets[i]/4]);
    if(table_probe) {
        if(xnu_page_size!=16384 || !kernel_map_value)return;
        struct kmem_result allocation=kmem_alloc_tagged(kernel_map_value,16384,0,0,3,0);
        if(allocation.status || !allocation.address)return;
        pool=allocation.address;root=pa_of(pool);
        if((pool&16383)||(root&4095)||!root||(root>>36)||
           root<g_phys_base||g_phys_size<4096||root-g_phys_base>g_phys_size-4096||
           pa_of(pool+4095)!=root+4095) {kmem_free3(kernel_map_value,pool,16384);return;}
        memset((void *)pool,0,16384);clean_cache(pool,16384,0);
        __asm__ volatile("dsb sy"::: "memory");
        requested[1]=saved[1];requested[4]=(u32)root;requested[5]=(u32)(root>>32);
        field("LMI_GPU_CB0_TABLE_ROOT\n",root);
    }
    log_line("LMI_GPU_CB0_CONTEXT_BEGIN\n");
    for(u32 i=0;i<10;i++)if(!table_probe||i!=1)smmu_wr32(&s[offsets[i]/4],requested[i]);
    for(u32 i=0;i<10;i++)actual[i]=smmu_rd32(&s[offsets[i]/4]);
    /* TCR2 controls TTBR ASID field access: restore it before TTBR halves.
     * Keep the temporary AArch64 format until all CB fields are restored. */
    for(u32 i=2;i<10;i++)smmu_wr32(&s[offsets[i]/4],saved[i]);
    if(!table_probe)smmu_wr32(&s[offsets[1]/4],saved[1]);
    smmu_wr32(&s[offsets[0]/4],saved[0]);
    for(u32 i=0;i<10;i++)restored[i]=smmu_rd32(&s[offsets[i]/4]);
    for(u32 i=0;i<10;i++) {
        field("LMI_GPU_CB0_CONTEXT_OFFSET\n",offsets[i]);
        field("LMI_GPU_CB0_CONTEXT_BEFORE\n",saved[i]);
        field("LMI_GPU_CB0_CONTEXT_REQUESTED\n",requested[i]);
        field("LMI_GPU_CB0_CONTEXT_ACTUAL\n",actual[i]);
        field("LMI_GPU_CB0_CONTEXT_RESTORED\n",restored[i]);
    }
    field("LMI_GPU_CB0_CONTEXT_SCTLR\n",smmu_rd32(&s[0x8000/4]));
    field("LMI_GPU_CB0_CONTEXT_GFSR\n",smmu_rd32(&s[0x48/4]));
    field("LMI_GPU_CB0_CONTEXT_FSR\n",smmu_rd32(&s[0x8058/4]));
    if(pool) {
        u32 safe=1;
        for(u32 i=0;i<10;i++)safe&=saved[i]==restored[i];
        safe&=!(smmu_rd32(&s[0x8000/4])&1);
        if(safe) {kmem_free3(kernel_map_value,pool,16384);log_line("LMI_GPU_CB0_TABLE_FREED\n");}
        else log_line("LMI_GPU_CB0_TABLE_RETAINED\n");
    }
    log_line("LMI_GPU_CB0_CONTEXT_END\n");
}
#endif
#if !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
static void cb0_format_probe(volatile u32 *s) {
    u32 before=smmu_rd32(&s[0x1800/4]);
    if(before || (smmu_rd32(&s[0x8000/4])&1) || smmu_rd32(&s[0x48/4])) {
        log_line("LMI_GPU_CB0_FORMAT_REFUSED\n");return;
    }
    for(int i=0;i<6;i++)if(smmu_rd32(&s[(0x800+4*i)/4])&(1u<<31)) {
        log_line("LMI_GPU_CB0_FORMAT_REFUSED\n");return;
    }
    log_line("LMI_GPU_CB0_FORMAT_BEGIN\n");
    u32 value=before|1u;
    /* Qualcomm HYP emulation requires an actual source register, not WZR. */
    __asm__ volatile("str %w0, [%1]" : "+r"(value) : "r"(&s[0x1800/4]) : "memory");
    __asm__ volatile("dsb sy":::"memory");
    u32 actual=smmu_rd32(&s[0x1800/4]);
    value=before;
    __asm__ volatile("str %w0, [%1]" : "+r"(value) : "r"(&s[0x1800/4]) : "memory");
    __asm__ volatile("dsb sy":::"memory");
    field("LMI_GPU_CB0_FORMAT_BEFORE\n",before);
    field("LMI_GPU_CB0_FORMAT_WRITTEN\n",actual);
    field("LMI_GPU_CB0_FORMAT_RESTORED\n",smmu_rd32(&s[0x1800/4]));
    field("LMI_GPU_CB0_FORMAT_SCTLR\n",smmu_rd32(&s[0x8000/4]));
    field("LMI_GPU_CB0_FORMAT_GFSR\n",smmu_rd32(&s[0x48/4]));
    log_line("LMI_GPU_CB0_FORMAT_END\n");
}
#endif
#ifdef LMI_GPU_RPMH_PROBE
static int rpmh_probe(void) {
    extern int lmi_gpu_arc_min_votes(volatile u32 *);
    volatile u32 *rscc=(volatile u32 *)io_map(0x3de0000,0x10000);
    int voted=lmi_gpu_arc_min_votes(rscc);
    field("LMI_GPU_RPMH_RESULT\n",voted);
    if(voted>=2) {log_line("LMI_GPU_RPMH_KEEP_CLOCKS_UNTIL_RESET\n");return 2;}
    return 0;
}
#endif
static int smmu_readonly(u32 mode) {
    volatile u32 *gcc=(volatile u32 *)io_map(0x100000,0x80000);
    if(!gcc) {REFUSED("LMI_GPU_SMMU_NO_GCC\n",1);return 0;}
    const u32 clocks[]={0x7100c,0x71018};
    u32 saved[2];int ready=1;
    for(int n=0;n<2;n++)saved[n]=gcc[clocks[n]/4]&1;
    log_line("LMI_GPU_SMMU_BEGIN\n");
    for(int n=0;n<2;n++) {
        gcc[clocks[n]/4]=gcc[clocks[n]/4]|1u;
        __asm__ volatile("dsb sy":::"memory");
        for(int k=0;k<200 && !clock_on(gcc[clocks[n]/4]);k++)delay(1,1000);
        field("LMI_GPU_SMMU_CLOCK_OFFSET\n",clocks[n]);
        field("LMI_GPU_SMMU_CLOCK_STATUS\n",gcc[clocks[n]/4]);
        ready=ready && clock_on(gcc[clocks[n]/4]);
    }
    if(ready) {
#if defined(LMI_GPU_RPMH_BUS_PROBE) && !defined(LMI_GPU_RSC_PDC_VOTE)
        /* Same DT clocks as vendor gmu_enable_clks; CM3 remains RESET1.
         * Do not remove these or any parent after a pending transaction. */
        if(rpmh_probe()==2)return 2;
#endif
#ifdef LMI_GPU_RSC_INIT
        extern int lmi_gpu_rsc_init(void);
        int initialized=lmi_gpu_rsc_init();
        field("LMI_GPU_RSC_INIT_RESULT\n",initialized);
        if(initialized>=2)return 2;
#endif
#ifndef LMI_GPU_GMU_ROUTE
        volatile u32 *s=(volatile u32 *)io_map(0x3da0000,0x10000);
        if(s) {
            const u32 offsets[]={0x20,0x24,0x28,0x3c,0,0x48};
            u32 id0=0,id1=0;
            for(int n=0;n<6;n++) {
                field("LMI_GPU_SMMU_READ_ADDRESS\n",0x3da0000+offsets[n]);
                u32 value=smmu_rd32(&s[offsets[n]/4]);
                field("LMI_GPU_SMMU_VALUE\n",value);
                if(n==0)id0=value;
                if(n==1)id1=value;
            }
            u32 page=(id1&(1u<<31))?65536:4096;
            u32 global=page*(1u<<(((id1>>28)&7)+1));
            u32 nr=id0&255,cb=id1&255;
            /* GR0 census; mode8 additionally snapshots the CB0 candidate. */
            if(id0 && id0!=~0u && (id0&(1u<<27)) && nr && nr<=128 &&
               cb && ((id1>>16)&255)<=cb && global+cb*page<=0x10000) {
                u32 valid=0;
                for(u32 i=0;i<nr;i++) {
                    field("LMI_GPU_SMMU_STREAM_INDEX\n",i);
                    u32 smr=smmu_rd32(&s[(0x800+4*i)/4]);valid|=smr>>31;
                    field("LMI_GPU_SMMU_SMR\n",smr);
                    field("LMI_GPU_SMMU_S2CR\n",smmu_rd32(&s[(0xc00+4*i)/4]));
                }
                log_line("LMI_GPU_SMMU_STREAMS_END\n");
                /* Vendor nonstatic first-free candidate only. This is a
                 * finite read-only snapshot, never a context ownership grant. */
                if(mode==8 || mode==9 || mode==10 || mode==11 || (mode>=12 && mode<=24)) {
                    if(valid || (id0&(1u<<8)) || (smmu_rd32(&s[0])&(1u<<3)) ||
                       page!=4096 || global!=0x8000 || cb!=5) {
                        log_line("LMI_GPU_CB0_REFUSED_LAYOUT\n");
                    } else {
                        const u32 cbregs[]={0x1000,0x1800,0x8000,
                            0x8010,0x8020,0x8024,0x8028,0x802c,
                            0x8030,0x8034,0x8038,0x803c,0x8058,0x8060,0x8064};
                        log_line("LMI_GPU_CB0_BEGIN\n");
                        u32 first[15],changed=0;
                        for(u32 pass=0;pass<3;pass++) {
                            if(pass)delay(1000,1000);
                            field("LMI_GPU_CB0_SNAPSHOT\n",pass);
                            for(u32 n=0;n<sizeof(cbregs)/sizeof(cbregs[0]);n++) {
                                field("LMI_GPU_CB0_READ_ADDRESS\n",0x3da0000+cbregs[n]);
                                u32 value=smmu_rd32(&s[cbregs[n]/4]);
                                if(!pass)first[n]=value;
                                else changed+=(value!=first[n]);
                                field("LMI_GPU_CB0_VALUE\n",value);
                            }
                        }
                        field("LMI_GPU_CB0_CHANGED_READS\n",changed);
                        log_line("LMI_GPU_CB0_END\n");
#ifdef LMI_GPU_WIRED_CONTEXT
                        if((mode>=12 && mode<=24) && !changed) {
                            extern void lmi_gpu_ram_use(int (*)(u64,void *),void *);
                            extern int lmi_gmu_root_probe(u64,void *);
                            lmi_gpu_ram_use(lmi_gmu_root_probe,(void *)s);
                        }
#elif !defined(LMI_GPU_RSC_PDC_VOTE)
                        if(mode==9 && !changed)cb0_format_probe(s);
#endif
#ifdef LMI_GPU_CONTEXT_PROBE
                        if((mode==10 || mode==11) && !changed)cb0_context_probe(s,mode==11);
#endif
                    }
                }
            } else log_line("LMI_GPU_SMMU_LAYOUT_REFUSED\n");
        } else log_line("LMI_GPU_SMMU_MAP_FAILED\n");
#endif
    } else REFUSED("LMI_GPU_SMMU_CLOCK_REFUSED\n",4);
    for(int n=1;n>=0;n--) {
        gcc[clocks[n]/4]=(gcc[clocks[n]/4]&~1u)|saved[n];
        __asm__ volatile("dsb sy":::"memory");
        delay(10,1000);
        if(n==1 && !saved[n]) {
            for(int k=0;k<200 && !(gcc[clocks[n]/4]&(1u<<31));k++)delay(1,1000);
        }
        field("LMI_GPU_SMMU_RESTORE_OFFSET\n",clocks[n]);
        field("LMI_GPU_SMMU_RESTORE_EXPECTED\n",saved[n]);
        field("LMI_GPU_SMMU_RESTORE_ACTUAL\n",gcc[clocks[n]/4]&1);
        field("LMI_GPU_SMMU_RESTORE_STATUS\n",gcc[clocks[n]/4]);
    }
    log_line("LMI_GPU_SMMU_END\n");
    return 0;
}
#if !defined(LMI_GPU_CONTEXT_PROBE) && !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
static void tcm_load(volatile u32 *gmu) {
    u64 size=0;int disk=-1;
    const unsigned char *fw=image_file("fw","a650_gmu.bin",&size,&disk);
    if(!fw || size!=41548 || gmu[0x14000/4]!=1) {
        log_line("LMI_GPU_TCM_REFUSED\n");return;
    }
    u32 crc=~0u;
    for(u64 n=0;n<size;n++) {
        crc^=fw[n];
        for(int k=0;k<8;k++)crc=(crc>>1)^((0u-(crc&1))&0xedb88320u);
    }
    if((~crc)!=0x5c66275c) {log_line("LMI_GPU_TCM_BAD_CRC\n");return;}
    struct block {u32 off,length;const u32 *data;} blocks[5];
    u32 count=0,total=0,wrong=0,restore_wrong=0;
    /* Parse the entire pinned file before allocation or TCM writes. */
    for(u64 at=0;at<size;) {
            if(size-at<16) {log_line("LMI_GPU_TCM_BAD_HEADER\n");return;}
            const u32 *h=(const u32 *)(fw+at);
            u32 addr=h[0],length=h[1];at+=16;
            if(length>size-at || (length&3)) {
                log_line("LMI_GPU_TCM_BAD_SIZE\n");return;
            }
            u32 off=0;
            if(addr<0x4000 && length<=0x4000-addr)off=0x3000+addr;
            else if(addr>=0x10004000 && addr<0x10008000 && length<=0x10008000-addr)
                off=0x7000+addr-0x10004000;
            if(length && off) {
                if(addr&3) {log_line("LMI_GPU_TCM_BAD_ALIGN\n");return;}
                if(count==5) {log_line("LMI_GPU_TCM_LAYOUT_MISMATCH\n");return;}
                blocks[count++]=(struct block){off,length,(const u32 *)(fw+at)};
                total+=length;
            } else if(length && !((addr==0x4000 && length==21968) || (addr==0x157000 && length==920))) {
                log_line("LMI_GPU_TCM_UNKNOWN_EXTERNAL\n");return;
            }
            at+=length;
    }
    if(count!=5 || total!=18404) {log_line("LMI_GPU_TCM_LAYOUT_MISMATCH\n");return;}
    u32 *saved=alloc_data(total);
    if(!saved) {log_line("LMI_GPU_TCM_NO_SNAPSHOT\n");return;}
    if(gmu[0x14000/4]!=1) {free_data(saved,total);log_line("LMI_GPU_TCM_REFUSED\n");return;}
    log_line("LMI_GPU_TCM_BEGIN\n");
    field("LMI_GPU_TCM_DISK\n",(u32)disk);
    field("LMI_GPU_TCM_FIRMWARE_CRC\n",~crc);
    /* Snapshot all words before changing any, then write/verify/restore/verify.
     * No failure exit between the first write and complete restoration. */
    for(int pass=0;pass<5;pass++) {
        u32 cursor=0;
        for(u32 b=0;b<count;b++) {
            struct block *v=&blocks[b];
            if(pass==1)field("LMI_GPU_TCM_BLOCK_OFFSET\n",v->off);
            for(u32 n=0;n<v->length/4;n++,cursor++) {
                volatile u32 *word=&gmu[v->off/4+n];
                if(pass==0)saved[cursor]=*word;
                else if(pass==1)*word=v->data[n];
                else if(pass==2)wrong+=(*word!=v->data[n]);
                else if(pass==3)*word=saved[cursor];
                else restore_wrong+=(*word!=saved[cursor]);
            }
        }
        __asm__ volatile("dsb sy":::"memory");
    }
    free_data(saved,total);
    field("LMI_GPU_TCM_BYTES\n",total);
    field("LMI_GPU_TCM_MISMATCHES\n",wrong);
    field("LMI_GPU_TCM_RESTORE_MISMATCHES\n",restore_wrong);
    field("LMI_GPU_TCM_RESET_AFTER\n",gmu[0x14000/4]);
    log_line("LMI_GPU_TCM_END\n");
}
/* kona GPUCC: use the existing crystal source only. No PLL/RCG change,
 * no GMU register access and no firmware/CP execution. Restore all votes. */
#endif
#if defined(LMI_GPU_RSCC_READONLY) && !defined(LMI_GPU_RPMH_PROBE) && !defined(LMI_GPU_RSC_INIT)
/* lmi live DT kgsl-3d0 reg-name rscc, 03de0000/10000.
 * Vendor
 * a6xx_reg.h word346 is TCS0 STATUS, i.e. d00+18 in bytes.
 * Read only while CM3 RESET1 and CX/AHB clocks are held by the caller.
 * This census establishes accessibility, not ownership or active rail level. */
static void rscc_readonly(void) {
    volatile u32 *r=(volatile u32 *)io_map(0x3de0000,0x10000);
    if(!r)return;
    const u32 common[]={0xc,0x10,0x2c,0x404,0xd00,0xd04};
    log_line("LMI_GPU_RSCC_BEGIN\n");
    for(u32 i=0;i<6;i++) {
        field("LMI_GPU_RSCC_READ_OFFSET\n",common[i]);
        field("LMI_GPU_RSCC_VALUE\n",smmu_rd32(&r[common[i]/4]));
    }
    u32 config=smmu_rd32(&r[3]);
    /* Actual lmi DRV0 config4000000a: ten TCS, eight commands/TCS.
     * Do not reuse the alioth census's four-slot/16-command assumption.
     * All reads below are within the live DT's64KiB register resource. */
    if(config!=0x4000000a) {
        log_line("LMI_GPU_RSCC_LAYOUT_REFUSED\n");return;
    }
    const u32 offsets[]={0x10,0x14,0x18,0x1c,0x30,0x34,0x38,0x3c,0x40,0x44,0x48,0x4c,0x50,0x54};
    for(u32 slot=0;slot<10;slot++) {
        field("LMI_GPU_RSCC_SLOT\n",slot);
        for(u32 i=0;i<14;i++) {
            u32 at=0xd00+slot*0x2a0+offsets[i];
            field("LMI_GPU_RSCC_READ_OFFSET\n",at);
            field("LMI_GPU_RSCC_VALUE\n",smmu_rd32(&r[at/4]));
        }
    }
    log_line("LMI_GPU_RSCC_READONLY_OK\n");
}
#endif
#ifdef LMI_GPU_RSC_STATE
/* Source-defined metadata only: lmi GPUCC, GMU/RSC, GPU PDC config and
 * the 64-byte QMP descriptor. Never read a QMP message or ring its doorbell.
 * Caller holds cold CX/crystal clocks; firmware must still be in reset. */
static int rsc_state_bank(u32 base,u32 size,const u32 *offsets,u32 count) {
    field("LMI_GPU_RSC_STATE_BANK\n",base);
    volatile u32 *r=(volatile u32 *)io_map(base,size);
    if(!r)return 0;
    for(u32 i=0;i<count;i++) {
        field("LMI_GPU_RSC_STATE_ADDRESS\n",base+offsets[i]);
        field("LMI_GPU_RSC_STATE_VALUE\n",smmu_rd32(&r[offsets[i]/4]));
    }
    return 1;
}
static void rsc_state(volatile u32 *gmu) {
    if(smmu_rd32(&gmu[0x14000/4])!=1 || smmu_rd32(&gmu[0x14070/4])) {
        log_line("LMI_GPU_RSC_STATE_RESET_REFUSED\n");return;
    }
    const u32 cc[]={0x1000,0x1004,0x1068,0x1078,0x1088,0x108c,
        0x1090,0x1098,0x109c,0x111c,0x1120,0x1124,0x1540};
    const u32 gm[]={0x14000,0x14070,0x143a0,0x143b0,0x24c1c,0x24c20};
    const u32 rs[]={0xc,0x10,0x20,0x24,0x28,0x2c,0x34,0x38,
        0x3c,0x40,0x44,0x48,0x400,0x404,0x600,0x604,0x608,0x60c,0x610};
    const u32 pd[]={0x4500,0x4520};
    const u32 qp[]={0,4,8,12,16,20,24,28,32,36,40,44,48,52,56,60};
    log_line("LMI_GPU_RSC_STATE_BEGIN\n");
    if(!rsc_state_bank(0x3d90000,0x9000,cc,13) ||
       !rsc_state_bank(0x3d6a000,0x30000,gm,6) ||
       !rsc_state_bank(0x3de0000,0x10000,rs,19) ||
       !rsc_state_bank(0xb290000,0x10000,pd,2) ||
       !rsc_state_bank(0xc300000,0x1000,qp,16)) {
        log_line("LMI_GPU_RSC_STATE_MAP_FAILED\n");return;
    }
    log_line("LMI_GPU_RSC_STATE_OK\n");
}
#endif
static int gmu_readonly(u32 mode) {
    volatile u32 *gmu=(volatile u32 *)io_map(0x3d6a000,0x30000);
    if(!gmu) {REFUSED("LMI_GPU_GMU_MAP_FAILED\n",5);return 0;}
    log_line("LMI_GPU_GMU_BEGIN\n");
#if !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
    field("LMI_GPU_GMU_READ_ADDRESS\n",0x3d7e000);
#endif
    field("LMI_GPU_GMU_SYSRESET\n",gmu[0x14000/4]);
#if !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
    field("LMI_GPU_GMU_READ_ADDRESS\n",0x3d7e220);
#endif
#ifndef LMI_GPU_RPMH_PROBE
    u64 start,end,freq;
    __asm__ volatile("isb; mrs %0, cntvct_el0":"=r"(start));
    u32 before=gmu[0x14220/4];
    delay(10000,1000);
    u32 after=gmu[0x14220/4];
    __asm__ volatile("isb; mrs %0, cntvct_el0":"=r"(end));
    __asm__ volatile("mrs %0, cntfrq_el0":"=r"(freq));
#if !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
    field("LMI_GPU_GMU_COUNTER_BEFORE\n",before);
    field("LMI_GPU_GMU_COUNTER_AFTER\n",after);
#endif
    field("LMI_GPU_GMU_COUNTER_DELTA\n",(u32)(after-before));
    field("LMI_GPU_GMU_CPU_TICKS\n",end-start);
    field("LMI_GPU_GMU_CPU_HZ\n",freq);
#endif
    log_line("LMI_GPU_GMU_END\n");
#if defined(LMI_GPU_RPMH_PROBE) && !defined(LMI_GPU_RPMH_BUS_PROBE)
    if((mode>=16 && mode<=20) && gmu[0x14000/4]==1)
        if(rpmh_probe()==2)return 2;
#elif defined(LMI_GPU_RSCC_READONLY) && !defined(LMI_GPU_RPMH_PROBE) && !defined(LMI_GPU_RSC_INIT)
    if((mode==15 || mode==21) && gmu[0x14000/4]==1)rscc_readonly();
#ifdef LMI_GPU_RSC_STATE
    if(mode==21)rsc_state(gmu);
#endif
#endif
    #if !defined(LMI_GPU_CONTEXT_PROBE) && !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
    if(mode==5)tcm_load(gmu);
#endif
    if(mode==6 || mode==8 || mode==9 || mode==10 || mode==11 || (mode>=12 && mode<=46)) {
        if(gmu[0x14000/4]==1) {if(smmu_readonly(mode)==2)return 2;}
        else REFUSED("LMI_GPU_SMMU_RESET_REFUSED\n",7);
    }
    return 0;
}
static int clock_probe(volatile u32 *cc,u32 mode) {
    const u32 offsets[]={0x1078,0x109c,0x1098};
    u32 saved[3];
    if((cc[0x1124/4]&0x371f)!=1 || (cc[0x1120/4]&1)) {
        REFUSED("LMI_GPU_CLOCK_REFUSED_SOURCE\n",8);return 0;
    }
    log_line("LMI_GPU_CLOCK_BEGIN\n");
    field("LMI_GPU_CLOCK_SOURCE\n",cc[0x1124/4]);
    for(int n=0;n<3;n++)saved[n]=cc[offsets[n]/4]&1;
    for(int n=0;n<3;n++) {
        cc[offsets[n]/4]=cc[offsets[n]/4]|1u;
        __asm__ volatile("dsb sy":::"memory");
        delay(10,1000); /* critical AHB uses BRANCH_HALT_DELAY */
        for(int k=0;k<100;k++) {
            if(n==0 || !(cc[offsets[n]/4]&(1u<<31)))break;
            delay(100,1000);
        }
        field("LMI_GPU_CLOCK_OFFSET\n",offsets[n]);
        field("LMI_GPU_CLOCK_STATUS\n",cc[offsets[n]/4]);
    }
    if(mode>=4 && !((cc[0x109c/4]|cc[0x1098/4])&(1u<<31)))
        if(gmu_readonly(mode)==2)return 2;
    for(int n=2;n>=0;n--) {
        cc[offsets[n]/4]=(cc[offsets[n]/4]&~1u)|saved[n];
        __asm__ volatile("dsb sy":::"memory");
        delay(10,1000);
        field("LMI_GPU_CLOCK_RESTORE_OFFSET\n",offsets[n]);
        field("LMI_GPU_CLOCK_RESTORE_EXPECTED\n",saved[n]&1);
        field("LMI_GPU_CLOCK_RESTORE_ACTUAL\n",cc[offsets[n]/4]&1);
    }
    log_line("LMI_GPU_CLOCK_END\n");
    return 0;
}
void lmi_gpu_probe(void) {
    u32 mode=0;
#if defined(LMI_GPU_RAM_PLAN) && !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_GMU_ROUTE)
    extern void lmi_gpu_ram_plan(void);
    if(boot_arg("lmi_gpu",&mode,4) && mode==7)lmi_gpu_ram_plan();
#else
#ifdef LMI_GPU_WIRED_CONTEXT
#if defined(LMI_GPU_RPMH_PROBE)
#if defined(LMI_GPU_RPMH_ARC_SLOT_PROBE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=20)return;
#elif defined(LMI_GPU_RPMH_BUS_PROBE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=19)return;
#elif defined(LMI_GPU_RPMH_INTERFACE_PROBE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=18)return;
#elif defined(LMI_GPU_RSCC_SDE_PROBE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=17)return;
#else
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=16)return;
#endif
    /* The voltage wrapper re-parses and validates both resources before
     * requesting them. Full read-only AUX census is retained in mode14/15. */
#elif defined(LMI_GPU_RSCC_READONLY)
#ifdef LMI_GPU_RSC_INIT
#ifdef LMI_GPU_PDC_ENABLE
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=24)return;
#elif defined(LMI_GPU_RSC_SEQUENCE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=23)return;
#else
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=22)return;
#endif
#elif defined(LMI_GPU_RSC_STATE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=21)return;
#else
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=15)return;
#endif
    extern int lmi_gpu_arc_inventory(void);
    if(!lmi_gpu_arc_inventory())return;
#elif defined(LMI_GPU_ARC_INVENTORY)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=14)return;
    extern int lmi_gpu_arc_inventory(void);
    if(!lmi_gpu_arc_inventory())return;
#elif defined(LMI_GPU_STAGE1_INIT)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=13)return;
#else
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=12)return;
#endif
#else
#ifdef LMI_GPU_RSC_PDC_VOTE
#ifdef LMI_GPU_UNSECURE
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=46)return;
#elif defined(LMI_GPU_ZAP_LOAD)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=45)return;
#elif defined(LMI_GPU_ZAP_METADATA)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=44)return;
#elif defined(LMI_GPU_SCM_QUERY)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=43)return;
#elif defined(LMI_GPU_CP_CONFIG_READY)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=42)return;
#elif defined(LMI_GPU_CP_CONFIG_PLAN)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=41)return;
#elif defined(LMI_GPU_FAL_VETO)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=40)return;
#elif defined(LMI_GPU_CORE_ACCESS)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=39)return;
#elif defined(LMI_GPU_CP_SP_CLOCK)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=38)return;
#elif defined(LMI_GPU_CP_FENCE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=37)return;
#elif defined(LMI_GPU_CP)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=36)return;
#elif defined(LMI_GPU_CORE_MEMORY)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=35)return;
#elif defined(LMI_GPU_CP_PLAN)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=34)return;
#elif defined(LMI_GPU_GX)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=33)return;
#elif defined(LMI_GPU_HFI_CORE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=32)return;
#elif defined(LMI_GPU_HFI_PERF)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=31)return;
#elif defined(LMI_GPU_TABLE_PLAN)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=30)return;
#elif defined(LMI_GPU_HFI_IO)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=29)return;
#elif defined(LMI_GPU_GMU_BOOT)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=28)return;
#elif defined(LMI_GPU_GMU_ROUTE)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=27)return;
#elif defined(LMI_GPU_GMU_200MHZ)
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=26)return;
#else
    if(!boot_arg("lmi_gpu",&mode,4) || mode!=25)return;
#endif
#else
    if(!boot_arg("lmi_gpu",&mode,4) || mode<1 || mode>11 || mode==7)return;
#endif
#endif
#if !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
    log_line("LMI_GPU_READONLY_BEGIN\n");
#endif
    volatile u32 *gcc=(volatile u32 *)io_map(0x100000,0x80000);
    if(!gcc) {REFUSED("LMI_GPU_NO_GCC_MAP\n",6);return;}
#if !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
    const u32 offsets[]={0x52000,0x71004,0x7100c,0x71018,0x71154};
    for(int n=0;n<5;n++) {
        field("LMI_GPU_GCC_OFFSET\n",offsets[n]);
        field("LMI_GPU_GCC_VALUE\n",gcc[offsets[n]/4]);
    }
    volatile unsigned char *fuse=(volatile unsigned char *)io_map(0x784000,0x1000);
    if(fuse)field("LMI_GPU_SPEED_BIN\n",(fuse[0x19b]>>5)&7);
#endif
    if(gcc[0x71004/4]&(1u<<31)) {
        REFUSED("LMI_GPU_GPUCC_CLOCK_OFF_SKIP\n",2);
    } else {
        volatile u32 *gpucc=(volatile u32 *)io_map(0x3d90000,0x9000);
        if(gpucc) {
            /* gpucc-sm8250.c, no SC7280 hub clock offsets. */
#if !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
            const u32 cc[]={0,4,0x100,0x104,0x1004,0x1008,0x100c,
                0x1064,0x106c,0x1078,0x1098,0x109c,0x1120,0x1124,0x5000};
            for(int n=0;n<15;n++) {
                field("LMI_GPU_GPUCC_OFFSET\n",cc[n]);
                field("LMI_GPU_GPUCC_VALUE\n",gpucc[cc[n]/4]);
            }
#endif
            if(mode>=2) {
                u32 original=gpucc[0x106c/4];
                /* Only cold, software-controlled CX; no takeover of live GPU. */
                if((original&3)!=1 || (original&(1u<<31)) ||
                    (gpucc[0x100c/4]&(1u<<31))) {
                    REFUSED("LMI_GPU_CX_REFUSED_STATE\n",3);
                } else {
                    log_line("LMI_GPU_CX_POWER_BEGIN\n");
                    gpucc[0x106c/4]=original&~1u;
                    __asm__ volatile("dsb sy":::"memory");
                    for(int n=0;n<500;n++) {
                        if((gpucc[0x106c/4]|gpucc[0x1540/4])&(1u<<31))break;
                        delay(100,1000);
                    }
                    field("LMI_GPU_CX_POWER_STATUS\n",gpucc[0x106c/4]);
                    field("LMI_GPU_CX_HW_STATUS\n",gpucc[0x1540/4]);
                    if(mode>=3 && ((gpucc[0x106c/4]|gpucc[0x1540/4])&(1u<<31)))
                        if(clock_probe(gpucc,mode)==2)return;
                    /* Clock votes restored; no SMMU, GMU firmware or CP started. */
                    gpucc[0x106c/4]=original;
                    __asm__ volatile("dsb sy":::"memory");
                    for(int n=0;n<500;n++) {
                        if(!((gpucc[0x106c/4]|gpucc[0x1540/4])&(1u<<31)))break;
                        delay(100,1000);
                    }
                    field("LMI_GPU_CX_RESTORED_STATUS\n",gpucc[0x106c/4]);
                    field("LMI_GPU_CX_RESTORED_HW\n",gpucc[0x1540/4]);
                    log_line("LMI_GPU_CX_POWER_END\n");
                }
            }
        }
    }
#if !defined(LMI_GPU_WIRED_CONTEXT) && !defined(LMI_GPU_RSC_PDC_VOTE)
    log_line("LMI_GPU_READONLY_END\n");
#endif
#endif
}
