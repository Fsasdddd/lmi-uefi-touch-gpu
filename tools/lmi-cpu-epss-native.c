/* Replaces only the otherwise disabled redwood CPU/DDR boot helper and its
 * quiesce entry. The old DDR pointer's eight-byte zero BSS slot is exclusively
 * owned here after all references to the old helper unit are audited/replaced.
 * Heap state and device mappings intentionally live until the RAM kernel ends.
 * Native loader_return still stops the other CPUs before this quiesce entry. */
#include "lmi-cpu-epss.h"
extern struct lmi_epss_state *lmi_epss_native_state;
extern int PE_parse_boot_argn(const char *,void *,int);
extern uintptr_t ml_io_map(uintptr_t,size_t);
extern void *IOMallocAligned(size_t,size_t);
extern void bzero(void *,size_t);
extern void lmi_frame_emit(const char *,const uint64_t *,unsigned);
extern void lmi_timing_cleanup(void);
static uintptr_t native_map(void *context,uint32_t physical,uint32_t size)
{(void)context;return ml_io_map(physical,size);}
static int native_read(void *context,uintptr_t base,uint32_t offset,uint32_t *value)
{(void)context;*value=*(volatile uint32_t *)(base+offset);return 1;}
static int native_write(void *context,uintptr_t base,uint32_t offset,uint32_t value)
{(void)context;*(volatile uint32_t *)(base+offset)=value;return 1;}
static void native_barrier(void *context)
{(void)context;__asm__ volatile("dsb sy":::"memory");}
static void status(const char *tag,struct lmi_epss_state *s,int ok)
{
    uint64_t v[6]={(unsigned)ok,s?s->prepared:0,s?s->dirty:0,
        s?s->applied:0,s?s->changed:0,s?s->failed_domain:0};
    lmi_frame_emit(tag,v,6);
}
void lmi_epss_native_init(void)
{
    uint32_t mode=0;
    if(!PE_parse_boot_argn("lmi_cpu",&mode,4) || (mode!=1 && mode!=2))return;
    if(__atomic_load_n(&lmi_epss_native_state,__ATOMIC_ACQUIRE))return;
    struct lmi_epss_state *s=IOMallocAligned(sizeof(*s),16);
    if(!s) {status("LMI_CPU_EPSS_INIT",0,0);return;}
    bzero(s,sizeof(*s));
    __atomic_store_n(&lmi_epss_native_state,s,__ATOMIC_RELEASE);
    struct lmi_epss_io io={0,native_map,native_read,native_write,native_barrier};
    int ready=lmi_epss_prepare(s,&io);
    status("LMI_CPU_EPSS_INIT",s,ready);
    for(unsigned i=0;i<3;i++) {
        struct lmi_epss_domain *d=&s->domain[i];
        if(!d->base)continue; /* Keep mapped LUT evidence even on a refused plan. */
        for(unsigned begin=0;begin<40;begin+=8) {
            uint64_t v[10]={i,begin};
            for(unsigned j=0;j<8;j++)v[j+2]=d->lut[begin+j];
            lmi_frame_emit("LMI_CPU_EPSS_LUT",v,10);
        }
    }
    if(!ready)return;
    int ok=mode==2?lmi_epss_apply(s):1;
    status("LMI_CPU_EPSS_APPLY",s,ok);
    for(unsigned i=0;i<3;i++) {
        struct lmi_epss_domain *d=&s->domain[i];
        uint64_t v[7]={i,d->rows,d->original,d->target,d->khz,d->applied_readback,mode};
        lmi_frame_emit("LMI_CPU_EPSS_REQUEST",v,7);
    }
}
void lmi_epss_native_quiesce(void)
{
    struct lmi_epss_state *s=__atomic_load_n(&lmi_epss_native_state,__ATOMIC_ACQUIRE);
    if(!s)return;
    int ok=0;
    for(unsigned attempt=0;attempt<3 && !ok;attempt++)ok=lmi_epss_restore(s);
    status("LMI_CPU_EPSS_RESTORE",s,ok);
    for(unsigned i=0;i<3;i++) {
        struct lmi_epss_domain *d=&s->domain[i];
        uint64_t v[4]={i,d->original,d->restored_readback,!!(s->dirty&(1u<<i))};
        lmi_frame_emit("LMI_CPU_EPSS_RESTORE_DOMAIN",v,4);
    }
}
/* Checkpoint63 redirects loader_return through the existing display/GPU
 * cleanup rather than native redwood_ddr_quiesce. Keep that entire verified
 * stop/fence/DPU chain, then restore CPU requests before returning to loader. */
void lmi_epss_native_cleanup(void)
{
    lmi_timing_cleanup();
    lmi_epss_native_quiesce();
}
