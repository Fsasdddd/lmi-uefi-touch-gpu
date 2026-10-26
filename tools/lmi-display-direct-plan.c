#include "lmi-display-direct-plan.h"
static uint32_t word(const unsigned char *p,unsigned at)
{
    return (uint32_t)p[at]|(uint32_t)p[at+1]<<8|(uint32_t)p[at+2]<<16|(uint32_t)p[at+3]<<24;
}
static int whole(const unsigned char *swap,unsigned at)
{
    int32_t x=(int32_t)word(swap,at),y=(int32_t)word(swap,at+4);
    int32_t w=(int32_t)word(swap,at+8),h=(int32_t)word(swap,at+12);
    /* Match the frozen drawLayer default-rectangle semantics. */
    if(w<=0 || h<=0)return 1;
    return !x && !y && w==1125 && h==2436;
}
int lmi_direct_plan(const unsigned char *swap,size_t length,const struct lmi_direct_surface_view s[4],struct lmi_direct_plan *p)
{
    if(!p)return 0;
    *p=(struct lmi_direct_plan){0};
    if(!swap || length!=0x46c || !s || !(word(swap,0x104)&1) ||
       !word(swap,0x54) || word(swap,0x54)!=s[0].sid)return 0;
    for(unsigned n=1;n<4;n++)if(word(swap,0x54+4*n) || s[n].sid || s[n].allocation)return 0;
    const struct lmi_direct_surface_view *b=s;
    /* First integration deliberately admits only the existing measured pitch
     * and ordinary kernel-owned BGRA memory, without client-address aliases. */
    if(b->client_backed || !b->allocation || b->width!=1125 || b->height!=2436 ||
       b->format!=0x42475241 || b->planes || b->element_bytes!=4 || b->pitch!=4544 ||
       b->offset>b->allocation_bytes || b->allocation_bytes>UINTPTR_MAX-b->allocation ||
       b->allocation+b->offset< b->allocation || ((b->allocation+b->offset)&4095) ||
       (uint64_t)b->pitch*b->height>b->allocation_bytes-b->offset ||
       !whole(swap,0x64) || !whole(swap,0xc4))return 0;
    p->pixels=b->allocation+b->offset;p->sid=b->sid;p->pitch=b->pitch;p->bytes=b->pitch*b->height;
    return 1;
}
