#include "lmi-display-fast-v62.h"
#include "lmi-display-compositor-abi.h"
#include "lmi-display-surface-abi.h"
extern void *IOMallocAligned(size_t,size_t);
extern void *memcpy(void *,const void *,size_t);
extern void bzero(void *,size_t);
extern void loader_log_line(const char *);
static uint32_t word(const void *p,unsigned at)
{return *(const uint32_t *)((const unsigned char *)p+at);}
static uintptr_t pointer(const void *p,unsigned at)
{return *(const uintptr_t *)((const unsigned char *)p+at);}
static struct lmi_fast_stats *statistics(void)
{return __atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);}
/* Decode only the compiled real surface ABI; never pass a client address to
 * DMA. The ordinary presenter already holds this source until show returns. */
static __attribute__((noinline)) int pixels(const unsigned char *swap,void **surfaces,struct lmi_direct_plan *plan,struct lmi_fast_stats *stats)
{
    if(!swap || !surfaces || !surfaces[0]) {stats->reasons|=1;return 0;}
    if(surfaces[1] || surfaces[2] || surfaces[3]) {stats->reasons|=2;return 0;}
    const void *s=surfaces[0];unsigned i=LMI_SURF_info;
    struct lmi_direct_surface_view view[4]={0};
    view[0]=(struct lmi_direct_surface_view){
        .allocation=pointer(s,LMI_SURF_kpixels),.sid=word(s,LMI_SURF_sid),
        .allocation_bytes=word(s,i+0x1c),.offset=word(s,i+0x2c),
        .width=word(s,i+0x20),.height=word(s,i+0x24),.pitch=word(s,i+0x28),
        .format=word(s,i+0x30),.planes=word(s,i+0x38),
        .element_bytes=*(const uint16_t *)((const unsigned char *)s+i+0x40),
        .client_backed=pointer(s,LMI_SURF_client)!=0};
    if(!stats->sampled) {
        stats->metadata[0]=view[0].sid;
        stats->metadata[1]=(uint64_t)view[0].width<<32|view[0].height;
        stats->metadata[2]=(uint64_t)view[0].pitch<<32|view[0].format;
        stats->metadata[3]=(uint64_t)view[0].allocation_bytes<<32|view[0].offset;
        stats->metadata[4]=word(swap,0x104);stats->metadata[5]=view[0].client_backed;
        for(unsigned n=0;n<4;n++) {
            unsigned at=(n<2?0x64:0xc4)+(n&1)*8;
            stats->metadata[6+n]=(uint64_t)word(swap,at)<<32|word(swap,at+4);
        }
        stats->sampled=1;
    }
    if(!pointer(s,LMI_SURF_memory) || word(s,i+0x18)!=view[0].sid) {stats->reasons|=4;return 0;}
    int ok=lmi_direct_plan(swap,0x46c,view,plan);
    if(!ok)stats->reasons|=8;
    return ok;
}
int lmi_fast_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *swap,void **surfaces,unsigned *index,uint64_t *ticket)
{
    struct lmi_fast_stats *s=statistics();struct lmi_direct_plan plan;
    int n=-1,latest=0,eligible=0;
    if(s && !s->active && c && c->initialized && p && p->initialized && !p->failed && !p->stopping && !p->detached &&
       p->serial!=UINT64_MAX && index && ticket && lmi_fast_original_fields(c) && pixels(swap,surfaces,&plan,s)) {
        /* This is exactly the frozen acquire order. There is one presenter;
         * no completion/poll or other state writer runs inside frame(). */
        for(unsigned i=0;i<2;i++)if(p->state[i]==LMI_FREE) {n=(int)i;break;}
        if(n>=0) {
            const struct lmi_frame_buffer *b=p->buffer+n;
            eligible=b->width==1125 && b->height==2436 && b->pitch==4544 && b->bytes>=4544u*2436u &&
                b->bytes<=UINTPTR_MAX-b->pixels &&
                (plan.pixels+plan.bytes<=b->pixels || b->pixels+b->bytes<=plan.pixels);
            if(!eligible)s->reasons|=64;
        } else s->reasons|=32;
    }
    if(eligible) {
        latest=c->latest;c->latest=n;
        s->self=c->self;s->surface=surfaces[0];s->source=plan.pixels;
        s->target=p->buffer[n].pixels;s->bytes=4544u*2436u;s->source_pitch=plan.pitch;s->active=1;
    } else if(s) {s->slow++;s->reasons|=16;}
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
        if(s->source_pitch==4544)memcpy((void *)s->target,(const void *)s->source,s->bytes);
        else {
            /* Copy into the proven owned 4544-byte pitch. Source row padding
             * is excluded beyond that length; visible pixels stay identical. */
            for(unsigned y=0;y<2436;y++)memcpy((void *)(s->target+(uintptr_t)y*4544),
                (const void *)(s->source+(uintptr_t)y*s->source_pitch),4544);
            s->strided++;
        }
        s->copies++;return;
    }
    lmi_fast_original_draw(self,surface,src,dst);
}
/* No variadic ABI crossing. The helper is ELF AArch64; Darwin arm64 kernel
 * printf-family routines take variadic integers on the stack, not x3..x7.
 * Format bounded uint64 values locally and call only the fixed line ABI. */
static __attribute__((noinline)) void emit(const char *tag,const uint64_t *values,unsigned count)
{
    char line[256],digits[20];unsigned at=0;
    while(*tag)line[at++]=*tag++;
    for(unsigned n=0;n<count;n++) {
        uint64_t value=values[n];unsigned used=0;
        line[at++]=' ';
        do {digits[used++]=(char)('0'+value%10);value/=10;}while(value);
        while(used)line[at++]=digits[--used];
    }
    line[at++]='\n';line[at]=0;loader_log_line(line);
}
void lmi_fast_cleanup(void)
{
    lmi_fast_original_cleanup(); /* Exact SMP stop + DPU restore, before reading stats. */
    struct lmi_fast_stats *s=__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);
    if(s) {
        const uint64_t counts[]={s->frames,s->copies,s->slow};
        emit("LMI_DPU_FAST",counts,3);
        emit("LMI_FRAME_GUARD",&s->reasons,1);
        emit("LMI_FRAME_META",s->metadata,10);
        emit("LMI_FRAME_STRIDE",&s->strided,1);
        emit("LMI_SWAP_FENCE",&s->fence.began,10);
    }
}
