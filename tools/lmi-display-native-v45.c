/* Automatic spatial-pattern probe only. Desktop show is forwarded to the
 * frozen compositor AFTER verified restoration; this is not desktop scanout.
 * Native services never free owned memory during the kernel's RAM lifetime. */
#include "lmi-display-probe.h"
#define RO __attribute__((section("__TEXT_EXEC,__lmi_ro")))
#define FN static LMI_PIPE_CODE
extern uintptr_t ml_io_map(uintptr_t,size_t);
extern void *IOMallocAligned(size_t,size_t);
extern uint64_t kvtophys(uintptr_t);
extern void bzero(void *,size_t);
extern void delay(unsigned);
extern int snprintf(char *,size_t,const char *,...);
extern void loader_log_line(const char *);
extern void lmi_dpu_original_show(void *,const unsigned char *,void **);
extern volatile const uint32_t *volatile display_map;
extern volatile unsigned long display_samples;
extern volatile struct lmi_native_state {
    struct lmi_display_probe *probe;
    unsigned stopping,restoring,attempted,done;
} state;
struct native_context {
    struct lmi_display_probe probe;
    volatile uint32_t *map[2];
    /* Retain the exact reads immediately preceding a refusal. Logging after
     * failure must not replace these with a later snapshot of live hardware. */
    uint32_t previous_key,previous_value,last_key,last_value;
    uintptr_t allocation,translated;
    size_t allocation_bytes;
    uint64_t physical_address;

};
struct lmi_dpu_snapshot {uint32_t mux,sync,autorefresh,frame,transfer_line,ctl_start,ctl_flush,source_address,source_stride;};
/* Preserve old extension symbol names. This aligned entry starts the sole RX
 * page; subsequent functions/constants must fit inside that existing page. */
LMI_PIPE_CODE __attribute__((aligned(16384))) int
lmi_dpu_read_snapshot(volatile const uint32_t *mdss,struct lmi_dpu_snapshot *out)
{
    if(!mdss || !out)return 0;
    out->mux=mdss[0x6ba5c/4];out->sync=mdss[0x6ba88/4];out->autorefresh=mdss[0x6bab4/4];
    out->frame=mdss[0x6b8ac/4];out->transfer_line=mdss[0x6bab0/4];out->ctl_start=mdss[0x201c/4];
    out->ctl_flush=mdss[0x2018/4];out->source_address=mdss[0x5014/4];out->source_stride=mdss[0x5024/4];return 1;
}
static const char display_entry[] RO="LMI_DPU_PROBE_BEGIN automatic=1 desktop_pipeline=0\n";
static const char display_format[] RO="LMI_DPU_PROBE stage=%u ok=%u expected=%x actual=%x ticks=%llu\n";
static const char returned[] RO="LMI_DPU_PROBE_RETURN restored=1\n";
static const char retained[] RO="LMI_DPU_PROBE_RETURN restored=0 retained=1\n";
static const char display_map_failure[] RO="LMI_DPU_PROBE_REFUSED native-service-preflight\n";
static const char debug_format[] RO="LMI_DPU_PROBE_STATE flags=%x frame=%u line=%u done=%x source=%x auto=%x sync=%x cb=%x fsr=%x global=%x\n";
static const char evidence_format[] RO="LMI_DPU_PREFLIGHT kind=%u key=%llx value=%llx\n";
FN void evidence(unsigned kind,uint64_t key,uint64_t value)
{
    char text[128];
    snprintf(text,sizeof(text),evidence_format,kind,(unsigned long long)key,(unsigned long long)value);
    loader_log_line(text);
}
FN int stopping(void *opaque)
{(void)opaque;return __atomic_load_n(&state.stopping,__ATOMIC_ACQUIRE)!=0;}
FN uint64_t irq_off(void)
{uint64_t flags;__asm__ volatile("mrs %0, daif\nmsr daifset, #3":"=r"(flags)::"memory");return flags;}
FN void irq_restore(uint64_t flags) {__asm__ volatile("msr daif, %0"::"r"(flags):"memory");}
FN int enter(void *opaque,uint64_t *flags)
{
    (void)opaque;*flags=irq_off();
    if(stopping(0) && !state.restoring) {irq_restore(*flags);return 0;}
    return 1;
}
FN void leave(void *opaque,uint64_t flags) {(void)opaque;irq_restore(flags);}
FN uint32_t read_mmio(void *opaque,unsigned space,uint32_t offset)
{
    struct native_context *c=opaque;
    uint32_t value=c->map[space][offset/4];__asm__ volatile("dsb sy":::"memory");
    c->previous_key=c->last_key;c->previous_value=c->last_value;
    c->last_key=(space<<24)|offset;c->last_value=value;return value;
}
FN void write_mmio(void *opaque,unsigned space,uint32_t offset,uint32_t value)
{
    struct native_context *c=opaque;
    c->map[space][offset/4]=value;__asm__ volatile("dsb sy":::"memory");
}
FN uintptr_t allocate(void *opaque,size_t bytes,size_t alignment)
{
    struct native_context *c=opaque;if(stopping(0))return 0;
    c->allocation_bytes=bytes;
    c->allocation=(uintptr_t)IOMallocAligned(bytes,alignment);return c->allocation;
}
FN uint64_t physical(void *opaque,uintptr_t address)
{
    struct native_context *c=opaque;c->translated=address;
    c->physical_address=kvtophys(address);return c->physical_address;
}
FN void clean(void *opaque,uintptr_t address,size_t bytes)
{
    (void)opaque;
    for(uintptr_t line=address&~63ull;line<address+bytes;line+=64)
        __asm__ volatile("dc civac, %0"::"r"(line):"memory");
    __asm__ volatile("dsb sy":::"memory");
}
FN uint64_t ticks(void *opaque)
{(void)opaque;uint64_t n;__asm__ volatile("isb\nmrs %0, cntvct_el0":"=r"(n)::"memory");return n;}
FN void pause_us(void *opaque,unsigned us) {(void)opaque;delay(us);}
FN void report(void *opaque,unsigned stage,int ok,uint32_t expected,uint32_t actual,uint64_t elapsed)
{
    struct native_context *c=opaque;char text[192];
    if(stage==2 && !ok) {
        evidence(0,c->previous_key,c->previous_value);
        evidence(1,c->last_key,c->last_value);
        evidence(2,c->allocation_bytes,c->allocation);
        evidence(3,c->translated,c->physical_address);
        evidence(4,c->probe.dma.pages,c->probe.dma.tables);
    }
    snprintf(text,sizeof(text),display_format,stage,(unsigned)ok,expected,actual,(unsigned long long)elapsed);loader_log_line(text);
    uint64_t flags;
    if(!ok && enter(c,&flags)) {
        struct lmi_display_dma *d=&c->probe.dma;
        unsigned journal=(unsigned)d->journal|((unsigned)d->manual<<1)|((unsigned)d->mapped<<2)|
            ((unsigned)d->mapping_ready<<3)|((unsigned)d->source_owned<<4)|((unsigned)d->pending<<5)|
            ((unsigned)d->prepared<<6)|((unsigned)d->restoring<<7)|((unsigned)d->restored<<8)|((unsigned)d->allocated<<9);
        uint32_t frame=read_mmio(c,0,0x6b8ac),line=read_mmio(c,0,0x6bab0),done=read_mmio(c,0,0x1014);
        uint32_t source=read_mmio(c,0,0x5014),auto_value=read_mmio(c,0,0x6bab4),sync=read_mmio(c,0,0x6ba88);
        uint32_t cb=read_mmio(c,1,0x84000),fsr=read_mmio(c,1,0x84058),global=read_mmio(c,1,0x48);
        leave(c,flags);
        snprintf(text,sizeof(text),debug_format,journal,frame,line,done,source,auto_value,sync,cb,fsr,global);loader_log_line(text);
    }
}
FN struct lmi_display_probe *create(void)
{
    uint64_t hz,ctr;__asm__ volatile("mrs %0, cntfrq_el0":"=r"(hz));__asm__ volatile("mrs %0, ctr_el0":"=r"(ctr));
    if(hz!=19200000 || ((ctr>>16)&15)!=4 || stopping(0))return 0;
    struct native_context *c=IOMallocAligned(sizeof(*c),16384);if(!c)return 0;
    bzero(c,sizeof(*c));
    c->map[0]=(volatile uint32_t *)ml_io_map(0xae00000,0x84000);
    c->map[1]=(volatile uint32_t *)ml_io_map(0x15000000,0x100000);
    if(!c->map[0] || !c->map[1] || stopping(0))return 0;
    c->probe.dma.io=(struct lmi_dma_services){c,read_mmio,write_mmio,enter,leave,allocate,physical,clean,ticks,pause_us};
    c->probe.opaque=c;c->probe.stopping=stopping;c->probe.report=report;
    display_map=c->map[0];return &c->probe;
}
LMI_PIPE_CODE void lmi_dpu_observe_show(void *self,const unsigned char *swap,void **surfaces)
{
    if(stopping(0))return;
    display_samples++;
    if(!state.attempted) {
        state.attempted=1;loader_log_line(display_entry);
        struct lmi_display_probe *p=create();
        /* Publish the zeroed journal before any hardware ownership begins. */
        if(p) {
            __atomic_store_n(&state.probe,p,__ATOMIC_RELEASE);
            (void)lmi_display_probe_run(p);state.done=p->restore_ok;
        } else {state.done=1;loader_log_line(display_map_failure);}
    }
    if(!stopping(0) && state.done)lmi_dpu_original_show(self,swap,surfaces);
}
LMI_PIPE_CODE void lmi_display_smp_prepare(void)
{
    __atomic_store_n(&state.stopping,1,__ATOMIC_RELEASE);
    /* Preserve the exact native OFF verification, including its unknown-state
     * loop. Only AFTER it returns may this CPU bypass the transaction gate. */
    ((void (*)(void))0xfffffff00745a818ull)();
    state.restoring=1;
    struct lmi_display_probe *p=__atomic_load_n(&state.probe,__ATOMIC_ACQUIRE);
    int ok=!p || lmi_dma_restore(&p->dma);
    loader_log_line(ok?returned:retained);
    if(!ok)for(;;)__asm__ volatile("wfe":::"memory");
    state.restoring=0;
}
