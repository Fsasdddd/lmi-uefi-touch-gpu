#define _POSIX_C_SOURCE 200112L
#include "lmi-display-fast-v62.h"
#include "lmi-display-compositor-abi.h"
#include "lmi-display-surface-abi.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define BYTES (4544u*2436u)
#define GUARD 64u
struct lmi_fast_stats *lmi_fast_state;
struct fixture {
    unsigned char fb[LMI_FB_CLASS_BYTES],surface[728],swap[0x46c];
    struct lmi_compositor c;
    struct lmi_display_pipeline p;
    uint32_t *source,*gop;
    void *allocation;
    unsigned source_pitch;
    unsigned shows,draws,not_ready,stop,stop_after_show,bad_join;
};
static struct fixture *current;
static char logged[10][256];
static unsigned log_count;
static void sw(void *p,unsigned at,uint32_t value) {memcpy((char *)p+at,&value,4);}
static void sp(void *p,unsigned at,uintptr_t value) {memcpy((char *)p+at,&value,sizeof(value));}
static uintptr_t rp(const void *p,unsigned at) {uintptr_t v;memcpy(&v,(const char *)p+at,sizeof(v));return v;}
void *IOMallocAligned(size_t n,size_t a) {void *p=0;assert(!posix_memalign(&p,a,n));return p;}
void bzero(void *p,size_t n) {memset(p,0,n);}
static int ready(void *o,void *s) {(void)s;return !((struct fixture *)o)->not_ready;}
static int stopped(void *o) {return ((struct fixture *)o)->stop;}
void lmi_fast_original_draw(void *self,void *surface,const int32_t *src,const int32_t *dst)
{
    struct fixture *f=current;(void)surface;(void)dst;assert(self==f->fb);f->draws++;
    uint32_t *out=(void *)rp(self,LMI_FB_fBase);
    int x=src[2]>0?src[0]:0,y=src[3]>0?src[1]:0;
    int w=src[2]>0?src[2]:1125,h=src[3]>0?src[3]:2436;
    for(int row=y;row<y+h;row++)memcpy(out+row*1136+x,f->source+row*(f->source_pitch/4)+x,(size_t)w*4);
}
static void show(void *o,void *self,const unsigned char *swap,void **surfaces)
{
    struct fixture *f=o;assert(self==f->fb);f->shows++; /* queue wake happens before draw */
    lmi_fast_draw(self,surfaces[0],(const int32_t *)(swap+0x64),(const int32_t *)(swap+0xc4));
    if(f->stop_after_show)f->stop=1;
    if(f->bad_join)sw(f->fb,LMI_FB_fHelpersBusy,1);
}
static int validate(void *o,const struct lmi_frame_buffer b[2]) {(void)o;(void)b;return 1;}
static int clean(void *o,const struct lmi_frame_buffer *b) {(void)o;(void)b;return 1;}
static int start(void *o,const struct lmi_frame_buffer *b,uint32_t *first) {(void)o;(void)b;*first=1;return 1;}
static int sample(void *o,struct lmi_display_completion *c) {(void)o;(void)c;return 0;}
static int restore(void *o) {(void)o;return 1;}
void lmi_fast_original_cleanup(void) {assert(current);current->stop=1;}
void loader_log_line(const char *s) {
    assert(current->stop && log_count<10 && strlen(s)<256);
    assert(!strncmp(s,"LMI_DPU_FAST ",13) || !strncmp(s,"LMI_FRAME_GUARD ",16) || !strncmp(s,"LMI_FRAME_META ",15) || !strncmp(s,"LMI_FRAME_STRIDE ",17) || !strncmp(s,"LMI_SWAP_FENCE ",15));
    strcpy(logged[log_count++],s);
}
static void source(struct fixture *f,unsigned pitch,unsigned offset)
{
    free(f->allocation);f->allocation=IOMallocAligned(offset+pitch*2436u,4096);
    f->source=(void *)((unsigned char *)f->allocation+offset);f->source_pitch=pitch;
    for(unsigned y=0;y<2436;y++)for(unsigned x=0;x<pitch/4;x++)
        f->source[y*(pitch/4)+x]=x<1125 ? 0xff000000u|((y*12347u+x*71u)&0xffffffu) : 0xa0000000u|(y<<12)|x;
    sp(f->surface,LMI_SURF_kpixels,(uintptr_t)f->allocation);
    sw(f->surface,LMI_SURF_info+0x1c,offset+pitch*2436u);
    sw(f->surface,LMI_SURF_info+0x28,pitch);sw(f->surface,LMI_SURF_info+0x2c,offset);
}
static void identical(struct fixture *f,unsigned n)
{
    const unsigned char *out=(void *)f->p.buffer[n].pixels;
    for(unsigned y=0;y<2436;y++)assert(!memcmp(out+y*4544,(unsigned char *)f->source+y*f->source_pitch,4544));
}
static struct fixture *make(void)
{
    struct fixture *f=calloc(1,sizeof(*f));assert(f);current=f;
    lmi_fast_state=calloc(1,sizeof(*lmi_fast_state));assert(lmi_fast_state);
    source(f,4544,0);f->gop=malloc(4320u*2400u);assert(f->gop);
    for(unsigned i=0;i<1080u*2400;i++)f->gop[i]=0xff556677;
    sp(f->fb,LMI_FB_fBase,(uintptr_t)f->gop);sp(f->fb,LMI_FB_fColumn,0x1234);sp(f->fb,LMI_FB_fColumnWeight,0x5678);
    sw(f->fb,LMI_FB_fPanelWidth,1080);sw(f->fb,LMI_FB_fPanelHeight,2400);sw(f->fb,LMI_FB_fRowBytes,4320);
    sw(f->fb,LMI_FB_fWidth,1125);sw(f->fb,LMI_FB_fHeight,2436);f->fb[LMI_FB_fGraphics]=1;
    struct lmi_compositor_services io={f,ready,stopped,show};assert(lmi_compositor_init(&f->c,f->fb,&io));
    struct lmi_frame_buffer b[2];
    for(unsigned i=0;i<2;i++) {void *p=calloc(1,BYTES+GUARD);assert(p);memset((char *)p+BYTES,0xa5,GUARD);b[i]=(struct lmi_frame_buffer){(uintptr_t)p,BYTES,0x10000000+0x2000000*i,4544,1125,2436};}
    struct lmi_display_ops ops={validate,clean,start,sample,restore};assert(lmi_pipeline_init(&f->p,b,&ops,f,2400,256,960000));
    sw(f->surface,LMI_SURF_sid,42);sp(f->surface,LMI_SURF_memory,1);sp(f->surface,LMI_SURF_kpixels,(uintptr_t)f->source);
    unsigned k=LMI_SURF_info;
    sw(f->surface,k+0x18,42);sw(f->surface,k+0x1c,BYTES);sw(f->surface,k+0x20,1125);sw(f->surface,k+0x24,2436);
    sw(f->surface,k+0x28,4544);sw(f->surface,k+0x30,0x42475241);sw(f->surface,k+0x40,4);
    sw(f->swap,0x54,42);sw(f->swap,0x104,1);return f;
}
static int frame(struct fixture *f,unsigned *n,uint64_t *t) {void *s[4]={f->surface,0,0,0};return lmi_fast_frame(&f->c,&f->p,f->swap,s,n,t);}
static void destroy(struct fixture *f)
{
    assert(!lmi_fast_state || !lmi_fast_state->active);
    assert(rp(f->fb,LMI_FB_fBase)==(uintptr_t)f->gop && rp(f->fb,LMI_FB_fColumn)==0x1234);
    for(unsigned n=0;n<2;n++)for(unsigned i=0;i<GUARD;i++)assert(((unsigned char *)f->p.buffer[n].pixels)[BYTES+i]==0xa5);
    free((void *)f->p.buffer[0].pixels);free((void *)f->p.buffer[1].pixels);free(f->allocation);free(f->gop);
    free(lmi_fast_state);lmi_fast_state=0;free(f);current=0;
}
int main(void)
{
    unsigned scenarios=0,n,m;uint64_t ticket;
    struct fixture *f=make();assert(frame(f,&n,&ticket)==1 && !f->draws && f->shows==1);
    assert(lmi_fast_state->frames==1 && lmi_fast_state->copies==1 && !memcmp((void *)f->p.buffer[n].pixels,f->source,BYTES));
    assert(lmi_pipeline_submit(&f->p,n,ticket,0)==1);
    f->source[2]=0xffaabbcc;assert(frame(f,&m,&ticket)==1 && m!=n && !f->draws);
    assert(((uint32_t *)f->p.buffer[n].pixels)[2]!=0xffaabbcc && ((uint32_t *)f->p.buffer[m].pixels)[2]==0xffaabbcc);
    f->p.state[n]=LMI_FREE;f->p.scanning=-1; /* fake proven completion, retain latest m */
    sw(f->swap,0x64,3);sw(f->swap,0x68,4);sw(f->swap,0x6c,2);sw(f->swap,0x70,2);
    f->source[4*1136+3]=0xff112233;f->source[2]=0xffbadbad;
    assert(frame(f,&n,&ticket)==1 && f->draws==1 && lmi_fast_state->slow==1);
    assert(((uint32_t *)f->p.buffer[n].pixels)[2]==0xffaabbcc && ((uint32_t *)f->p.buffer[n].pixels)[4*1136+3]==0xff112233);
    lmi_fast_cleanup();assert(log_count==5 && !strcmp(logged[0],"LMI_DPU_FAST 2 2 1\n") && !strcmp(logged[3],"LMI_FRAME_STRIDE 0\n"));
    assert(lmi_fast_state->sampled && lmi_fast_state->metadata[1]==((uint64_t)1125<<32|2436));
    lmi_fast_state->frames=0;lmi_fast_state->copies=10;lmi_fast_state->slow=UINT64_MAX;
    for(unsigned i=0;i<10;i++)lmi_fast_state->metadata[i]=UINT64_MAX;
    lmi_fast_state->strided=UINT64_MAX;
    for(unsigned i=0;i<10;i++)((&lmi_fast_state->fence.began)[i])=UINT64_MAX;
    lmi_fast_cleanup();assert(log_count==10 && !strcmp(logged[5],"LMI_DPU_FAST 0 10 18446744073709551615\n"));
    assert(strlen(logged[7])==225 && !strcmp(logged[8],"LMI_FRAME_STRIDE 18446744073709551615\n"));assert(strlen(logged[9])==225);destroy(f);scenarios++;
    /* Exercise both pitch transitions with the other slot actively scanning,
     * then preserve untouched pixels through a partial native draw. */
    for(unsigned mode=0;mode<2;mode++) {
        f=make();if(mode)source(f,4608,0);
        assert(frame(f,&n,&ticket)==1 && !f->draws);identical(f,n);
        assert(lmi_pipeline_submit(&f->p,n,ticket,0)==1);
        unsigned char *saved=malloc(BYTES);assert(saved);memcpy(saved,(void *)f->p.buffer[n].pixels,BYTES);
        source(f,mode?4544:4608,0);f->source[2]=0xffaabbcc;
        assert(frame(f,&m,&ticket)==1 && m!=n && !f->draws);identical(f,m);
        assert(!memcmp(saved,(void *)f->p.buffer[n].pixels,BYTES));free(saved);
        assert(lmi_fast_state->frames==2 && lmi_fast_state->copies==2 && lmi_fast_state->strided==1);
        f->p.state[n]=LMI_FREE;f->p.scanning=-1; /* model proven completion */
        sw(f->swap,0x64,3);sw(f->swap,0x68,4);sw(f->swap,0x6c,2);sw(f->swap,0x70,2);
        f->source[4*(f->source_pitch/4)+3]=0xff112233;f->source[2]=0xffbadbad;
        assert(frame(f,&n,&ticket)==1 && f->draws==1 && lmi_fast_state->slow==1);
        assert(((uint32_t *)f->p.buffer[n].pixels)[2]==0xffaabbcc && ((uint32_t *)f->p.buffer[n].pixels)[4*1136+3]==0xff112233);
        destroy(f);scenarios++;
    }
    f=make();source(f,4608,4096);
    assert(frame(f,&n,&ticket)==1 && !f->draws && lmi_fast_state->strided==1);identical(f,n);
    log_count=0;lmi_fast_cleanup();assert(log_count==5 && !strcmp(logged[3],"LMI_FRAME_STRIDE 1\n"));
    destroy(f);scenarios++;
    f=make();source(f,4608,0);f->p.state[0]=LMI_READY;f->p.state[1]=LMI_SCANNING;f->p.scanning=1;
    assert(frame(f,&n,&ticket)==0 && !f->shows && !lmi_fast_state->copies && !lmi_fast_state->active);
    assert(f->p.state[0]==LMI_READY && f->p.state[1]==LMI_SCANNING);destroy(f);scenarios++;
    for(unsigned mode=0;mode<12;mode++) {
        f=make();unsigned k=LMI_SURF_info;
        if(mode==0)sw(f->surface,k+0x30,0x52474241);
        if(mode==1)sp(f->surface,LMI_SURF_client,1);
        if(mode==2)sw(f->swap,0x58,7);
        if(mode==3)sw(f->surface,k+0x1c,BYTES-1);
        if(mode==4)sw(f->surface,k+0x18,43);
        if(mode==5)sp(f->surface,LMI_SURF_memory,0);
        if(mode==6)sw(f->surface,k+0x38,1);
        if(mode==7)sw(f->surface,k+0x40,2);
        if(mode==8)sw(f->surface,k+0x28,4608);
        if(mode==9)sw(f->swap,0xcc,1124),sw(f->swap,0xd0,2436);
        if(mode==10)sw(f->swap,0x104,0);
        if(mode==11)sw(f->surface,k+0x2c,4);
        assert(frame(f,&n,&ticket)==1 && f->draws==1 && !lmi_fast_state->copies && lmi_fast_state->slow==1);
        destroy(f);scenarios++;
    }
    for(unsigned mode=0;mode<3;mode++) {
        f=make();if(mode==0)f->not_ready=1;if(mode==1)f->stop_after_show=1;if(mode==2)f->bad_join=1;
        assert(frame(f,&n,&ticket)==(mode?-1:0));assert(f->c.latest==-1 && f->shows==(mode?1u:0u));
        assert(lmi_fast_state->frames==0 && !lmi_fast_state->active);destroy(f);scenarios++;
    }
    f=make();void *surfaces[4]={f->surface,f->surface,0,0};
    assert(lmi_fast_frame(&f->c,&f->p,f->swap,surfaces,&n,&ticket)==1 && f->draws==1 && !lmi_fast_state->copies);
    destroy(f);scenarios++;
    printf("PASS: %u full/partial/scanout/queue/fence/error/native-draw scenarios\n",scenarios);
}
