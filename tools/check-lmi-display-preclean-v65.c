#define main v62_pixel_regression
#include "fast-pixel-regression-v65.c"
#undef main
#include "lmi-display-preclean-v65.h"
static struct {
    struct lmi_display_dma *dma;
    unsigned char *visible[2];
    unsigned cleans,starts,polls,fail_clean,complete,clean_before_poll;
    uint64_t tick;
} device;
uint64_t lmi_preclean_ticks(void) {return ++device.tick;}
int lmi_preclean_original_clean(void *opaque,const struct lmi_frame_buffer *b)
{
    device.cleans++;
    if(device.fail_clean) {device.fail_clean--;return 0;}
    struct lmi_display_dma *d=opaque;
    if(!d || !d->prepared || d->restoring || !b)return 0;
    unsigned n=b->iova==d->buffer[0].iova?0:1;
    if(b->iova!=d->buffer[n].iova || b->pixels!=d->buffer[n].pixels ||
       b->bytes!=LMI_DMA_BUFFER_BYTES || b->pitch!=4544)return 0;
    /* Separate CPU and PoC views: START cannot see uncleaned CPU stores. */
    memcpy(device.visible[n],(void *)b->pixels,(size_t)b->bytes);
    if(!device.polls)device.clean_before_poll++;
    return 1;
}
static int pre_start(void *opaque,const struct lmi_frame_buffer *b,uint32_t *first)
{
    assert(opaque==device.dma);
    unsigned n=b->iova==device.dma->buffer[0].iova?0:1;
    assert(!memcmp(device.visible[n],(void *)b->pixels,(size_t)b->bytes));
    assert(current->p.scanning<0 && current->p.state[n]==LMI_READY);
    device.starts++;device.complete=0;*first=41;return 1;
}
static int pre_sample(void *opaque,struct lmi_display_completion *c)
{
    assert(opaque==device.dma && current->p.scanning>=0);device.polls++;
    c->source=current->p.buffer[current->p.scanning].iova;
    c->frame=device.complete?42:41;c->line=device.complete?2400:17;
    c->status=device.complete?256:0;return 1;
}
void lmi_preclean_emit(const char *tag,const uint64_t *values,unsigned count)
{
    assert(current->stop && !strcmp(tag,"LMI_DPU_PRECLEAN") && count==6);
    assert(values==&((struct lmi_preclean_stats *)lmi_fast_state)->prepared);
}
static struct lmi_preclean_stats *stats(void) {return (void *)lmi_fast_state;}
static struct fixture *make_pre(void)
{
    memset(&device,0,sizeof(device));log_count=0;
    struct fixture *f=make();free(lmi_fast_state);
    lmi_fast_state=lmi_preclean_allocate(sizeof(*lmi_fast_state),16);assert(lmi_fast_state);
    assert(!stats()->armed && !stats()->prepared && !stats()->original.fence.began);
    device.dma=calloc(1,sizeof(*device.dma));assert(device.dma);device.dma->prepared=1;
    for(unsigned n=0;n<2;n++) {
        void *allocation=calloc(1,LMI_DMA_BUFFER_BYTES+GUARD);assert(allocation);
        memcpy(allocation,(void *)f->p.buffer[n].pixels,BYTES+GUARD);
        free((void *)f->p.buffer[n].pixels);f->p.buffer[n].pixels=(uintptr_t)allocation;
        f->p.buffer[n].bytes=LMI_DMA_BUFFER_BYTES;device.dma->buffer[n]=f->p.buffer[n];
        device.visible[n]=calloc(1,LMI_DMA_BUFFER_BYTES);assert(device.visible[n]);
    }
    f->p.context=device.dma;f->p.ops.clean=lmi_preclean_original_clean;
    f->p.ops.start=pre_start;f->p.ops.sample=pre_sample;return f;
}
static int pre_frame(struct fixture *f,unsigned *n,uint64_t *t)
{void *surfaces[4]={f->surface,0,0,0};return lmi_preclean_frame(&f->c,&f->p,f->swap,surfaces,n,t);}
static void done(struct fixture *f)
{device.complete=1;assert(lmi_pipeline_poll(&f->p,1)==1);}
static void destroy_pre(struct fixture *f)
{
    /* Adversarial descriptor mutations must not redirect the test's free. */
    f->p.buffer[0]=device.dma->buffer[0];f->p.buffer[1]=device.dma->buffer[1];
    free(device.dma);free(device.visible[0]);free(device.visible[1]);destroy(f);
}
int main(void)
{
    assert(v62_pixel_regression()==0);
    unsigned cases=0,n,m;uint64_t t;
    assert(!lmi_preclean_allocate(1,16) && !lmi_preclean_allocate(sizeof(struct lmi_fast_stats),32));cases++;
    struct fixture *f=make_pre();
    assert(pre_frame(f,&n,&t)==1 && device.cleans==1 && stats()->armed);
    assert(lmi_pipeline_submit(&f->p,n,t,0)==1 && stats()->consumed==1 && device.cleans==1);
    assert(!lmi_pipeline_poll(&f->p,0));
    unsigned char *old=malloc(BYTES);assert(old);memcpy(old,(void *)f->p.buffer[n].pixels,BYTES);
    f->source[2]=0xff123456;device.polls=0;
    assert(pre_frame(f,&m,&t)==1 && m!=n && stats()->pending==1 && device.cleans==2);
    assert(!memcmp(old,(void *)f->p.buffer[n].pixels,BYTES));free(old);
    assert(device.clean_before_poll==2 && device.starts==1 && stats()->consumed==1);
    assert(lmi_pipeline_submit(&f->p,m,t,0)==0); /* Original DMA must finish. */
    done(f);assert(lmi_pipeline_submit(&f->p,m,t,1)==1 && device.cleans==2 && stats()->consumed==2);
    done(f);
    sw(f->swap,0x64,3);sw(f->swap,0x68,4);sw(f->swap,0x6c,2);sw(f->swap,0x70,2);
    f->source[2]=0xffbadbad;f->source[4*1136+3]=0xff112233;
    assert(pre_frame(f,&n,&t)==1 && f->draws==1);
    assert(((uint32_t *)f->p.buffer[n].pixels)[2]==0xff123456);
    assert(((uint32_t *)f->p.buffer[n].pixels)[4*1136+3]==0xff112233);
    assert(lmi_pipeline_submit(&f->p,n,t,2)==1 && device.cleans==3);done(f);
    assert(stats()->prepared==3 && stats()->consumed==3 && !stats()->fallback);
    assert(stats()->clean_ticks==3);lmi_preclean_cleanup();destroy_pre(f);cases++;
    /* Every identity, lifetime and state change invalidates the credit. A
     * fallback must actually invoke maintenance, even if the adapter refuses. */
    for(unsigned mode=0;mode<23;mode++) {
        f=make_pre();assert(pre_frame(f,&n,&t)==1 && stats()->armed);
        struct lmi_frame_buffer b=f->p.buffer[n];
        if(mode==0)stats()->ticket++;
        if(mode==1)f->p.ticket[n]++;
        if(mode==2)f->p.serial++;
        if(mode==3)stats()->index=2;
        if(mode==4)f->p.state[n]=LMI_WRITING;
        if(mode==5)f->p.failed=1;
        if(mode==6)f->p.stopping=1;
        if(mode==7)f->p.detached=1;
        if(mode==8)f->p.initialized=0;
        if(mode==9)device.dma->prepared=0;
        if(mode==10)device.dma->restoring=1;
        if(mode==11)device.dma->restored=1;
        if(mode==12)f->p.buffer[n].width++;
        if(mode==13)f->p.buffer[n].height++;
        if(mode==14)f->p.buffer[n].pitch+=64;
        if(mode==15)f->p.buffer[n].bytes++;
        if(mode==16)f->p.buffer[n].pixels++;
        if(mode==17)f->p.buffer[n].iova+=4096;
        if(mode==18)f->p.scanning=(int)(1-n);
        if(mode==19)b.pixels++;
        if(mode==20)stats()->context=0;
        if(mode==21)stats()->owner=0;
        if(mode==22)stats()->armed=0;
        (void)lmi_preclean_clean(device.dma,&b);
        assert(device.cleans==2 && stats()->fallback==1 && !stats()->consumed && !stats()->armed);
        destroy_pre(f);cases++;
    }
    f=make_pre();assert(pre_frame(f,&n,&t)==1);
    assert(lmi_pipeline_submit(&f->p,n,t,0)==1);
    assert(lmi_preclean_clean(device.dma,f->p.buffer+n)==1 && device.cleans==2 && stats()->fallback==1);
    done(f);destroy_pre(f);cases++;
    for(unsigned fail=1;fail<=2;fail++) {
        f=make_pre();device.fail_clean=fail;
        assert(pre_frame(f,&n,&t)==1 && stats()->failed==1 && !stats()->armed);
        int rc=lmi_pipeline_submit(&f->p,n,t,0);
        assert(device.cleans==2 && !stats()->consumed && stats()->fallback==1);
        if(fail==1) {assert(rc==1);done(f);}else assert(rc==-1 && f->p.failed && !device.starts);
        destroy_pre(f);cases++;
    }
    /* A failed new composition cannot reuse the previous clean credit. */
    f=make_pre();assert(pre_frame(f,&n,&t)==1);
    f->p.state[1-n]=LMI_READY;
    assert(pre_frame(f,&m,&t)==0 && !stats()->armed);
    assert(lmi_preclean_clean(device.dma,f->p.buffer+n)==1 && device.cleans==2 && !stats()->consumed);
    destroy_pre(f);cases++;
    for(unsigned mode=0;mode<3;mode++) {
        f=make_pre();
        if(mode==0)f->not_ready=1;
        if(mode==1)f->stop_after_show=1;
        if(mode==2)f->bad_join=1;
        assert(pre_frame(f,&n,&t)!=1 && !stats()->armed && !device.cleans);
        sw(f->fb,LMI_FB_fHelpersBusy,0);destroy_pre(f);cases++;
    }
    /* Actual observed 4608 pitch still produces the exact owned 4544 image. */
    f=make_pre();source(f,4608,0);assert(pre_frame(f,&n,&t)==1);identical(f,n);
    assert(lmi_pipeline_submit(&f->p,n,t,0)==1 && device.cleans==1);done(f);destroy_pre(f);cases++;
    printf("PASS: %u preclean integration cases plus 21 frozen pixel regressions\n",cases);
    return 0;
}
