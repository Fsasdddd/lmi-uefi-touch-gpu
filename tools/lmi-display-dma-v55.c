#include "lmi-display-dma.h"
#ifdef LMI_PIPELINE_NATIVE
#define DMA_RO __attribute__((section("__TEXT_EXEC,__lmi_ro")))
#else
#define DMA_RO
#endif
#define FN static LMI_PIPE_LOCAL
#define CB 0x84000u
#define GOP 0x9c000000u
#define FSR_FAULT 0xc00001feu
#define SYNC 0x6ba88u
#define AUTO 0x6bab4u
#define FRAME 0x6b8acu
#define LINE 0x6bab0u
#define MISR 0x6b980u
#define DONE 0x100u
/* ASIDPNE (bit12) is an optional broadcast-maintenance hint. We use
 * local TLBI/SYNC, request the defined zero value and verify all bits exactly.
 * v48 wrote 0x1127 but real CB4 returned 0x127, refusing every desktop frame. */
#define SCTLR_TRANSLATE 0x127u
#define TE 0x100000u
#define TIMEOUT 960000ull
static const uint32_t cb_offset[] DMA_RO={0,0x10,0x20,0x24,0x28,0x2c,0x30,0x38,0x3c};
static const uint32_t scale_offset[] DMA_RO={
    0x5000,0x5008,0x5024,0x5100,0x5104,0x5108,0x5110,0x5114,0x5118,
    0x5120,0x5124,0x5128,0x5a90,0x5a94,0x5a98,0x5a9c,0x5a10,0x5a14,
    0x5a18,0x5a1c,0x5a20,0x5a40,0x5a44,0x5a48,0x5a04
};
static const uint32_t scale_expected[] DMA_RO={
    0x9600438,0,4320,0,0,0x9600438,0,0,0x9600438,0,0,0x9600438,
    0,0,0,0,0x200000,0x200000,0x200000,0x200000,0x03050305,0,0,0,0
};
FN __attribute__((noinline)) uint32_t rd(struct lmi_display_dma *d,unsigned space,uint32_t offset)
{return d->io.read(d->io.opaque,space,offset);}
FN __attribute__((noinline)) void wr(struct lmi_display_dma *d,unsigned space,uint32_t offset,uint32_t value)
{d->io.write(d->io.opaque,space,offset,value);}
static __attribute__((always_inline)) inline int enter(struct lmi_display_dma *d,uint64_t *flags)
{return d->io.enter(d->io.opaque,flags);}
static __attribute__((always_inline)) inline void leave(struct lmi_display_dma *d,uint64_t flags)
{d->io.leave(d->io.opaque,flags);}
static __attribute__((always_inline)) inline uint64_t tick(struct lmi_display_dma *d) {return d->io.ticks(d->io.opaque);}
FN int own_page(struct lmi_display_dma *d,uint64_t pa)
{
    if(!pa || pa>>36 || (pa&4095) ||
       (pa>=GOP && pa<(uint64_t)GOP+((4320u*2400+4095u)&~4095u)))return 0;
    unsigned slot=(unsigned)((pa>>12)*2654435761u)&8191;
    for(unsigned n=0;n<8192;n++,slot=(slot+1)&8191) {
        if(d->owned_pages[slot]==pa)return 0;
        if(!d->owned_pages[slot]) {d->owned_pages[slot]=pa;return 1;}
    }
    return 0;
}
FN int valid_range(uintptr_t address,size_t size)
{return address && !(address&16383) && size<=UINTPTR_MAX-address;}
FN int overlap(uintptr_t a,size_t as,uintptr_t b,size_t bs)
{return a<b+bs && b<a+as;}
FN int faults(struct lmi_display_dma *d)
{return (rd(d,1,CB+0x58)&FSR_FAULT) || rd(d,1,0x48) || (rd(d,0,0x1014)&(1u<<26));}
static const uint32_t profile_scalar[][2] DMA_RO={
    {0x1000020,0x4c017e57},
    {0x1000024,0x6000004a},
    {0x1000028,0x5111},
    {0x1000810,0x84020820},
    {0x1000c10,0x4},
    {0x1001010,0x1f000},
    {0x1001810,0x1},
    {0x5a00,0x3000},
    {0x5030,0x237ff},
    {0x5034,0x3020001},
    {0x5038,0x80000000},
    {0x5170,0x0},
    {0x5014,0x9c000000},
    {0x500c,0x9600438},
    {0x5010,0x0},
    {0x2000,0x1000005},
    {0x20f4,0x2},
    {0x6ba5c,0x0},
    {0x6ba88,0x180085},
    {0x6bab4,0x80000001},
};
FN int profile(struct lmi_display_dma *d)
{
    /* Two exact boot profiles measured on this same device. Bit19 is not
     * defined by our vendor/architectural headers; do not assign semantics,
     * clear it, or ignore any other bits. Never write global sCR0. The
     * selected raw value must remain unchanged across memory preparation;
     * translation and pixel equivalence still require the full live proof. */
    uint32_t global=rd(d,1,0);
    if(global!=0x240406u && global!=0x2c0406u)return 0;
    for(unsigned n=0;n<sizeof(profile_scalar)/sizeof(profile_scalar[0]);n++) {
        uint32_t key=profile_scalar[n][0];
        if(rd(d,key>>24,key&0xffffff)!=profile_scalar[n][1])return 0;
    }
    if(faults(d) || (rd(d,0,0x1010)&DONE) || (rd(d,0,MISR)&0x100))return 0;
    /* Unique coverage is insufficient if an unrelated stream shares CB4. */
    for(unsigned n=0;n<87;n++) {
        uint32_t smr=rd(d,1,0x800+4*n),s2cr=rd(d,1,0xc00+4*n);
        if(!(smr&0x80000000) || n==4)continue;
        if(((s2cr>>16)&3)==0 && (s2cr&255)==4)return 0;
        uint32_t mask=(smr>>16)&0x7fff,sid=smr&0x7fff;
        for(unsigned i=0;i<4;i++) {
            uint32_t stream=0x820+(i&1)*2+(i>>1)*0x400;
            if(!((sid^stream)&~mask))return 0;
        }
    }
    /* TCR2 has an UNKNOWN reset value (IHI0062D.c 16.5.39). It is inactive
     * with SCTLR.M=0, required above. Never gate on its boot residue: save
     * exact bits, replace it while quiet, invalidate TLB, then enable M.
     * Restoration writes and checks the original value before auto refresh. */
    for(unsigned n=0;n<9;n++)if(n!=1 && rd(d,1,CB+cb_offset[n])!=(n?0u:0xe0u))return 0;
    for(unsigned n=0;n<25;n++)if(rd(d,0,scale_offset[n])!=scale_expected[n])return 0;
    return (int)global;
}
FN uint64_t *table_child(struct lmi_display_dma *d,uint64_t *entry,int create)
{
    if(!*entry && create) {
        if(d->pages>=32)return 0;
        unsigned n=d->pages++;
        *entry=d->physical[n]|3ull;
    }
    if((*entry&3)!=3)return 0;
    for(unsigned n=1;n<d->pages;n++)if(*entry==(d->physical[n]|3ull))return (uint64_t *)(d->tables+4096*n);
    return 0;
}
FN uint64_t *leaf(struct lmi_display_dma *d,uint32_t iova,int create)
{
    uint64_t *root=(uint64_t *)d->tables;
    uint64_t *l2=table_child(d,root+(iova>>30),create);
    if(!l2)return 0;
    uint64_t *l3=table_child(d,l2+((iova>>21)&511),create);
    return l3?l3+((iova>>12)&511):0;
}
FN int build_mapping(struct lmi_display_dma *d,uint32_t iova,uintptr_t pixels,uint32_t bytes,int identity)
{
    uint32_t size=(bytes+4095u)&~4095u;
    if(!size || iova<4096 || (uint64_t)iova+size+4096>0x100000000ull ||
       (uint64_t)pixels+size<pixels)return 0;
    for(uint32_t offset=0;offset<size;offset+=4096) {
        uint64_t pa=identity?(uint64_t)iova+offset:d->io.physical(d->io.opaque,pixels+offset);
        uint64_t *pte=leaf(d,iova+offset,1);
        if(!pa || pa>>36 || (pa&4095) || !pte || *pte || (!identity && !own_page(d,pa)))return 0;
        *pte=pa|3ull|(3ull<<6)|(2ull<<8)|(1ull<<10)|(1ull<<11)|(1ull<<53)|(1ull<<54);
    }
    for(uint32_t offset=0;offset<size;offset+=4096) {
        uint64_t pa=identity?(uint64_t)iova+offset:d->io.physical(d->io.opaque,pixels+offset);
        uint64_t *pte=leaf(d,iova+offset,0);
        uint64_t expected=pa|3ull|(3ull<<6)|(2ull<<8)|(1ull<<10)|(1ull<<11)|(1ull<<53)|(1ull<<54);
        if(!pte || *pte!=expected)return 0;
    }
    uint64_t *before=leaf(d,iova-4096,0),*after=leaf(d,iova+size,0);
    return (!before || !*before) && (!after || !*after);
}
FN int allocate_buffers(struct lmi_display_dma *d)
{
    /* A failed allocation is not retryable on this owner; never lose pointers
     * by restarting initialization. No hardware has been touched at this point. */
    d->allocated=1;
    d->tables=d->io.allocate(d->io.opaque,LMI_DMA_TABLE_BYTES,16384);
    if(!valid_range(d->tables,LMI_DMA_TABLE_BYTES) ||
       overlap(d->tables,LMI_DMA_TABLE_BYTES,(uintptr_t)d,sizeof(*d)))return 0;
    for(unsigned n=0;n<32;n++) {
        d->physical[n]=d->io.physical(d->io.opaque,d->tables+n*4096);
        if(!own_page(d,d->physical[n]))return 0;
    }
    for(unsigned n=0;n<LMI_DMA_TABLE_BYTES/8;n++)((uint64_t *)d->tables)[n]=0;
    d->pages=1;
    if(!build_mapping(d,GOP,0,4320u*2400,1))return 0;
    for(unsigned n=0;n<2;n++) {
        struct lmi_frame_buffer *b=d->buffer+n;
        b->pixels=d->io.allocate(d->io.opaque,LMI_DMA_BUFFER_BYTES,16384);
        b->bytes=LMI_DMA_BUFFER_BYTES;b->pitch=4544;b->width=1125;b->height=2436;
        b->iova=0x10000000u+n*0x2000000u;
        if(!valid_range(b->pixels,LMI_DMA_BUFFER_BYTES) ||
           overlap(b->pixels,LMI_DMA_BUFFER_BYTES,(uintptr_t)d,sizeof(*d)) ||
           overlap(b->pixels,LMI_DMA_BUFFER_BYTES,d->tables,LMI_DMA_TABLE_BYTES) ||
           (n && overlap(b->pixels,LMI_DMA_BUFFER_BYTES,d->buffer[0].pixels,LMI_DMA_BUFFER_BYTES)) ||
           !build_mapping(d,b->iova,b->pixels,LMI_DMA_BUFFER_BYTES,0))return 0;
    }
    /* Cache all page translations once. No per-frame pmap walk or TLB churn. */
    d->io.clean(d->io.opaque,d->tables,LMI_DMA_TABLE_BYTES);return 1;
}
FN int idle(struct lmi_display_dma *d)
{
    uint64_t began=tick(d);
    do {
        uint64_t flags;if(!enter(d,&flags))return 0;
        uint32_t line=rd(d,0,LINE)&0xffff;
        leave(d,flags);
        if(!line || line>=2400)return 1;
        d->io.pause(d->io.opaque,50);
    }while(tick(d)-began<TIMEOUT);
    return 0;
}
FN int tlb_sync(struct lmi_display_dma *d)
{
    uint64_t flags;if(!enter(d,&flags))return 0;
    wr(d,1,CB+0x610,4);wr(d,1,CB+0x7f0,0);leave(d,flags);
    uint64_t began=tick(d);
    do {
        if(!enter(d,&flags))return 0;
        uint32_t busy=rd(d,1,CB+0x7f4)&1;leave(d,flags);
        if(!busy)return 1;
        d->io.pause(d->io.opaque,10);
    }while(tick(d)-began<192000ull);
    return 0;
}
FN int wait_frame(struct lmi_display_dma *d,uint32_t first,int automatic,uint32_t *signature)
{
    uint64_t began=tick(d);
    do {
        uint64_t flags;if(!enter(d,&flags))return 0;
        uint32_t frames=rd(d,0,FRAME)-first,line=rd(d,0,LINE)&0xffff;
        uint32_t done=rd(d,0,0x1014)&DONE,misr=rd(d,0,MISR);
        int bad=faults(d);uint32_t crc=rd(d,0,MISR+4),source=rd(d,0,0x5014);leave(d,flags);
        if(bad || (!automatic && frames>1))return 0;
        uint32_t expected=automatic?d->saved_source:d->current_source;
        if(source!=expected)return 0;
        if(frames>=(automatic?2u:1u) && line>=2400 && (automatic || done) && (misr&0x300)==0x300) {
            if(signature)*signature=crc;return 1;
        }
        d->io.pause(d->io.opaque,50);
    }while(tick(d)-began<(automatic?1920000ull:TIMEOUT));
    return 0;
}
FN int send_gop(struct lmi_display_dma *d,uint32_t *signature)
{
    uint64_t flags;if(!enter(d,&flags))return 0;
    wr(d,0,0x1018,DONE);
    if((rd(d,0,0x1014)&DONE) || rd(d,0,0x5014)!=d->saved_source ||
       rd(d,0,AUTO)!=1 || rd(d,0,SYNC)!=d->saved_sync) {leave(d,flags);return 0;}
    d->first=rd(d,0,FRAME);d->current_source=d->saved_source;d->pending=1;
    wr(d,0,0x201c,1);leave(d,flags);
    if(!wait_frame(d,d->first,0,signature))return 0;
    d->pending=0;return 1;
}
int lmi_dma_prepare(struct lmi_display_dma *d)
{
    /* The whole owner, including its physical-alias set, starts zeroed. */
    if(!d || d->allocated || d->journal || d->prepared || d->restoring || d->restored ||
       !d->io.read || !d->io.write || !d->io.enter || !d->io.leave ||
       !d->io.allocate || !d->io.physical || !d->io.clean || !d->io.ticks || !d->io.pause)return 0;
    uint64_t flags;if(!enter(d,&flags))return 0;
    int ok=profile(d);leave(d,flags);if(!ok || !allocate_buffers(d))return 0;
    if(!enter(d,&flags))return 0;
    if(profile(d)!=ok) {leave(d,flags);return 0;}
    for(unsigned n=0;n<9;n++)d->cb_saved[n]=rd(d,1,CB+cb_offset[n]);
    for(unsigned n=0;n<25;n++)d->scale_saved[n]=rd(d,0,scale_offset[n]);
    d->saved_source=rd(d,0,0x5014);d->saved_flush=rd(d,0,0x2018);
    d->saved_sync=rd(d,0,SYNC);d->saved_auto=rd(d,0,AUTO);d->saved_misr=rd(d,0,MISR);
    d->journal=1;d->misr_owned=1;
    wr(d,0,MISR,1u<<10);wr(d,0,MISR,0x81000101);
    uint32_t first=rd(d,0,FRAME);leave(d,flags);
    uint32_t before,again;
    if(!wait_frame(d,first,1,&before))return 0;
    if(!enter(d,&flags))return 0;
    first=rd(d,0,FRAME);leave(d,flags);
    if(!wait_frame(d,first,1,&again) || before!=again)return 0;
    d->baseline=before;d->baseline_valid=1;
    if(!enter(d,&flags))return 0;
    d->manual=1;wr(d,0,SYNC,d->saved_sync&~TE);wr(d,0,AUTO,d->saved_auto&~0x80000000u);leave(d,flags);
    if(!idle(d) || !enter(d,&flags))return 0;
    wr(d,0,SYNC,d->saved_sync);wr(d,0,0x1018,DONE);
    first=rd(d,0,FRAME);leave(d,flags);
    d->io.pause(d->io.opaque,50000);
    if(!enter(d,&flags))return 0;
    ok=rd(d,0,FRAME)==first && !(rd(d,0,0x1014)&DONE) && rd(d,0,AUTO)==1 && rd(d,0,SYNC)==d->saved_sync;
    if(!ok){leave(d,flags);return 0;}
    d->mapped=1;
    uint64_t root=d->physical[0]|(4ull<<48);
    uint32_t install[9]={0xe0,0x38011,(uint32_t)root,(uint32_t)(root>>32),0,0,0x803519,0xf404ff44,0};
    for(unsigned n=0;n<9;n++)wr(d,1,CB+cb_offset[n],install[n]);
    ok=1;
    for(unsigned n=0;n<9;n++)if((rd(d,1,CB+cb_offset[n])^install[n])&(n==1?~0x60u:~0u))ok=0;
    leave(d,flags);if(!ok || !tlb_sync(d) || !enter(d,&flags))return 0;
    wr(d,1,CB,SCTLR_TRANSLATE);ok=rd(d,1,CB)==SCTLR_TRANSLATE;leave(d,flags);
    if(!ok)return 0;
    d->mapping_ready=1;
    if(!send_gop(d,&again) || again!=d->baseline)return 0;
    d->prepared=1;return 1;
}
int lmi_dma_set_scaling(struct lmi_display_dma *d,int enabled)
{
    if(!d || (enabled!=0 && enabled!=1) || !d->prepared || d->restoring || d->pending || !idle(d))return 0;
    struct lmi_qseed_plan plan;
    if(enabled && !lmi_qseed_configure_plan(&plan,0x3000,4544))return 0;
    if(enabled){plan.write[20].value=0x03050305u;plan.write[24].value|=1u<<13;}
    uint64_t flags;if(!enter(d,&flags))return 0;
    if(faults(d) || rd(d,0,AUTO)!=1 || rd(d,1,CB)!=SCTLR_TRANSLATE){leave(d,flags);return 0;}
    d->scaled=enabled!=0;d->source_owned=1;
    for(unsigned n=0;n<25;n++) {
        uint32_t value=enabled?plan.write[n].value:d->scale_saved[n];
        if(!enabled && n==2)value=4544; /* native reference uses the same owned pitch */
        wr(d,0,scale_offset[n],value);
    }
    int ok=1;
    for(unsigned n=0;n<25;n++) {
        uint32_t value=enabled?plan.write[n].value:d->scale_saved[n];
        if(!enabled && n==2)value=4544;
        if(enabled && plan.write[n].offset!=scale_offset[n])ok=0;
        if(rd(d,0,scale_offset[n])!=value)ok=0;
    }
    leave(d,flags);return ok;
}
int lmi_dma_validate(void *context,const struct lmi_frame_buffer b[2])
{
    struct lmi_display_dma *d=context;if(!d || !d->prepared || d->restoring || d->restored || !b)return 0;
    for(unsigned n=0;n<2;n++)if(b[n].pixels!=d->buffer[n].pixels || b[n].iova!=d->buffer[n].iova ||
        b[n].bytes!=d->buffer[n].bytes || b[n].pitch!=4544 || b[n].width!=1125 || b[n].height!=2436)return 0;
    return 1;
}
int lmi_dma_clean(void *context,const struct lmi_frame_buffer *b)
{
    struct lmi_display_dma *d=context;if(!d || !d->prepared || d->restoring || !b)return 0;
    if(b!=d->buffer && b!=d->buffer+1) {
        /* The portable pipeline holds descriptor copies. */
        if(!((b->pixels==d->buffer[0].pixels && b->iova==d->buffer[0].iova) ||
             (b->pixels==d->buffer[1].pixels && b->iova==d->buffer[1].iova)))return 0;
    }
    if(b->bytes!=LMI_DMA_BUFFER_BYTES || b->pitch!=4544)return 0;
    d->io.clean(d->io.opaque,b->pixels,(size_t)b->bytes);return 1;
}
int lmi_dma_start(void *context,const struct lmi_frame_buffer *b,uint32_t *first)
{
    struct lmi_display_dma *d=context;
    if(!d || !b || !first || !d->prepared || d->restoring || d->pending)return 0;
    if(!((b->iova==d->buffer[0].iova && b->pixels==d->buffer[0].pixels) ||
         (b->iova==d->buffer[1].iova && b->pixels==d->buffer[1].pixels)))return 0;
    uint64_t flags;if(!enter(d,&flags))return 0;
    uint32_t line=rd(d,0,LINE)&0xffff;
    if(faults(d) || rd(d,0,AUTO)!=1 || rd(d,0,SYNC)!=d->saved_sync ||
       rd(d,1,CB)!=SCTLR_TRANSLATE || (rd(d,0,0x1010)&DONE) || (line && line<2400)) {leave(d,flags);return -1;}
    d->source_owned=1;d->current_source=b->iova;
    wr(d,0,0x5014,b->iova);wr(d,0,0x2018,1);wr(d,0,0x1018,DONE);
    int valid=rd(d,0,0x5014)==b->iova && !(rd(d,0,0x1014)&DONE);
    d->first=rd(d,0,FRAME);*first=d->first;
    if(valid) {d->pending=1;wr(d,0,0x201c,1);}
    leave(d,flags);return valid?1:-1;
}
int lmi_dma_sample(void *context,struct lmi_display_completion *c)
{
    struct lmi_display_dma *d=context;if(!d || !c || !d->prepared || d->restoring)return 0;
    uint64_t flags;if(!enter(d,&flags))return 0;
    c->status=rd(d,0,0x1014);c->frame=rd(d,0,FRAME);c->line=rd(d,0,LINE)&0xffff;c->source=rd(d,0,0x5014);
    c->fault=faults(d) || rd(d,0,AUTO)!=1 || rd(d,0,SYNC)!=d->saved_sync || rd(d,1,CB)!=SCTLR_TRANSLATE || (rd(d,0,0x1010)&DONE);
    if(!c->fault && (c->status&DONE) && c->frame-d->first==1 && c->line>=2400 && c->source==d->current_source)d->pending=0;
    leave(d,flags);return 1;
}
uint32_t lmi_dma_signature(struct lmi_display_dma *d)
{
    uint64_t flags;if(!d || !enter(d,&flags))return 0;
    uint32_t value=rd(d,0,MISR+4);leave(d,flags);return value;
}
int lmi_dma_restore(void *context)
{
    struct lmi_display_dma *d=context;if(!d)return 0;
    if(!d->journal || d->restored)return 1;
    /* Caller has stopped every presenter/writer. Once recovery begins, no
     * callback may restart a desktop transfer, even after a failed recovery. */
    d->restoring=1;d->prepared=0;
    uint64_t flags;
    /* A queued CTL_START may still be waiting for TE with LINE=0. Do not
     * disable TE first or mistake that zero for completed/idle DMA. */
    if(d->pending) {
        if(!wait_frame(d,d->first,0,0))return 0;
        d->pending=0;
    }
    int ok=1;
    if(d->manual) {
        if(!d->baseline_valid || !enter(d,&flags))return 0;
        wr(d,0,SYNC,d->saved_sync&~TE);wr(d,0,AUTO,1);
        ok=rd(d,0,SYNC)==(d->saved_sync&~TE) && rd(d,0,AUTO)==1;
        uint32_t first=rd(d,0,FRAME);leave(d,flags);
        if(!ok || !idle(d))return 0;
        d->io.pause(d->io.opaque,50000);
        if(!enter(d,&flags))return 0;
        if(rd(d,0,FRAME)!=first || rd(d,0,AUTO)!=1 ||
           rd(d,0,SYNC)!=(d->saved_sync&~TE)) {leave(d,flags);return 0;}
        for(unsigned n=0;n<25;n++)wr(d,0,scale_offset[n],d->scale_saved[n]);
        wr(d,0,0x5014,d->saved_source);wr(d,0,0x2018,1);
        for(unsigned n=0;n<25;n++)ok&=rd(d,0,scale_offset[n])==d->scale_saved[n];
        ok&=rd(d,0,0x5014)==d->saved_source;
        wr(d,0,SYNC,d->saved_sync);leave(d,flags);
        if(!ok)return 0;
        uint32_t crc=0;
        /* A fully installed identity mapping must show GOP before removal.
         * A partial CB installation never started an owned-buffer transfer;
         * restore it while quiet instead of attempting DMA through it. */
        if(d->mapped && d->mapping_ready && d->source_owned &&
           (!send_gop(d,&crc) || crc!=d->baseline))return 0;
        if(d->mapped) {
            if(!enter(d,&flags))return 0;
            wr(d,0,SYNC,d->saved_sync&~TE);
            ok=rd(d,0,SYNC)==(d->saved_sync&~TE) && rd(d,0,AUTO)==1;
            if(!ok){leave(d,flags);return 0;}
            d->mapping_ready=0;
            wr(d,1,CB,0xe0);ok=rd(d,1,CB)==0xe0;leave(d,flags);
            if(!ok || !tlb_sync(d) || !enter(d,&flags))return 0;
            for(unsigned n=1;n<9;n++)wr(d,1,CB+cb_offset[n],d->cb_saved[n]);
            wr(d,1,CB,d->cb_saved[0]);
            for(unsigned n=0;n<9;n++)ok&=rd(d,1,CB+cb_offset[n])==d->cb_saved[n];
            if(!ok){leave(d,flags);return 0;}
            d->mapped=0;
            wr(d,0,SYNC,d->saved_sync);leave(d,flags);
        }
        /* Prove bypass output before automatic refresh resumes. A failed
         * proof retains both buffers and the journal for a later retry. */
        if(!send_gop(d,&crc) || crc!=d->baseline || !enter(d,&flags))return 0;
        wr(d,0,SYNC,d->saved_sync&~TE);wr(d,0,AUTO,d->saved_auto);wr(d,0,SYNC,d->saved_sync);
        ok=rd(d,0,AUTO)==d->saved_auto && rd(d,0,SYNC)==d->saved_sync;
        first=rd(d,0,FRAME);leave(d,flags);
        if(!ok || !wait_frame(d,first,1,&crc) || crc!=d->baseline)return 0;
        d->manual=0;d->source_owned=0;d->scaled=0;
    }
    if(d->mapped || d->pending || !enter(d,&flags))return 0;
    /* If acquisition failed before a baseline was captured, MISR is the only
     * owned hardware state. Never require a nonexistent signature to undo it. */
    if(d->misr_owned) {
        wr(d,0,MISR,1u<<10);wr(d,0,MISR,d->saved_misr&0x8f0001ffu);
        ok&=(rd(d,0,MISR)&0x8f0001ffu)==(d->saved_misr&0x8f0001ffu);
        if(ok)d->misr_owned=0;
    }
    /* CTL_FLUSH is a command, not saved state. Replaying its initial value
     * could flush unrelated pipes; restoration flushes only our VIG0 above. */
    d->restored=ok;d->prepared=0;leave(d,flags);return ok;
}
