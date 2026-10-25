/* Mode30: read-only vendor table preparation, never submits a power request. */
#include "lmi-gpu-table-plan.h"
typedef unsigned long long u64;
#define PLAN __attribute__((noinline,section(".gpu_plan")))
#define DATA __attribute__((section(".gpu_plan_data")))
extern u64 io_map_memory(u64,u64);
extern u64 io_map(u64,u64);
extern void log_line(const char *);
extern void log_hex(u64);
arc_u32 __attribute__((noinline,section(".gpu_page1"))) lmi_gpu_page1(arc_u32 v) {return v^0x65000001;}
arc_u32 __attribute__((noinline,section(".gpu_page2"))) lmi_gpu_page2(arc_u32 v) {return v^0x65000002;}
arc_u32 __attribute__((noinline,section(".gpu_page3"))) lmi_gpu_page3(arc_u32 v) {return v^0x65000003;}
/* ABI: 3 header words + 16 GX descriptors of 3 words + 4 CX of 2. */
_Static_assert(sizeof(struct lmi_gpu_perf_table)==236,"pinned HFI PERF_TBL size");
static int PLAN vote(const struct lmi_arc_resource *pri,const struct lmi_arc_resource *mx,arc_u32 level,arc_u32 *value) {
    arc_u32 k=0,j=0;
    while(k<pri->count && pri->levels[k]<level)k++;
    if(k==pri->count)return 0;
    /* Match vendor setup_volt_dependency_tbl: clamp MX to its highest index. */
    while(j+1<mx->count && mx->levels[j]<pri->levels[k])j++;
    *value=((arc_u32)pri->levels[k]<<16)|(j<<8)|k;return 1;
}
static arc_u32 PLAN plan16(const unsigned char *p) {return p[0]|((arc_u32)p[1]<<8);}
static arc_u32 PLAN plan32(const unsigned char *p) {return plan16(p)|(plan16(p+2)<<16);}
/* BCM addresses only; do not interpret their auxiliary data as ARC levels. */
arc_u32 PLAN lmi_gpu_bcm_address(const void *memory,arc_u32 bytes,const char *id) {
    const unsigned char *db=memory;arc_u32 result=0;
    if(!db || bytes<144 || bytes>0x20000 || plan32(db+4)!=0x0c0330db)return 0;
    for(arc_u32 s=0;s<8;s++) {
        const unsigned char *h=db+8+s*16;
        if(plan16(h)!=5)continue;
        arc_u32 at=144+plan16(h+2),count=plan16(h+6);
        if(count>512 || at>bytes || count*24>bytes-at)return 0;
        for(arc_u32 n=0;n<count;n++) {
            const unsigned char *e=db+at+24*n;arc_u32 equal=1;
            for(arc_u32 k=0;k<8;k++)equal&=e[k]==(unsigned char)id[k];
            if(!equal)continue;
            arc_u32 address=plan32(e+16);
            if(result || !address || (address&3) || ((address>>16)&7)!=5)return 0;
            result=address;
        }
    }
    return result;
}
int PLAN lmi_gpu_prepare_perf(const void *db,arc_u32 bytes,struct lmi_gpu_perf_table *table) {
    struct lmi_arc_resource gx,cx,mx;
    if(!table || !lmi_gpu_arc_parse(db,bytes,"gfx.lvl",&gx) ||
       !lmi_gpu_arc_parse(db,bytes,"cx.lvl\0",&cx) || !lmi_gpu_arc_parse(db,bytes,"mx.lvl\0",&mx) ||
       gx.address==cx.address || gx.address==mx.address || cx.address==mx.address || gx.count<8)return 0;
    static const arc_u32 khz[] DATA={0,305000,400000,441600,490000,525000,587000,670000};
    static const arc_u32 levels[] DATA={0,64,128,144,192,224,256,320};
    struct lmi_gpu_perf_table t={0};t.gx_count=8;t.cx_count=2;
    for(arc_u32 n=0;n<8;n++) {
        t.gx[n][1]=0xffffffff;t.gx[n][2]=khz[n];
        if(!vote(&gx,&mx,levels[n],&t.gx[n][0]))return 0;
    }
    if(!vote(&cx,&mx,0,&t.cx[0][0]) || !vote(&cx,&mx,48,&t.cx[1][0]))return 0;
    t.cx[1][1]=200000;*table=t;return 1;
}
int PLAN lmi_gpu_table_plan(void) {
    volatile unsigned char *fuse=(void *)io_map(0x784000,0x3000);
    if(!fuse)return 0;
    arc_u32 bin=(fuse[0x19b]>>5)&7;
    log_line("LMI_GPU_PLAN_SPEED_BIN\n");log_hex(bin);
    if(bin)return 0; /* This table comes from live DT speed-bin0 only. */
    log_line("LMI_GPU_RX_PAGES\n");
    arc_u32 proof[]={lmi_gpu_page1(0x1badb002),lmi_gpu_page2(0x1badb002),lmi_gpu_page3(0x1badb002)};
    for(arc_u32 n=0;n<3;n++) {log_hex(proof[n]);if(proof[n]!=(0x1badb002^(0x65000001+n)))return 0;}
    struct lmi_gpu_perf_table table;
    const void *db=(void *)io_map_memory(0x80860000,0x20000);
    if(!lmi_gpu_prepare_perf(db,0x20000,&table))return 0;
    const char *ids[]={"gfx.lvl","cx.lvl\0","mx.lvl\0"};
    log_line("LMI_GPU_PLAN_ARCS\n");
    for(arc_u32 n=0;n<3;n++) {
        struct lmi_arc_resource r;if(!lmi_gpu_arc_parse(db,0x20000,ids[n],&r))return 0;
        log_hex(r.address);log_hex(r.count);
        for(arc_u32 k=0;k<16;k++)log_hex(r.levels[k]);
    }
    const char *bus[]={"SH0\0\0\0\0","MC0\0\0\0\0","ACV\0\0\0\0","CN0\0\0\0\0"};
    log_line("LMI_GPU_PLAN_BCM\n");
    for(arc_u32 n=0;n<4;n++) {arc_u32 a=lmi_gpu_bcm_address(db,0x20000,bus[n]);log_hex(a);if(!a)return 0;}
    log_line("LMI_GPU_PERF_PLAN\n");
    const arc_u32 *words=(const arc_u32 *)&table;
    for(arc_u32 n=0;n<59;n++)log_hex(words[n]);
    log_line("LMI_GPU_TABLE_PLAN_VERIFIED\n");return 1;
}
