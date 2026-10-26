#include "lmi-display-pipeline.h"

static LMI_PIPE_CODE int valid_buffer(const struct lmi_frame_buffer *b)
{
    uint64_t size=(uint64_t)b->pitch*b->height;
    return b->pixels && b->width && b->height && b->width<=8192 && b->height<=8192 &&
        b->pitch>=(uint64_t)b->width*4 && !(b->pitch&63) && size && size<=b->bytes &&
        b->iova>=0x10000 && !(b->iova&4095) && b->bytes<=0x100000000ull-b->iova &&
        b->bytes<=UINTPTR_MAX-b->pixels;
}
static LMI_PIPE_CODE int overlap(uint64_t a,uint64_t as,uint64_t b,uint64_t bs)
{
    return a<b+bs && b<a+as;
}
static LMI_PIPE_CODE int hold(struct lmi_display_pipeline *p)
{
    p->failed=1;p->stopping=1;
    /* Preserve every allocation on uncertain completion, including a READY
     * frame. Recovery never silently reuses a buffer or clears the error. */
    for(unsigned n=0;n<2;n++)p->state[n]=LMI_HELD;
    return -1;
}
int lmi_pipeline_init(struct lmi_display_pipeline *p,const struct lmi_frame_buffer b[2],
    const struct lmi_display_ops *ops,void *context,uint32_t height,uint32_t done,uint64_t timeout)
{
    /* p must be zero initialized before its first use. */
    if(!p || p->initialized || !b || !ops || !ops->validate || !ops->clean || !ops->start ||
       !ops->sample || !ops->restore_detach || !height || height>8192 ||
       !done || (done&(done-1)) || !timeout || timeout>UINT64_MAX/2 ||
       !valid_buffer(b) || !valid_buffer(b+1) || b[0].width!=b[1].width ||
       b[0].height!=b[1].height || b[0].pitch!=b[1].pitch ||
       overlap(b[0].pixels,b[0].bytes,b[1].pixels,b[1].bytes) ||
       overlap(b[0].iova,b[0].bytes,b[1].iova,b[1].bytes))return 0;
    /* A fresh object only; never reinitialize an active DMA owner. */
    struct lmi_display_pipeline fresh={0};
    fresh.buffer[0]=b[0];fresh.buffer[1]=b[1];fresh.ops=*ops;fresh.context=context;
    fresh.output_height=height;fresh.done_bit=done;fresh.timeout=timeout;fresh.scanning=-1;fresh.initialized=1;
    if(!ops->validate(context,b))return 0;
    *p=fresh;return 1;
}
int lmi_pipeline_acquire(struct lmi_display_pipeline *p,uint64_t *ticket)
{
    if(!p || !p->initialized || !ticket || p->stopping || p->failed || p->detached)return -1;
    for(unsigned n=0;n<2;n++)if(p->state[n]==LMI_FREE) {
        if(p->serial==UINT64_MAX)return hold(p);
        p->state[n]=LMI_WRITING;p->ticket[n]=++p->serial;*ticket=p->serial;return (int)n;
    }
    return -1;
}
int lmi_pipeline_complete_frame(struct lmi_display_pipeline *p,unsigned n,uint64_t ticket)
{
    if(!p || !p->initialized || n>=2 || p->stopping || p->failed || p->detached ||
       p->state[n]!=LMI_WRITING || !ticket || p->ticket[n]!=ticket)return 0;
    /* Called only after the compositor and all row workers have completed.
     * A release fence publishes the full pixels before a scanout consumer. */
    __atomic_thread_fence(__ATOMIC_RELEASE);p->state[n]=LMI_READY;return 1;
}
int lmi_pipeline_cancel_frame(struct lmi_display_pipeline *p,unsigned n,uint64_t ticket)
{
    if(!p || !p->initialized || n>=2 || p->failed || p->detached ||
       p->state[n]!=LMI_WRITING || !ticket || p->ticket[n]!=ticket)return 0;
    p->state[n]=LMI_FREE;return 1;
}
int lmi_pipeline_submit(struct lmi_display_pipeline *p,unsigned n,uint64_t ticket,uint64_t now)
{
    if(!p || !p->initialized || n>=2 || p->stopping || p->failed || p->detached || p->scanning>=0 ||
       p->state[n]!=LMI_READY || !ticket || p->ticket[n]!=ticket)return 0;
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if(!p->ops.clean(p->context,p->buffer+n))return hold(p);
    uint32_t first=0;
    int started=p->ops.start(p->context,p->buffer+n,&first);
    if(started<0)return hold(p);
    if(!started)return 0;
    if(started!=1)return hold(p);
    p->first_frame=first;p->started_at=now;p->scanning=(int)n;
    p->state[n]=LMI_SCANNING;p->submitted++;return 1;
}
int lmi_pipeline_poll(struct lmi_display_pipeline *p,uint64_t now)
{
    if(!p || !p->initialized || p->failed || p->detached)return -1;
    if(p->scanning<0)return 0;
    struct lmi_display_completion c={0};
    if(!p->ops.sample(p->context,&c) || c.fault)return hold(p);
    unsigned n=(unsigned)p->scanning;
    uint32_t delta=c.frame-p->first_frame;
    if(c.source!=p->buffer[n].iova || delta>1)return hold(p);
    if((c.status&p->done_bit) && delta==1 && c.line>=p->output_height) {
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        p->state[n]=LMI_FREE;p->scanning=-1;p->completed++;return 1;
    }
    if(now-p->started_at>=p->timeout)return hold(p);
    return 0;
}
void lmi_pipeline_stop(struct lmi_display_pipeline *p) {if(p)p->stopping=1;}
int lmi_pipeline_detach_after_cpu_stop(struct lmi_display_pipeline *p)
{
    if(!p || !p->initialized || !p->stopping)return 0;
    if(p->detached)return 1;
    if(p->ops.restore_detach(p->context)!=1)return hold(p);
    /* The caller guarantees row/presenter CPUs cannot resume. No allocation
     * is freed here; only this proven state permits the owner to free it. */
    p->scanning=-1;p->state[0]=p->state[1]=LMI_FREE;p->detached=1;return 1;
}

int lmi_qseed_configure_plan(struct lmi_qseed_plan *p,uint32_t version,uint32_t pitch)
{
    if(!p)return 0;
    p->count=0;
    if(version!=0x3000 || (pitch!=4544 && pitch!=4608))return 0;
    enum {sx=(uint32_t)(((uint64_t)1125<<21)/1080),
    sy=(uint32_t)(((uint64_t)2436<<21)/2400)};
    /* Vendor QSEED4 defaults: H preload=4, V preload=2; bilinear
     * RGB/alpha, blend_cfg=1, dynamic expansion enabled. Keep pixel-centered
     * phase to place the diagnostic cell edges between output samples. */
    enum {px=(sx-(1u<<21))/2,py=(sy-(1u<<21))/2};
#ifdef LMI_PIPELINE_NATIVE
#define PLAN_RO __attribute__((section("__TEXT_EXEC,__lmi_ro")))
#else
#define PLAN_RO
#endif
    static const struct lmi_scale_write values[] PLAN_RO={
        {0x5000,(2436u<<16)|1125u},{0x5008,0},{0x5024,4544},
        {0x5100,0},{0x5104,0},{0x5108,(2436u<<16)|1125u},
        {0x5110,0},{0x5114,0},{0x5118,(2436u<<16)|1125u},
        {0x5120,0},{0x5124,0},{0x5128,(2436u<<16)|1125u},
        {0x5a90,px},{0x5a94,py},{0x5a98,px},{0x5a9c,py},
        {0x5a10,sx},{0x5a14,sy},{0x5a18,sx},{0x5a1c,sy},
        {0x5a20,0x02040204},{0x5a40,(2436u<<16)|1125u},
        {0x5a44,(2436u<<16)|1125u},{0x5a48,(2400u<<16)|1080u},
        {0x5a04,0xa0034401}
    };
    for(unsigned n=0;n<sizeof(values)/sizeof(values[0]);n++)p->write[p->count++]=values[n];
    p->write[2].value=pitch;
    return 1;
}
