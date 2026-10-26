#include "lmi-display-probe.h"
#ifdef LMI_PIPELINE_NATIVE
#define RO __attribute__((section("__TEXT_EXEC,__lmi_ro")))
#else
#define RO
#endif
#define FN static LMI_PIPE_LOCAL
static const struct lmi_display_ops probe_ops RO={
    lmi_dma_validate,lmi_dma_clean,lmi_dma_start,lmi_dma_sample,lmi_dma_restore
};
FN int stopped(struct lmi_display_probe *p) {return p->stopping && p->stopping(p->opaque);}
FN void report(struct lmi_display_probe *p,unsigned stage,int ok,uint32_t expected,uint32_t actual,uint64_t ticks)
{p->stage=stage;if(p->report)p->report(p->opaque,stage,ok,expected,actual,ticks);}
LMI_PIPE_CODE int lmi_display_diagnostic_pattern(struct lmi_display_probe *p,unsigned n,int scaled,unsigned seed)
{
    if(!p || n>=2 || seed>=8 || stopped(p))return 0;
    const struct lmi_frame_buffer *b=p->dma.buffer+n;
    if(!b->pixels || b->bytes!=LMI_DMA_BUFFER_BYTES || b->pitch!=4544 ||
       b->width!=1125 || b->height!=2436)return 0;
    uint32_t *pixels=(uint32_t *)b->pixels;
    /* Poison stride padding, unused rows and allocation tail. A spatial grid
     * makes pitch, phase, geometry and A/B mapping errors visible to MISR.
     * Cell 25x203 -> 24x200 aligns exactly for this 1125x2436 ->1080x2400 ratio. */
    for(unsigned i=0;i<b->bytes/4;i++) {
        if(!(i&1023) && stopped(p))return 0;
        pixels[i]=0xff00ff00u;
    }
    unsigned width=scaled?1125:1080,height=scaled?2436:2400;
    unsigned cell_x=scaled?25:24,cell_y=scaled?203:200;
    for(unsigned y=0;y<height;y++) {
        if(stopped(p))return 0;
        uint32_t *row=(uint32_t *)(b->pixels+(uintptr_t)y*b->pitch);
        for(unsigned x=0;x<width;) {
            unsigned kind=seed>>1;
            unsigned block=(kind&1)?x/cell_x:0;
            unsigned band=(kind&2)?y/cell_y:0;
            uint32_t color=((block+3*band+seed)&1)?0xffd03070u:0xff20c0a0u;
            for(unsigned end=x+cell_x;x<end;x++)row[x]=color;
        }
    }
    return !stopped(p);
}
FN int produce(struct lmi_display_probe *p,int scaled,unsigned seed,int *index,uint64_t *ticket)
{
    if(stopped(p))return 0;
    int n=lmi_pipeline_acquire(&p->pipeline,ticket);if(n<0)return 0;
    *index=n;
    return lmi_display_diagnostic_pattern(p,(unsigned)n,scaled,seed) &&
        lmi_pipeline_complete_frame(&p->pipeline,(unsigned)n,*ticket);
}
FN int finish(struct lmi_display_probe *p,unsigned stage,unsigned seed,int scaled,uint64_t began)
{
    struct lmi_dma_services *io=&p->dma.io;
    int done;
    do {
        if(stopped(p))return 0;
        done=lmi_pipeline_poll(&p->pipeline,io->ticks(io->opaque));
        if(done<0)return 0;
        if(!done)io->pause(io->opaque,50);
    }while(!done);
    uint32_t crc=lmi_dma_signature(&p->dma),expected=p->reference[seed&1];
    int ok=1;
    if(!scaled && p->frames<2)p->reference[seed&1]=expected=crc;
    else ok=crc==expected;
    p->frames++;
    report(p,stage,ok,expected,crc,io->ticks(io->opaque)-began);
    return ok?1:2; /* 2 means completed pixels differ, not a DMA fault. */
}
FN int pair(struct lmi_display_probe *p,int scaled,unsigned round,unsigned kind,unsigned stage)
{
    struct lmi_dma_services *io=&p->dma.io;
    int a,b;uint64_t ta,tb;
    unsigned seed=(kind<<1)|(round&1);
    if(!produce(p,scaled,seed,&a,&ta))return 0;
    uint64_t began=io->ticks(io->opaque);
    if(lmi_pipeline_submit(&p->pipeline,(unsigned)a,ta,began)!=1)return 0;
    /* Populate B while A has an outstanding real hardware transfer. No poll
     * may acknowledge A until B's whole frame is published. */
    if(!produce(p,scaled,seed^1,&b,&tb) || a==b)return 0;
    int result=finish(p,stage,seed,scaled,began);if(!result)return 0;
    began=io->ticks(io->opaque);
    if(lmi_pipeline_submit(&p->pipeline,(unsigned)b,tb,began)!=1)return 0;
    int other=finish(p,stage+1,seed^1,scaled,began);
    return !other?0:(result==1 && other==1?1:2);
}
LMI_PIPE_CODE int lmi_display_diagnostic_run(struct lmi_display_probe *p)
{
    if(!p || p->stage || stopped(p))return 0;
    p->verified=0;p->keep_active=0;
    report(p,1,1,0,0,0);
    int ok=lmi_dma_prepare(&p->dma);
    report(p,2,ok,0,p->dma.baseline,0);
    if(ok)ok=lmi_pipeline_init(&p->pipeline,p->dma.buffer,&probe_ops,&p->dma,2400,0x100,960000);
    uint32_t matched=0;
    for(unsigned variant=0;ok && variant<8;variant++)for(unsigned kind=0;ok && kind<4;kind++) {
        unsigned base=1000+variant*100+kind*10;
        p->frames=0;
        ok=lmi_dma_set_scaling(&p->dma,0);
        if(ok)ok=pair(p,0,0,kind,base)==1 && pair(p,0,1,kind,base+2)==1 && p->reference[0]!=p->reference[1];
        if(!ok)break;
        ok=lmi_dma_set_scaling(&p->dma,(int)variant+1);
        if(!ok) {report(p,base+8,0,0,0,0);break;}
        int first=pair(p,1,0,kind,base+4);
        int second=first?pair(p,1,1,kind,base+6):0;
        ok=first && second;
        int same=first==1 && second==1;
        if(same)matched|=1u<<(variant*4+kind);
        report(p,base+8,same,p->reference[0],p->reference[1],variant+1);
    }
    report(p,90,ok,(uint32_t)p->pipeline.submitted,(uint32_t)p->pipeline.completed,matched);
    if(stopped(p))return 0;
    if(p->pipeline.initialized) {
        lmi_pipeline_stop(&p->pipeline);
        p->restore_ok=lmi_pipeline_detach_after_cpu_stop(&p->pipeline)==1;
    } else p->restore_ok=lmi_dma_restore(&p->dma);
    p->verified=0; /* No diagnostic variant can enable desktop scanout. */
    report(p,5,p->restore_ok,0,0,0);
    return 0;
}
