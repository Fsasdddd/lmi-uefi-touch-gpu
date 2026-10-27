#include "lmi-display-compositor.h"
#include "lmi-display-compositor-abi.h"
#define FN static LMI_PIPE_LOCAL
extern void *memcpy(void *,const void *,size_t);
static __attribute__((always_inline)) inline uint32_t word(const void *self,unsigned offset)
{return *(const uint32_t *)((const unsigned char *)self+offset);}
static __attribute__((always_inline)) inline uintptr_t pointer(const void *self,unsigned offset)
{return *(const uintptr_t *)((const unsigned char *)self+offset);}
static __attribute__((always_inline)) inline void set_word(void *self,unsigned offset,uint32_t value)
{*(uint32_t *)((unsigned char *)self+offset)=value;}
static __attribute__((always_inline)) inline void set_pointer(void *self,unsigned offset,uintptr_t value)
{*(uintptr_t *)((unsigned char *)self+offset)=value;}
FN int original_fields(const struct lmi_compositor *c)
{
    void *s=c->self;
    return pointer(s,LMI_FB_fBase)==c->original_base &&
        pointer(s,LMI_FB_fColumn)==c->original_column && pointer(s,LMI_FB_fColumnWeight)==c->original_weight &&
        word(s,LMI_FB_fPanelWidth)==1080 && word(s,LMI_FB_fPanelHeight)==2400 && word(s,LMI_FB_fRowBytes)==4320 &&
        word(s,LMI_FB_fWidth)==1125 && word(s,LMI_FB_fHeight)==2436 &&
        *((unsigned char *)s+LMI_FB_fGraphics) && !word(s,LMI_FB_fHelpersBusy);
}
int lmi_compositor_init(struct lmi_compositor *c,void *self,const struct lmi_compositor_services *io)
{
    if(!c || c->initialized || !self || !io || !io->ready || !io->stopping || !io->show)return 0;
    c->self=self;c->io=*io;c->latest=-1;
    c->original_base=pointer(self,LMI_FB_fBase);c->original_column=pointer(self,LMI_FB_fColumn);
    c->original_weight=pointer(self,LMI_FB_fColumnWeight);
    if(!c->original_base || !c->original_column || !c->original_weight || !original_fields(c))return 0;
    c->initialized=1;return 1;
}
int lmi_compositor_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *swap,void **surfaces,unsigned *index,uint64_t *ticket)
{
    if(!c || !c->initialized || !p || !p->initialized || !swap || !surfaces || !index || !ticket ||
       c->io.stopping(c->io.opaque) || !original_fields(c))return 0;
    for(unsigned layer=0;layer<4;layer++)if(surfaces[layer] && !c->io.ready(c->io.opaque,surfaces[layer]))return 0;
    int acquired=lmi_pipeline_acquire(p,ticket);if(acquired<0)return 0;
    unsigned n=(unsigned)acquired;*index=n;
    const struct lmi_frame_buffer *b=p->buffer+n;
    if(b->width!=1125 || b->height!=2436 || b->pitch!=4544 || b->bytes<4544u*2436u) {
        lmi_pipeline_cancel_frame(p,n,*ticket);return 0;
    }
    /* Preserve the previous complete composition even when this swap only
     * updates a small rectangle. Reading a scanning buffer is permitted;
     * acquire prevents writing it. Bootstrap once from the untouched GOP. */
    if(c->latest>=0) {
        if(c->latest!=(int)n)
            memcpy((void *)b->pixels,(const void *)p->buffer[c->latest].pixels,4544u*2436u);
    } else for(unsigned y=0;y<2436;y++) {
        if(c->io.stopping(c->io.opaque)) {lmi_pipeline_cancel_frame(p,n,*ticket);return 0;}
        uint32_t *out=(uint32_t *)(b->pixels+(uintptr_t)y*4544);
        const uint32_t *in=(const uint32_t *)(c->original_base+(uintptr_t)(y*2400u/2436u)*4320);
        for(unsigned x=0;x<1125;x++)out[x]=in[x*1080u/1125u];
        for(unsigned x=1125;x<1136;x++)out[x]=0xff00ff00u;
    }
    if(c->io.stopping(c->io.opaque)) {lmi_pipeline_cancel_frame(p,n,*ticket);return 0;}
    void *s=c->self;
    set_pointer(s,LMI_FB_fBase,b->pixels);set_word(s,LMI_FB_fPanelWidth,1125);
    set_word(s,LMI_FB_fPanelHeight,2436);set_word(s,LMI_FB_fRowBytes,4544);
    set_pointer(s,LMI_FB_fColumn,(uintptr_t)c->columns);set_pointer(s,LMI_FB_fColumnWeight,(uintptr_t)c->weights);
    c->io.show(c->io.opaque,s,swap,surfaces); /* consumes queue and joins every row worker */
    int ok=pointer(s,LMI_FB_fBase)==b->pixels && word(s,LMI_FB_fPanelWidth)==1125 &&
        word(s,LMI_FB_fPanelHeight)==2436 && word(s,LMI_FB_fRowBytes)==4544 &&
        pointer(s,LMI_FB_fColumn)==(uintptr_t)c->columns &&
        pointer(s,LMI_FB_fColumnWeight)==(uintptr_t)c->weights && !word(s,LMI_FB_fHelpersBusy);
    set_pointer(s,LMI_FB_fBase,c->original_base);set_word(s,LMI_FB_fPanelWidth,1080);
    set_word(s,LMI_FB_fPanelHeight,2400);set_word(s,LMI_FB_fRowBytes,4320);
    set_pointer(s,LMI_FB_fColumn,c->original_column);set_pointer(s,LMI_FB_fColumnWeight,c->original_weight);
    if(!ok || c->io.stopping(c->io.opaque) || !lmi_pipeline_complete_frame(p,n,*ticket))return -1;
    c->latest=(int)n;c->frames++;return 1;
}
