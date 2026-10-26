#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lmi-display-compositor.h"
#include "lmi-display-compositor-abi.h"
struct fixture {
    unsigned char fb[LMI_FB_CLASS_BYTES];
    struct lmi_compositor c;
    struct lmi_display_pipeline p;
    struct lmi_frame_buffer b[2];
    uint32_t *gop;
    unsigned shows,not_ready,stop_calls,stop_at,stop_after_show,bad_join,complete;
    uint32_t first;
};
static void sw(struct fixture *f,unsigned o,uint32_t v) {memcpy(f->fb+o,&v,4);}
static void sp(struct fixture *f,unsigned o,uintptr_t v) {memcpy(f->fb+o,&v,sizeof(v));}
static uint32_t rw(struct fixture *f,unsigned o) {uint32_t v;memcpy(&v,f->fb+o,4);return v;}
static uintptr_t rp(struct fixture *f,unsigned o) {uintptr_t v;memcpy(&v,f->fb+o,sizeof(v));return v;}
static int stopped(void *opaque) {struct fixture *f=opaque;return f->stop_at && ++f->stop_calls>=f->stop_at;}
static int ready(void *opaque,void *s) {(void)s;return !((struct fixture *)opaque)->not_ready;}
static void show(void *opaque,void *self,const unsigned char *swap,void **surfaces)
{
    struct fixture *f=opaque;(void)surfaces;assert(self==f->fb);
    f->shows++;assert(rw(f,LMI_FB_fPanelWidth)==1125 && rw(f,LMI_FB_fPanelHeight)==2436 && rw(f,LMI_FB_fRowBytes)==4544);
    assert(rp(f,LMI_FB_fColumn)==(uintptr_t)f->c.columns && rp(f,LMI_FB_fColumnWeight)==(uintptr_t)f->c.weights);
    /* Simulate the real callback touching the last logical column, joining
     * its row workers, and updating only one rectangle from the next swap. */
    f->c.columns[1124]=1124;f->c.weights[1124]=0;
    uint32_t *pixels=(uint32_t *)rp(f,LMI_FB_fBase);
    for(unsigned y=swap[0];y<(unsigned)swap[0]+2;y++)for(unsigned x=swap[1];x<(unsigned)swap[1]+3;x++)pixels[y*1136+x]=0xff000000u|swap[2];
    if(f->bad_join)sw(f,LMI_FB_fHelpersBusy,1);
    if(f->stop_after_show)f->stop_at=1;
}
static int validate(void *o,const struct lmi_frame_buffer b[2]) {(void)o;(void)b;return 1;}
static int clean(void *o,const struct lmi_frame_buffer *b) {(void)o;(void)b;return 1;}
static int start(void *o,const struct lmi_frame_buffer *b,uint32_t *first) {(void)b;struct fixture *f=o;*first=++f->first;f->complete=0;return 1;}
static int sample(void *o,struct lmi_display_completion *c)
{
    struct fixture *f=o;c->status=f->complete?0x100:0;c->frame=f->first+f->complete;
    c->line=f->complete?2400:0;c->source=f->p.buffer[f->p.scanning].iova;c->fault=0;return 1;
}
static int restore(void *o) {(void)o;return 1;}
static struct fixture *make(void)
{
    struct fixture *f=calloc(1,sizeof(*f));assert(f);
    f->gop=malloc(4320u*2400u);assert(f->gop);
    for(unsigned n=0;n<1080u*2400;n++)f->gop[n]=0xff556677;
    for(unsigned n=0;n<2;n++) {
        void *pixels=calloc(4544u*2436u,1);assert(pixels);
        f->b[n]=(struct lmi_frame_buffer){(uintptr_t)pixels,4544u*2436u,0x10000000u+0x2000000u*n,4544,1125,2436};
    }
    sp(f,LMI_FB_fBase,(uintptr_t)f->gop);sp(f,LMI_FB_fColumn,0x1234);sp(f,LMI_FB_fColumnWeight,0x5678);
    sw(f,LMI_FB_fPanelWidth,1080);sw(f,LMI_FB_fPanelHeight,2400);sw(f,LMI_FB_fRowBytes,4320);
    sw(f,LMI_FB_fWidth,1125);sw(f,LMI_FB_fHeight,2436);f->fb[LMI_FB_fGraphics]=1;
    struct lmi_compositor_services io={f,ready,stopped,show};assert(lmi_compositor_init(&f->c,f->fb,&io));
    struct lmi_display_ops ops={validate,clean,start,sample,restore};
    assert(lmi_pipeline_init(&f->p,f->b,&ops,f,2400,0x100,960000));return f;
}
static void fields(struct fixture *f)
{
    assert(rp(f,LMI_FB_fBase)==(uintptr_t)f->gop && rp(f,LMI_FB_fColumn)==0x1234 && rp(f,LMI_FB_fColumnWeight)==0x5678);
    assert(rw(f,LMI_FB_fPanelWidth)==1080 && rw(f,LMI_FB_fPanelHeight)==2400 && rw(f,LMI_FB_fRowBytes)==4320);
    for(unsigned n=0;n<1080u*2400;n++)assert(f->gop[n]==0xff556677);
}
static void destroy(struct fixture *f) {free((void *)f->b[0].pixels);free((void *)f->b[1].pixels);free(f->gop);free(f);}
int main(void)
{
    unsigned scenarios=0,n,m;uint64_t ta,tb;void *surfaces[4]={(void *)1,0,0,0};
    const unsigned char a[]={3,4,0xaa},b[]={8,9,0xbb};
    struct fixture *f=make();scenarios++;
    assert(lmi_compositor_frame(&f->c,&f->p,a,surfaces,&n,&ta)==1 && f->shows==1);fields(f);
    uint32_t *pa=(uint32_t *)f->b[n].pixels;assert(pa[3*1136+4]==0xff0000aa && pa[0]==0xff556677 && pa[1135]==0xff00ff00);
    assert(lmi_pipeline_submit(&f->p,n,ta,0)==1);
    assert(lmi_compositor_frame(&f->c,&f->p,b,surfaces,&m,&tb)==1 && m!=n && f->shows==2);fields(f);
    uint32_t *pb=(uint32_t *)f->b[m].pixels;
    assert(pb[3*1136+4]==0xff0000aa && pb[8*1136+9]==0xff0000bb);
    assert(pa[8*1136+9]==0xff556677 && f->p.state[n]==LMI_SCANNING);
    assert(!lmi_pipeline_poll(&f->p,100));f->complete=1;assert(lmi_pipeline_poll(&f->p,200)==1);
    assert(lmi_pipeline_submit(&f->p,m,tb,201)==1);f->complete=1;assert(lmi_pipeline_poll(&f->p,202)==1);
    assert(lmi_compositor_frame(&f->c,&f->p,a,surfaces,&n,&ta)==1 && f->shows==3);fields(f);
    assert(((uint32_t *)f->b[n].pixels)[8*1136+9]==0xff0000bb);destroy(f);
    f=make();scenarios++;f->not_ready=1;
    assert(!lmi_compositor_frame(&f->c,&f->p,a,surfaces,&n,&ta) && !f->shows && f->p.state[0]==LMI_FREE);fields(f);destroy(f);
    f=make();scenarios++;sw(f,LMI_FB_fWidth,750);
    assert(!lmi_compositor_frame(&f->c,&f->p,a,surfaces,&n,&ta) && !f->shows);fields(f);destroy(f);
    for(unsigned at=1;at<=2439;at+=127) {
        f=make();scenarios++;f->stop_at=at;
        assert(!lmi_compositor_frame(&f->c,&f->p,a,surfaces,&n,&ta) && !f->shows);fields(f);destroy(f);
    }
    for(unsigned mode=0;mode<2;mode++) {
        f=make();scenarios++;if(mode)f->bad_join=1;else f->stop_after_show=1;
        assert(lmi_compositor_frame(&f->c,&f->p,a,surfaces,&n,&ta)==-1 && f->shows==1 && f->p.state[n]==LMI_WRITING);fields(f);destroy(f);
    }
    printf("PASS: %u compositor ownership/partial-update/stop scenarios\n",scenarios);
}
