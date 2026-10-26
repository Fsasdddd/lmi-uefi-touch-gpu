#include "lmi-display-fast-v59.h"
#include "lmi-display-compositor-abi.h"
#include "lmi-display-surface-abi.h"
extern void *IOMallocAligned(size_t,size_t);
extern void *memcpy(void *,const void *,size_t);
extern void bzero(void *,size_t);
extern int snprintf(char *,size_t,const char *,...);
extern void loader_log_line(const char *);
static uint32_t word(const void *p,unsigned at)
{return *(const uint32_t *)((const unsigned char *)p+at);}
static uintptr_t pointer(const void *p,unsigned at)
{return *(const uintptr_t *)((const unsigned char *)p+at);}
static struct lmi_fast_stats *statistics(void)
{
    struct lmi_fast_stats *s=lmi_fast_state;
    if(!s) {
        s=IOMallocAligned(sizeof(*s),16);
        if(s) {bzero(s,sizeof(*s));__atomic_store_n(&lmi_fast_state,s,__ATOMIC_RELEASE);}
    }
    return s;
}
/* Decode only the compiled real surface ABI; never pass a client address to
 * DMA. The ordinary presenter already holds this source until show returns. */
static int pixels(const unsigned char *swap,void **surfaces,struct lmi_direct_plan *plan)
{
    if(!swap || !surfaces || !surfaces[0] || surfaces[1] || surfaces[2] || surfaces[3])return 0;
    const void *s=surfaces[0];unsigned i=LMI_SURF_info;
    struct lmi_direct_surface_view view[4]={0};
    view[0]=(struct lmi_direct_surface_view){
        .allocation=pointer(s,LMI_SURF_kpixels),.sid=word(s,LMI_SURF_sid),
        .allocation_bytes=word(s,i+0x1c),.offset=word(s,i+0x2c),
        .width=word(s,i+0x20),.height=word(s,i+0x24),.pitch=word(s,i+0x28),
        .format=word(s,i+0x30),.planes=word(s,i+0x38),
        .element_bytes=*(const uint16_t *)((const unsigned char *)s+i+0x40),
        .client_backed=pointer(s,LMI_SURF_client)!=0};
    return pointer(s,LMI_SURF_memory) && word(s,i+0x18)==view[0].sid && lmi_direct_plan(swap,0x46c,view,plan);
}
int lmi_fast_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *swap,void **surfaces,unsigned *index,uint64_t *ticket)
{
    struct lmi_fast_stats *s=statistics();struct lmi_direct_plan plan;
    int n=-1,latest=0,eligible=0;
    if(s && !s->active && c && c->initialized && p && p->initialized && !p->failed && !p->stopping && !p->detached &&
       p->serial!=UINT64_MAX && index && ticket && lmi_fast_original_fields(c) && pixels(swap,surfaces,&plan)) {
        /* This is exactly the frozen acquire order. There is one presenter;
         * no completion/poll or other state writer runs inside frame(). */
        for(unsigned i=0;i<2;i++)if(p->state[i]==LMI_FREE) {n=(int)i;break;}
        if(n>=0) {
            const struct lmi_frame_buffer *b=p->buffer+n;
            eligible=b->width==1125 && b->height==2436 && b->pitch==4544 && b->bytes>=plan.bytes &&
                b->bytes<=UINTPTR_MAX-b->pixels &&
                (plan.pixels+plan.bytes<=b->pixels || b->pixels+b->bytes<=plan.pixels);
        }
    }
    if(eligible) {
        latest=c->latest;c->latest=n;
        s->self=c->self;s->surface=surfaces[0];s->source=plan.pixels;
        s->target=p->buffer[n].pixels;s->bytes=plan.bytes;s->active=1;
    } else if(s)s->slow++;
    /* Keep native GPU waits, queue dequeue/wakeup, fLock, record(), stats,
     * and the original consume-once error semantics. Full overwrite alone
     * skips the previous-frame copy. Partial/multilayer frames are untouched. */
    int result=lmi_fast_original_frame(c,p,swap,surfaces,index,ticket);
    if(eligible) {
        s->active=0;
        if(result==1)s->frames++;else c->latest=latest;
    }
    return result;
}
void lmi_fast_draw(void *self,void *surface,const int32_t *src,const int32_t *dst)
{
    struct lmi_fast_stats *s=lmi_fast_state;
    if(s && s->active && self==s->self && surface==s->surface && pointer(self,LMI_FB_fBase)==s->target &&
       word(self,LMI_FB_fPanelWidth)==1125 && word(self,LMI_FB_fPanelHeight)==2436 && word(self,LMI_FB_fRowBytes)==4544) {
        /* Runs at native drawLayer's callsite, after dequeue and GPU wait,
         * with fLock held. DPU reads the OTHER owned buffer concurrently. */
        memcpy((void *)s->target,(const void *)s->source,s->bytes);s->copies++;return;
    }
    lmi_fast_original_draw(self,surface,src,dst);
}
void lmi_fast_cleanup(void)
{
    lmi_fast_original_cleanup(); /* Exact SMP stop + DPU restore, before reading stats. */
    struct lmi_fast_stats *s=__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);
    if(s) {
        char line[120];
        snprintf(line,sizeof(line),"LMI_DPU_FAST %llu %llu %llu\n",(unsigned long long)s->frames,
            (unsigned long long)s->copies,(unsigned long long)s->slow);loader_log_line(line);
    }
}
