/* Same-run spatial proof followed by logical-size desktop composition and
 * owned A/B hardware scanout. Every original swap is consumed at most once. */
#include "lmi-display-probe.h"
#include "lmi-display-compositor.h"
#include "lmi-display-compositor-abi.h"
#define RO __attribute__((section("__TEXT_EXEC,__lmi_ro")))
#define FN static LMI_PIPE_LOCAL
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
    struct lmi_compositor compositor;
    uint64_t began;
    /* Retain the exact reads immediately preceding a refusal. Logging after
     * failure must not replace these with a later snapshot of live hardware. */
    uint32_t last_key,last_value,failed_stage,failed_key,failed_value;
    char trace[16][128];
    unsigned trace_count;
};
static const char display_entry[] RO="LMI_DPU_PROBE_BEGIN live=1\n";
static const char display_format[] RO="LMI_DPU_PROBE stage=%u ok=%u exp=%x got=%x ticks=%llu\n";
static const char returned[] RO="LMI_DPU_PROBE_RETURN restored=1\n";
static const char retained[] RO="LMI_DPU_PROBE_RETURN restored=0 retained=1\n";
static const char display_map_failure[] RO="LMI_DPU_REFUSAL\n";
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
    c->last_key=(space<<24)|offset;c->last_value=value;return value;
}
FN void write_mmio(void *opaque,unsigned space,uint32_t offset,uint32_t value)
{
    struct native_context *c=opaque;
    c->map[space][offset/4]=value;__asm__ volatile("dsb sy":::"memory");
}
FN uintptr_t allocate(void *opaque,size_t bytes,size_t alignment)
{
    (void)opaque;if(stopping(0))return 0;
    return (uintptr_t)IOMallocAligned(bytes,alignment);
}
FN uint64_t physical(void *opaque,uintptr_t address)
{
    (void)opaque;return kvtophys(address);
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
    struct native_context *c=opaque;
    if(!ok && !c->failed_stage) {
        c->failed_stage=stage;c->failed_key=c->last_key;c->failed_value=c->last_value;
    }
    /* Publish complete lines only; replay after verified SMP stop so the log
     * ring cannot discard the spatial proof during desktop observation. */
    unsigned n=c->trace_count;
    if(n<16) {
        snprintf(c->trace[n],sizeof(c->trace[n]),display_format,stage,(unsigned)ok,expected,actual,(unsigned long long)elapsed);
        __atomic_store_n(&c->trace_count,n+1,__ATOMIC_RELEASE);
    }
}
static const char desktop_enabled[] RO="LMI_DPU_DESKTOP enabled=1\n";
static const char desktop_fallback[] RO="LMI_DPU_FALLBACK restored=1\n";
static const char desktop_failed[] RO="LMI_DPU_FALLBACK retained=1\n";
static const char desktop_stats[] RO="LMI_DPU_DESKTOP n=%llu sub=%llu done=%llu dt=%llu\n";
FN void statistics(struct native_context *c)
{
    char text[224];
    snprintf(text,sizeof(text),desktop_stats,(unsigned long long)c->compositor.frames,
        (unsigned long long)c->probe.pipeline.submitted,(unsigned long long)c->probe.pipeline.completed,
        (unsigned long long)(ticks(c)-c->began));loader_log_line(text);
}
FN int gpu_ready(void *opaque,void *surface)
{
    (void)opaque;
    /* Exact symbol checked by the builder; same frozen 64-bit ms ABI. */
    return ((_Bool (*)(void *,uint64_t))0xfffffff0079e5970ull)(surface,500);
}
FN void original_show(void *opaque,void *self,const unsigned char *swap,void **surfaces)
{(void)opaque;lmi_dpu_original_show(self,swap,surfaces);}
FN void desktop_show(struct native_context *c,void *self,const unsigned char *swap,void **surfaces)
{
    unsigned index=0;uint64_t ticket=0;
    int consumed=lmi_compositor_frame(&c->compositor,&c->probe.pipeline,swap,surfaces,&index,&ticket);
    int ok=consumed==1;
    while(ok && c->probe.pipeline.scanning>=0 && !stopping(c)) {
        int complete=lmi_pipeline_poll(&c->probe.pipeline,ticks(c));
        if(complete<0)ok=0;
        else if(!complete)delay(50);
    }
    if(stopping(c))return;
    if(ok)ok=lmi_pipeline_submit(&c->probe.pipeline,index,ticket,ticks(c))==1;
    if(ok) {
        if(!(c->compositor.frames%120))statistics(c);
        return;
    }
    lmi_pipeline_stop(&c->probe.pipeline);
    int restored=lmi_pipeline_detach_after_cpu_stop(&c->probe.pipeline)==1;
    state.done=restored?1u:0u;
    statistics(c);loader_log_line(restored?desktop_fallback:desktop_failed);
    if(restored && consumed==0 && !stopping(c))lmi_dpu_original_show(self,swap,surfaces);
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
        /* Consume this swap exactly once and let the native compositor
         * disable the text console before capturing stable GOP signatures. */
        lmi_dpu_original_show(self,swap,surfaces);
        if(stopping(0))return;
        /* Empty startup swaps do not disable the console. Wait until an
         * actual surface has been drawn before capturing a stable baseline. */
        if(!*((volatile unsigned char *)self+LMI_FB_fGraphics))return;
        state.attempted=1;
        struct lmi_display_probe *p=create();
        /* Publish the zeroed journal before any hardware ownership begins. */
        if(p) {
            __atomic_store_n(&state.probe,p,__ATOMIC_RELEASE);
            struct native_context *c=(struct native_context *)p;
            struct lmi_compositor_services io={c,gpu_ready,stopping,original_show};
            p->keep_active=lmi_compositor_init(&c->compositor,self,&io);
            (void)lmi_display_probe_run(p);
            if(p->verified && p->keep_active) {
                c->began=ticks(c);state.done=2;
            } else state.done=p->restore_ok;
        } else {state.done=1;loader_log_line(display_map_failure);}
        return; /* Original show already consumed this first swap. */
    }
    if(stopping(0))return;
    if(state.done==2)desktop_show((struct native_context *)state.probe,self,swap,surfaces);
    else if(state.done==1)lmi_dpu_original_show(self,swap,surfaces);
}
LMI_PIPE_CODE void lmi_display_smp_prepare(void)
{
    __atomic_store_n(&state.stopping,1,__ATOMIC_RELEASE);
    /* Preserve the exact native OFF verification, including its unknown-state
     * loop. Only AFTER it returns may this CPU bypass the transaction gate. */
    ((void (*)(void))0xfffffff00745a818ull)();
    state.restoring=1;
    struct lmi_display_probe *p=__atomic_load_n(&state.probe,__ATOMIC_ACQUIRE);
    /* The early trace can fall into the overwritten middle of the log ring.
     * Preserve the first refusal and the final state after every writer stops. */
    /* Stage 100+first failure: ok=verified, exp=probe frames,
     * got=final route (2=new),
     * ticks=(refused register key<<32)|value. These are diagnostic snapshots,
     * never substitutes for the complete eight-frame spatial proof. */
    if(p) {
        struct native_context *c=(struct native_context *)p;
        report(c,100+c->failed_stage,p->verified,p->frames,state.done,
            ((uint64_t)c->failed_key<<32)|c->failed_value);
        loader_log_line(display_entry);
        for(unsigned n=0;n<c->trace_count && n<16;n++)loader_log_line(c->trace[n]);
        if(p->verified && state.done==2)loader_log_line(desktop_enabled);
    } else loader_log_line(display_map_failure);
    int ok=!p || lmi_dma_restore(&p->dma);
    if(p && p->keep_active && p->verified)statistics((struct native_context *)p);
    loader_log_line(ok?returned:retained);
    if(!ok)for(;;)__asm__ volatile("wfe":::"memory");
    state.restoring=0;
}
