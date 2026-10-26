#define _POSIX_C_SOURCE 200112L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Include the production implementation to inspect its page tables, not a
 * second implementation of the adapter. The MMIO model is a host protocol
 * model only: it cannot prove real bus ordering, pixels or register behavior. */
#include "lmi-display-dma-v56.c"
#include "lmi-display-probe.h"

struct allocation {uintptr_t va;size_t size;uint64_t pa;};
struct fake {
    uint32_t mdss[0x70000/4],smmu[0x100000/4];
    struct allocation allocation[3];
    struct lmi_display_dma *d;
    unsigned allocations,enters,writes,starts,cleans,locked;
    unsigned fail_enter,drop_write,busy_tlb,stall,unstable,pa_alias,va_alias;
    unsigned asidpne_ignored,drop_translation,unexpected_control,flip_global;
    unsigned ignored_blend,drop_scaler_enable,unexpected_scaler,drop_preload;
    unsigned normalized_signature;
    unsigned model_patterns,scaled_bad,probe_stopping,restore_mode,stop_stage,reports;
    int queued;
    uint64_t now;
};
static unsigned scenarios;
static uint32_t *reg(struct fake *f,unsigned space,uint32_t offset)
{
    assert(space<=1 && !(offset&3));
    assert(offset<(space?sizeof(f->smmu):sizeof(f->mdss)));
    return (space?f->smmu:f->mdss)+offset/4;
}
static uint32_t read_reg(void *context,unsigned space,uint32_t offset)
{
    struct fake *f=context;assert(f->locked);
    if(space && offset==CB+0x7f4)return f->busy_tlb;
    return *reg(f,space,offset);
}
static void write_reg(void *context,unsigned space,uint32_t offset,uint32_t value)
{
    struct fake *f=context;assert(f->locked);f->writes++;
    if(space) {
        assert(offset==CB+0x610 || offset==CB+0x7f0);
        /* Only the journaled context registers or its own TLB operations. */
    }
    if(f->writes==f->drop_write)return;
    if(!space && offset==0x1018) {*reg(f,0,0x1014)&=~value;return;}
    if(!space && offset==0x2018)assert(value==1); /* never replay a flush snapshot */
    if(!space && offset==MISR) {
        *reg(f,0,MISR)=(value&0x400)?0:value&0x8f0001ff;return;
    }
    if(!space && offset==0x201c) {
        assert(!f->queued && *reg(f,0,AUTO)==1 && (*reg(f,0,SYNC)&TE));
        f->queued=1;f->starts++;*reg(f,0,LINE)=0;
    }
    if(!space && offset==0x5a04) {
        if(f->ignored_blend)value&=~0x80000000u;
        if(f->drop_scaler_enable)value&=~1u;
        if(f->unexpected_scaler)value|=1u<<20;
    }
    if(!space && offset==0x5a20 && f->drop_preload)value&=~4u;
    *reg(f,space,offset)=value;
}
/* Write wrapper recognizes context registers separately so unrelated global
 * or stream writes fail the test, even during interrupted restoration. */
static void checked_write(void *context,unsigned space,uint32_t offset,uint32_t value)
{
    struct fake *f=context;
    if(space) {
        for(unsigned n=0;n<9;n++)if(offset==CB+cb_offset[n]) {
            assert(f->locked && !f->queued && *reg(f,0,AUTO)==1);
            f->writes++;
            if(f->writes!=f->drop_write) {
                if(offset==CB && (value&1)) {
                    assert(value==0x127u); /* All functional bits are requested exactly. */
                    if(f->asidpne_ignored)value&=~0x1000u;
                    if(f->drop_translation)value&=~1u;
                    if(f->unexpected_control)value|=0x80000000u;
                }
                *reg(f,space,offset)=value;
            }
            return;
        }
    } else {
        int allowed=offset==SYNC || offset==AUTO || offset==MISR || offset==0x5014 ||
            offset==0x1018 || offset==0x2018 || offset==0x201c;
        for(unsigned n=0;n<25;n++)allowed|=offset==scale_offset[n];
        assert(allowed);
    }
    write_reg(context,space,offset,value);
}
static int gate(void *context,uint64_t *flags)
{
    struct fake *f=context;assert(!f->locked);f->enters++;
    if(f->enters==f->fail_enter)return 0;
    if(f->probe_stopping && !f->restore_mode)return 0;
    f->locked=1;*flags=0xcafe;return 1;
}
static void ungate(void *context,uint64_t flags)
{struct fake *f=context;assert(f->locked && flags==0xcafe);f->locked=0;}
static uintptr_t allocate(void *context,size_t bytes,size_t alignment)
{
    struct fake *f=context;assert(!f->locked && f->allocations<3);
    unsigned n=f->allocations++;void *p=0;
    if(!n && f->flip_global)*reg(f,1,0)^=1u<<19;
    assert(!posix_memalign(&p,alignment,bytes));
    f->allocation[n]=(struct allocation){(uintptr_t)p,bytes,0x40000000ull+0x10000000ull*n};
    if(n==1 && f->va_alias==1)return f->allocation[0].va+16384;
    if(n==2 && f->va_alias==2)return f->allocation[1].va;
    if(n==1 && f->va_alias==3)return UINTPTR_MAX-16383;
    return (uintptr_t)p;
}
static uint64_t physical(void *context,uintptr_t va)
{
    struct fake *f=context;assert(!f->locked);
    for(unsigned n=0;n<f->allocations;n++) {
        struct allocation *a=f->allocation+n;
        if(va>=a->va && va-a->va<a->size) {
            uint64_t offset=va-a->va,pa=a->pa+offset;
            if(f->pa_alias==1 && n==0 && offset==4096)pa=a->pa;
            if(f->pa_alias==2 && n==1 && !offset)pa=f->allocation[0].pa;
            if(f->pa_alias==3 && n==1 && offset==4096)pa=a->pa;
            if(f->pa_alias==4 && n==2 && !offset)pa=f->allocation[1].pa;
            if(f->pa_alias==5 && n==1 && !offset)pa=GOP;
            if(f->pa_alias==6 && n==0 && !offset)pa=GOP;
            if(f->pa_alias==7 && n==1 && !offset)pa=1ull<<36;
            if(f->pa_alias==8 && n==1 && !offset)pa++;
            if(f->pa_alias==9 && n==1 && !offset)pa=0;
            return pa;
        }
    }
    assert(!"unowned virtual memory");return 0;
}
static void clean(void *context,uintptr_t va,size_t bytes)
{
    struct fake *f=context;assert(!f->locked);int owned=0;
    for(unsigned n=0;n<f->allocations;n++)owned|=va==f->allocation[n].va && bytes==f->allocation[n].size;
    assert(owned);f->cleans++;
}
static uint64_t ticks(void *context) {return ((struct fake *)context)->now;}
static void pause_us(void *context,unsigned us)
{
    struct fake *f=context;assert(!f->locked);f->now+=(uint64_t)us*192/10+1;
    int automatic=(*reg(f,0,AUTO)&0x80000000) && (*reg(f,0,SYNC)&TE);
    if((automatic || (f->queued && (*reg(f,0,SYNC)&TE))) && !f->stall) {
        uint32_t frame=++*reg(f,0,FRAME);*reg(f,0,LINE)=2400;
        *reg(f,0,0x1014)|=DONE;f->queued=0;
        if(*reg(f,0,MISR)&0x100) {
            *reg(f,0,MISR)|=0x200;
            uint32_t source=*reg(f,0,0x5014);
            *reg(f,0,MISR+4)=source==GOP?0x12345678u:source^0xabcdefu;
            if(f->model_patterns && source!=GOP) {
                unsigned n=source==f->d->buffer[0].iova?0:1;
                assert(source==f->d->buffer[n].iova);
                /* Deliberately a protocol signature, not a QSEED emulator or
                 * pixel-validation substitute. Test real output with MISR. */
                *reg(f,0,MISR+4)=*(uint32_t *)f->d->buffer[n].pixels^0xabcdefu;
                if(f->normalized_signature) {
                    uint32_t color=*(uint32_t *)f->d->buffer[n].pixels;
                    if(color==0xff000000u)*reg(f,0,MISR+4)=0x484aa7cbu^(f->normalized_signature==2);
                    if(color==0xffffffffu)*reg(f,0,MISR+4)=0xf874a603u;
                    if(*reg(f,0,0x5a04))*reg(f,0,MISR+4)^=0x484aa7cbu;
                }
                if(f->scaled_bad && *reg(f,0,0x5a04) && *reg(f,0,0x5a10)!=(1u<<21))*reg(f,0,MISR+4)^=1;
            }
            if(f->unstable)*reg(f,0,MISR+4)^=frame;
        }
    }
}
static struct fake *setup(void)
{
    struct fake *f=calloc(1,sizeof(*f));assert(f);
    f->d=calloc(1,sizeof(*f->d));assert(f->d);scenarios++;
    f->d->io=(struct lmi_dma_services){f,read_reg,checked_write,gate,ungate,allocate,physical,clean,ticks,pause_us};
    *reg(f,1,0)=0x240406;*reg(f,1,0x20)=0x4c017e57;*reg(f,1,0x24)=0x6000004a;*reg(f,1,0x28)=0x5111;
    *reg(f,1,0x810)=0x84020820;*reg(f,1,0xc10)=4;*reg(f,1,0x1010)=0x1f000;*reg(f,1,0x1810)=1;
    *reg(f,1,CB)=0xe0;*reg(f,1,CB+0x10)=0x40034072;*reg(f,1,CB+0x58)=0x400;
    *reg(f,0,0x5a00)=0x3000;*reg(f,0,0x5030)=0x237ff;*reg(f,0,0x5034)=0x3020001;
    *reg(f,0,0x5038)=0x80000000;*reg(f,0,0x5014)=GOP;*reg(f,0,0x500c)=0x9600438;
    *reg(f,0,0x2000)=0x1000005;*reg(f,0,0x20f4)=2;*reg(f,0,SYNC)=0x180085;
    *reg(f,0,AUTO)=0x80000001;*reg(f,0,LINE)=2400;*reg(f,0,0x2018)=0x80000000;
    *reg(f,0,0x5000)=0x9600438;*reg(f,0,0x5024)=4320;
    *reg(f,0,0x5108)=*reg(f,0,0x5118)=*reg(f,0,0x5128)=0x9600438;
    *reg(f,0,0x5a10)=*reg(f,0,0x5a14)=*reg(f,0,0x5a18)=*reg(f,0,0x5a1c)=0x200000;
    *reg(f,0,0x5a20)=0x03050305;
    return f;
}
static void destroy(struct fake *f)
{
    assert(!f->locked);
    /* Model teardown is not a production free. Failed recovery assertions
     * below require retained ownership; the fake device is destroyed here. */
    for(unsigned n=0;n<f->allocations;n++)free((void *)f->allocation[n].va);
    free(f->d);free(f);
}
static void restored(struct fake *f)
{
    assert(!f->d->mapped && !f->d->pending && !f->d->manual && !f->queued);
    assert(*reg(f,1,CB)==0xe0 && *reg(f,1,CB+0x10)==0x40034072);
    assert(*reg(f,0,0x5014)==GOP && *reg(f,0,0x5000)==0x9600438 && *reg(f,0,0x5024)==4320);
    assert(*reg(f,0,AUTO)==0x80000001 && *reg(f,0,SYNC)==0x180085 && !(*reg(f,0,MISR)&0x100));
    assert(!lmi_dma_start(f->d,f->d->buffer,&f->d->first));
}
static void page_tables(struct fake *f)
{
    struct lmi_display_dma *d=f->d;
    for(unsigned n=0;n<2;n++) {
        struct lmi_frame_buffer *b=d->buffer+n;
        for(unsigned offset=0;offset<b->bytes;offset+=4096) {
            uint64_t *pte=leaf(d,b->iova+offset,0);assert(pte);
            assert((*pte&0xfffffffff000ull)==physical(f,b->pixels+offset));
            assert((*pte&(3ull<<6))==(3ull<<6) && (*pte&(1ull<<10)));
        }
        uint64_t *before=leaf(d,b->iova-4096,0),*after=leaf(d,b->iova+(uint32_t)b->bytes,0);
        assert((!before || !*before) && (!after || !*after));
    }
}
static int probe_stopping(void *context) {return ((struct fake *)context)->probe_stopping;}
static void probe_report(void *context,unsigned stage,int ok,uint32_t expected,uint32_t actual,uint64_t elapsed)
{
    struct fake *f=context;(void)ok;(void)expected;(void)actual;(void)elapsed;f->reports++;
    if(stage==f->stop_stage)f->probe_stopping=1;
}
static struct fake *setup_probe(void)
{
    struct fake *f=setup();struct lmi_dma_services io=f->d->io;free(f->d);
    struct lmi_display_probe *p=calloc(1,sizeof(*p));assert(p);f->d=&p->dma;f->d->io=io;
    p->opaque=f;p->stopping=probe_stopping;p->report=probe_report;f->model_patterns=1;
    return f;
}
static void pattern_check(struct lmi_display_probe *p,int scaled,unsigned seed)
{
    assert(lmi_display_probe_pattern(p,0,scaled,seed));
    const struct lmi_frame_buffer *b=p->dma.buffer;
    unsigned width=scaled?1125:1080,height=scaled?2436:2400,cw=scaled?25:24,ch=scaled?203:200;
    for(unsigned y=0;y<height;y++) {
        uint32_t *row=(uint32_t *)(b->pixels+(uintptr_t)y*b->pitch);
        for(unsigned cell=0;cell<45;cell++) {
            uint32_t expected=((cell+3*(y/ch)+seed)&1)?0xffd03070u:0xff20c0a0u;
            assert(row[cell*cw]==expected && row[(cell+1)*cw-1]==expected);
        }
        for(unsigned x=width;x<b->pitch/4;x++)assert(row[x]==0xff00ff00);
    }
    for(uint64_t offset=(uint64_t)height*b->pitch;offset<b->bytes;offset+=4)
        assert(*(uint32_t *)(b->pixels+offset)==0xff00ff00);
}
int main(void)
{
    struct fake *f=setup();assert(lmi_dma_prepare(f->d));page_tables(f);
    unsigned prepare_enters=f->enters;
    assert(lmi_dma_set_scaling(f->d,1));assert(lmi_dma_clean(f->d,f->d->buffer));
    uint32_t first;assert(lmi_dma_start(f->d,f->d->buffer,&first)==1);
    assert(f->queued && f->d->pending && !lmi_dma_start(f->d,f->d->buffer+1,&first));
    struct lmi_display_completion c;assert(lmi_dma_sample(f->d,&c) && !c.fault && f->d->pending);
    /* Restoration must wait out a real TE-queued transfer with LINE=0. */
    unsigned before_restore=f->enters;
    assert(lmi_dma_restore(f->d));restored(f);unsigned total_writes=f->writes;
    unsigned recovery_enters=f->enters-before_restore;
    assert(lmi_dma_restore(f->d) && f->writes==total_writes);destroy(f);
    /* Real CB4 ignores the optional ASIDPNE hint. Requesting zero works on
     * both implementations; mandatory M and every other bit remain exact. */
    for(unsigned mode=0;mode<4;mode++) {
        f=setup();f->asidpne_ignored=mode&1;
        if(mode<2) {
            assert(lmi_dma_prepare(f->d) && *reg(f,1,CB)==0x127u);
            assert(lmi_dma_set_scaling(f->d,1));
            assert(lmi_dma_start(f->d,f->d->buffer,&first)==1);
        } else {
            f->drop_translation=mode==2;f->unexpected_control=mode==3;
            assert(!lmi_dma_prepare(f->d) && !f->d->mapping_ready);
            f->drop_translation=f->unexpected_control=0;
        }
        assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    }
    /* Measured v50 bit31 readback: supported zero is requested exactly.
     * Functional enable/preload loss and unexpected control bits still refuse. */
    for(unsigned mode=0;mode<4;mode++) {
        f=setup();f->ignored_blend=1;
        assert(lmi_dma_prepare(f->d));
        f->drop_scaler_enable=mode==1;f->unexpected_scaler=mode==2;f->drop_preload=mode==3;
        unsigned starts=f->starts;
        if(!mode) {
            assert(lmi_dma_set_scaling(f->d,1));
            assert(*reg(f,0,0x5a04)==0x20036401 && *reg(f,0,0x5a20)==0x03050305);
        } else {
            assert(!lmi_dma_set_scaling(f->d,1));
            assert(f->starts==starts); /* failed config cannot issue a frame */
        }
        f->drop_scaler_enable=f->unexpected_scaler=f->drop_preload=0;
        assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    }
    /* Both measured raw global profiles are accepted without any global
     * write. Every other single-bit mutation must fail before allocation. */
    for(unsigned variant=0;variant<2;variant++) {
        uint32_t raw=variant?0x2c0406u:0x240406u;
        f=setup();*reg(f,1,0)=raw;
        assert(lmi_dma_prepare(f->d) && lmi_dma_set_scaling(f->d,1));
        assert(lmi_dma_start(f->d,f->d->buffer,&first)==1);
        assert(lmi_dma_restore(f->d) && *reg(f,1,0)==raw);restored(f);destroy(f);
        for(unsigned bit=0;bit<32;bit++)if(bit!=19) {
            f=setup();*reg(f,1,0)=raw^(1u<<bit);
            assert(!lmi_dma_prepare(f->d) && !f->writes && !f->allocations);
            assert(lmi_dma_restore(f->d));destroy(f);
        }
        f=setup();*reg(f,1,0)=raw;f->flip_global=1;
        assert(!lmi_dma_prepare(f->d) && !f->writes && !f->d->journal);
        assert(lmi_dma_restore(f->d));destroy(f);
    }
    /* The experimental desktop can select only its one pinned configuration. */
    f=setup();assert(lmi_dma_prepare(f->d));assert(lmi_dma_set_scaling(f->d,1));
    assert(*reg(f,0,0x5a20)==0x03050305u && *reg(f,0,0x5a04)==0x20036401u);
    assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    f=setup();assert(lmi_dma_prepare(f->d));unsigned original_writes=f->writes;
    assert(!lmi_dma_set_scaling(f->d,-1));
    for(int mode=2;mode<=17;mode++)assert(!lmi_dma_set_scaling(f->d,mode));
    assert(f->writes==original_writes);assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    /* Deny each gate during preparation. Every interruption can be undone. */
    for(unsigned at=1;at<=prepare_enters;at++) {
        f=setup();f->fail_enter=at;(void)lmi_dma_prepare(f->d);f->fail_enter=0;
        assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    }
    /* Interrupt every recovery gate as well, then retry the same journal. */
    for(unsigned at=1;at<=recovery_enters;at++) {
        f=setup();assert(lmi_dma_prepare(f->d) && lmi_dma_set_scaling(f->d,1));
        assert(lmi_dma_start(f->d,f->d->buffer,&first)==1);
        f->fail_enter=f->enters+at;assert(!lmi_dma_restore(f->d));
        assert(!f->d->restored && f->d->restoring);f->fail_enter=0;
        assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    }
    /* Drop each individual MMIO store across prepare, submit and restore.
     * Lost START is deliberately uncertain: no synthetic DONE/release. */
    for(unsigned at=1;at<=total_writes;at++) {
        f=setup();f->drop_write=at;
        if(lmi_dma_prepare(f->d) && lmi_dma_set_scaling(f->d,1))
            (void)lmi_dma_start(f->d,f->d->buffer,&first);
        int ok=lmi_dma_restore(f->d);f->drop_write=0;
        for(unsigned retry=0;!ok && retry<3;retry++)ok=lmi_dma_restore(f->d);
        if(ok)restored(f);
        else {
            assert(f->d->pending && !f->d->restored && f->d->restoring);
            assert(f->d->buffer[0].pixels && f->d->tables && !lmi_dma_clean(f->d,f->d->buffer));
        }
        destroy(f);
    }
    /* Reject all forms of RAM alias, bad PA, and wrapping VA before MMIO. */
    for(unsigned mode=1;mode<=12;mode++) {
        f=setup();if(mode<=9)f->pa_alias=mode;else f->va_alias=mode-9;
        assert(!lmi_dma_prepare(f->d) && !f->writes && !f->d->journal);
        assert(!lmi_dma_prepare(f->d));assert(lmi_dma_restore(f->d));destroy(f);
    }
    /* All architectural SEP encodings are irrelevant while translation is
     * disabled; installation and restoration must retain the actual value. */
    for(unsigned sep=0;sep<8;sep++) {
        f=setup();uint32_t initial=(0x40034072u&~0x38000u)|(sep<<15);
        *reg(f,1,CB+0x10)=initial;
        assert(lmi_dma_prepare(f->d) && f->d->cb_saved[1]==initial);
        assert(*reg(f,1,CB+0x10)==0x38011);
        assert(lmi_dma_set_scaling(f->d,1));
        assert(lmi_dma_start(f->d,f->d->buffer,&first)==1);
        assert(lmi_dma_restore(f->d));
        assert(*reg(f,1,CB+0x10)==initial && !f->queued && !f->d->mapped);
        assert(*reg(f,0,AUTO)==0x80000001 && *reg(f,0,0x5014)==GOP);
        destroy(f);
    }
    /* UNKNOWN initial TCR2: each bit and a dense pattern roundtrip exactly.
     * An enabled context, or other changed live state, still causes no writes. */
    for(unsigned bit=0;bit<34;bit++) {
        f=setup();uint32_t initial=bit<32?1u<<bit:bit==32?0u:0xffffffffu;
        *reg(f,1,CB+0x10)=initial;
        assert(lmi_dma_prepare(f->d) && f->d->cb_saved[1]==initial);
        assert(lmi_dma_restore(f->d) && *reg(f,1,CB+0x10)==initial);destroy(f);
    }
    f=setup();*reg(f,1,CB)|=1;
    assert(!lmi_dma_prepare(f->d) && !f->writes && !f->allocations);destroy(f);
    /* A live probe hands the same validated ownership to desktop. Failed
     * patterns still restore instead of enabling a desktop on weak evidence. */
    f=setup_probe();struct lmi_display_probe *live=(struct lmi_display_probe *)f->d;
    live->keep_active=1;assert(lmi_display_probe_run(live));
    assert(live->verified && live->frames==8 && live->stage==7 && !live->restore_ok);
    assert(live->dma.prepared && !live->dma.restored && !live->pipeline.detached);
    lmi_pipeline_stop(&live->pipeline);
    assert(lmi_pipeline_detach_after_cpu_stop(&live->pipeline)==1);restored(f);destroy(f);
    f=setup_probe();live=(struct lmi_display_probe *)f->d;live->keep_active=1;f->scaled_bad=1;
    assert(!lmi_display_probe_run(live) && !live->verified && live->restore_ok);
    restored(f);destroy(f);
    /* Wrong topology/CB ownership/scaler version must cause ZERO stores. */
    for(unsigned mode=0;mode<6;mode++) {
        f=setup();
        if(mode==0)*reg(f,0,0x5a00)=0x2004;
        if(mode==1)*reg(f,1,0x814)=0x80000000|0x820;
        if(mode==2){*reg(f,1,0x814)=0x80000001;*reg(f,1,0xc14)=4;}
        if(mode==3)*reg(f,1,CB+0x58)|=2;
        if(mode==4)*reg(f,0,0x1014)|=1u<<26;
        if(mode==5)*reg(f,0,0x1010)=DONE;
        assert(!lmi_dma_prepare(f->d) && !f->writes && !f->allocations);destroy(f);
    }
    /* A failed/unstable baseline owns only MISR: no CB/source writes needed. */
    for(unsigned mode=0;mode<2;mode++) {
        f=setup();if(mode)f->unstable=1;else f->stall=1;
        assert(!lmi_dma_prepare(f->d) && !f->d->manual && !f->d->baseline_valid);
        assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    }
    /* A stuck local TLB sync cannot enable the new context. Recovery retries. */
    f=setup();f->busy_tlb=1;assert(!lmi_dma_prepare(f->d) && !f->d->mapping_ready);
    assert(!lmi_dma_restore(f->d) && !f->d->restored);f->busy_tlb=0;
    assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    /* A real queued transfer that stalls must retain buffers and translations. */
    f=setup();assert(lmi_dma_prepare(f->d));assert(lmi_dma_start(f->d,f->d->buffer,&first)==1);
    f->stall=1;assert(!lmi_dma_restore(f->d) && f->d->mapped && f->d->pending && !f->d->restored);
    assert(!lmi_dma_validate(f->d,f->d->buffer));f->stall=0;
    assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    /* Stale DONE is not completion, nor is an unexplained extra frame. */
    f=setup();assert(lmi_dma_prepare(f->d));assert(lmi_dma_start(f->d,f->d->buffer,&first)==1);
    *reg(f,0,0x1014)|=DONE;*reg(f,0,LINE)=2400;
    assert(lmi_dma_sample(f->d,&c) && f->d->pending);
    assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    f=setup();assert(lmi_dma_prepare(f->d));assert(lmi_dma_start(f->d,f->d->buffer,&first)==1);
    pause_us(f,50);++*reg(f,0,FRAME);
    assert(lmi_dma_sample(f->d,&c) && f->d->pending);
    assert(!lmi_dma_restore(f->d) && f->d->mapped && !f->d->restored);destroy(f);
    /* The complete portable probe, with B produced while A is outstanding. */
    f=setup_probe();struct lmi_display_probe *p=(struct lmi_display_probe *)f->d;
    assert(lmi_display_probe_run(p) && p->verified && p->frames==8 && p->restore_ok);
    assert(p->reference[0]!=p->reference[1] && f->starts>=8 && f->reports==14);restored(f);
    for(unsigned scaled=0;scaled<2;scaled++)for(unsigned seed=0;seed<2;seed++)pattern_check(p,scaled,seed);
    destroy(f);
    /* A scaler signature mismatch fails the probe but still restores GOP. */
    f=setup_probe();p=(struct lmi_display_probe *)f->d;f->scaled_bad=1;
    assert(!lmi_display_probe_run(p) && !p->verified && p->restore_ok && p->frames==5);restored(f);destroy(f);
    /* At each acquisition/transfer phase, hand cleanup to the stopped-CPU
     * path; the ordinary gate cannot bypass stop on its own. */
    const unsigned stop_stages[]={1,2,3,4,10,11,12,13};
    for(unsigned n=0;n<sizeof(stop_stages)/sizeof(*stop_stages);n++) {
        f=setup_probe();p=(struct lmi_display_probe *)f->d;f->stop_stage=stop_stages[n];
        assert(!lmi_display_probe_run(p) && !p->verified && f->probe_stopping);
        f->restore_mode=1;assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    }
    printf("PASS: %u DMA protocol scenarios; no hardware/pixel validation claimed\n",scenarios);
    return 0;
}
