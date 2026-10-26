#include "lmi-display-pipeline.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
/* A fake adapter drives adverse hardware sequences against production code.
 * These are host protocol checks, never substituted for DMA/pixel validation. */
static struct {
    unsigned validates,cleans,starts,samples,restores;
    int clean_ok,start_result,sample_ok,detach_ok;
    uint32_t first;
    struct lmi_display_completion c;
} hw;
static int validate(void *ctx,const struct lmi_frame_buffer b[2])
{assert(ctx==&hw && b[0].iova!=b[1].iova);hw.validates++;return 1;}
static int clean(void *ctx,const struct lmi_frame_buffer *b)
{assert(ctx==&hw && b->bytes);hw.cleans++;return hw.clean_ok;}
static int start(void *ctx,const struct lmi_frame_buffer *b,uint32_t *first)
{assert(ctx==&hw && hw.cleans>hw.starts);hw.starts++;*first=hw.first;hw.c.source=b->iova;return hw.start_result;}
static int sample(void *ctx,struct lmi_display_completion *c)
{assert(ctx==&hw);hw.samples++;*c=hw.c;return hw.sample_ok;}
static int detach(void *ctx) {assert(ctx==&hw);hw.restores++;return hw.detach_ok;}
static const struct lmi_display_ops ops={validate,clean,start,sample,detach};
static const struct lmi_frame_buffer buffers[2]={
    {0x100000000ull,4544ull*2436,0x10000000,4544,1125,2436},
    {0x110000000ull,4544ull*2436,0x12000000,4544,1125,2436}
};
static void setup(struct lmi_display_pipeline *p)
{
    memset(p,0,sizeof(*p));memset(&hw,0,sizeof(hw));
    hw.clean_ok=hw.sample_ok=hw.detach_ok=hw.start_result=1;hw.first=99;
    assert(lmi_pipeline_init(p,buffers,&ops,&hw,2400,0x100,960000));
}
static int frame(struct lmi_display_pipeline *p,uint64_t *ticket)
{
    int n=lmi_pipeline_acquire(p,ticket);assert(n>=0);
    assert(!lmi_pipeline_submit(p,n,*ticket,0)); /* incomplete frame */
    assert(lmi_pipeline_complete_frame(p,n,*ticket));return n;
}
int main(void)
{
    struct lmi_display_pipeline p;uint64_t a,b;
    setup(&p);int na=frame(&p,&a);assert(lmi_pipeline_submit(&p,na,a,1000)==1);
    int nb=frame(&p,&b);assert(nb!=na && p.state[na]==LMI_SCANNING);
    assert(!lmi_pipeline_submit(&p,nb,b,2000)); /* CPU finishes B while A scans */
    assert(lmi_pipeline_acquire(&p,&b)==-1);assert(hw.starts==1);
    /* Stale DONE, early counter edge and active scan cannot retire A. */
    hw.c.status=0x100;hw.c.frame=99;hw.c.line=2400;assert(!lmi_pipeline_poll(&p,3000));
    hw.c.frame=100;hw.c.line=1000;assert(!lmi_pipeline_poll(&p,4000));
    hw.c.line=2400;assert(lmi_pipeline_poll(&p,5000)==1 && p.state[na]==LMI_FREE);
    assert(lmi_pipeline_submit(&p,nb,p.ticket[nb],5000)==1);
    /* An old writer lease never publishes/recycles a newly acquired frame. */
    uint64_t newer;assert(lmi_pipeline_acquire(&p,&newer)==na && newer!=a);
    assert(!lmi_pipeline_complete_frame(&p,na,a));
    assert(!lmi_pipeline_cancel_frame(&p,na,a));assert(lmi_pipeline_cancel_frame(&p,na,newer));
    assert(!lmi_pipeline_init(&p,buffers,&ops,&hw,2400,0x100,960000));
    lmi_pipeline_stop(&p);assert(lmi_pipeline_acquire(&p,&a)==-1);
    assert(lmi_pipeline_detach_after_cpu_stop(&p) && p.detached && hw.restores==1);
    assert(lmi_pipeline_detach_after_cpu_stop(&p) && hw.restores==1);
    /* Every adverse completion retains both buffers, including the READY one. */
    for(unsigned n=0;n<6;n++) {
        setup(&p);na=frame(&p,&a);assert(lmi_pipeline_submit(&p,na,a,0)==1);
        hw.c.frame=100;hw.c.line=2400;hw.c.status=0x100;
        if(n==0)hw.c.fault=1;if(n==1)hw.c.source++;
        if(n==2)hw.c.frame=101;if(n==3)hw.sample_ok=0;
        if(n==4)hw.c.status=0;if(n==5)hw.c.frame=99;
        assert(lmi_pipeline_poll(&p,960000)==-1 && p.state[0]==LMI_HELD && p.state[1]==LMI_HELD);
        assert(lmi_pipeline_acquire(&p,&a)==-1);hw.detach_ok=0;
        assert(lmi_pipeline_detach_after_cpu_stop(&p)==-1 && !p.detached);
        hw.detach_ok=1;assert(lmi_pipeline_detach_after_cpu_stop(&p));
    }
    /* Unsigned frame/timer wrap, cancellation, no-write refusal, uncertain START. */
    setup(&p);hw.first=UINT32_MAX;na=frame(&p,&a);
    assert(lmi_pipeline_submit(&p,na,a,UINT64_MAX-100)==1);
    hw.c.frame=0;hw.c.line=2400;hw.c.status=0x100;assert(lmi_pipeline_poll(&p,50)==1);
    setup(&p);na=frame(&p,&a);hw.start_result=0;
    assert(!lmi_pipeline_submit(&p,na,a,0) && p.state[na]==LMI_READY);
    hw.start_result=-1;assert(lmi_pipeline_submit(&p,na,a,0)==-1 && p.failed);
    setup(&p);na=frame(&p,&a);hw.clean_ok=0;
    assert(lmi_pipeline_submit(&p,na,a,0)==-1 && !hw.starts);
    /* CPU and device ranges must each be disjoint; reject overflow/short stride. */
    for(unsigned n=0;n<7;n++) {
        struct lmi_frame_buffer bad[2];memcpy(bad,buffers,sizeof(bad));memset(&p,0,sizeof(p));
        if(n==0)bad[1].pixels=bad[0].pixels+4096;
        if(n==1)bad[1].iova=bad[0].iova+4096;
        if(n==2)bad[0].bytes=1;if(n==3)bad[0].pitch=128;
        if(n==4)bad[0].pixels=UINTPTR_MAX-64;
        if(n==5)bad[0].iova=0xfffff000;if(n==6)bad[0].width=0;
        assert(!lmi_pipeline_init(&p,bad,&ops,&hw,2400,0x100,960000));
    }
    struct lmi_qseed_plan plan;assert(lmi_qseed_configure_plan(&plan,0x3000,4544));
    assert(plan.count==25 && plan.write[plan.count-1].offset==0x5a04);
    for(unsigned n=0;n<plan.count;n++)assert(plan.write[n].offset!=0x5014); /* adapter owns flips */
    assert(!lmi_qseed_configure_plan(&plan,0x2004,4544) && !plan.count);
    assert(!lmi_qseed_configure_plan(&plan,0x3000,4500));
    puts("PASS: double-buffer overlap, complete-frame gate, stale completion/lease, wrap, timeout, retention, DMA bounds");
}
