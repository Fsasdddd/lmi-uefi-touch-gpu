/* A650 2D copy: Mesa fd6_blitter + A6xx register XML. No CP_MEMCPY.
 * Runs under the native GPU lock, after the real producer fence and drain.
 * Command BO is read-only; a DISTINCT owned RW state page receives saved
 * application registers and four explicit completion markers. No CPU writes
 * to state or pixels while GPU work may be in flight.
 */
#include "lmi-gpu-blit-v68.h"
struct range {uint32_t reg,count;};
/* Every register written by this IB is saved/restored, including CCU mode
 * and the A650 blit ECO workaround. No unrelated draw/shader state changes. */
static const struct range ranges[]={
    {0x8400,7},{0x8c00,2},{0x8c17,4},{0x8e04,1},{0x8e07,1},
    {0xacc0,1},{0xb4c0,5}
};
static uint32_t odd(uint32_t v)
{return 1u^(__builtin_popcount(v)&1u);}
static uint32_t p7(uint32_t op,uint32_t n)
{return 0x70000000u|op<<16|n|odd(op)<<23|odd(n)<<15;}
static uint32_t p4(uint32_t reg,uint32_t n)
{return 0x40000000u|reg<<8|n|odd(reg)<<27|odd(n)<<7;}
static __attribute__((noinline)) uint32_t save_restore(uint32_t *out,uint64_t state,int restore)
{
    uint32_t n=0,offset=0;
    for(unsigned i=0;i<sizeof(ranges)/sizeof(ranges[0]);i++) {
        out[n++]=p7(restore?0x42:0x3e,3);
        out[n++]=ranges[i].reg|(ranges[i].count<<(restore?19:18));
        out[n++]=(uint32_t)(state+offset);out[n++]=(uint32_t)((state+offset)>>32);
        offset+=4*ranges[i].count;
    }
    return n;
}
static __attribute__((noinline)) uint32_t event(uint32_t *out,uint32_t kind,uint64_t state,unsigned index)
{
    uint64_t address=state+LMI_BLIT_MARKER_OFFSET+index*4;
    out[0]=p7(0x46,4);out[1]=kind;out[2]=(uint32_t)address;
    out[3]=(uint32_t)(address>>32);out[4]=0x680c0101u+index;return 5;
}
uint32_t lmi_blit_commands(uint32_t *out,uint64_t src,uint64_t dst,uint64_t state,uint32_t pitch)
{
    if(!out || !src || !dst || !state || (src|dst|state)&4095 ||
       src>=0x100000000ull || dst>=0x100000000ull || state>=0x100000000ull ||
       (pitch!=4544 && pitch!=4608))return 0;
    uint32_t n=0;
    out[n++]=p7(0x26,0);
    n+=save_restore(out+n,state,0);
    out[n++]=p7(0x12,0); /* saved registers must be in RAM before restore */
    n+=event(out+n,0x1d,state,0);n+=event(out+n,0x1c,state,1);
    out[n++]=p7(0x26,0);
    out[n++]=p7(0x46,1);out[n++]=0x19;
    out[n++]=p7(0x46,1);out[n++]=0x18;
    out[n++]=p4(0x8e07,1);out[n++]=0x18000000;
    out[n++]=p7(0x46,1);out[n++]=0x31; /* fresh source texture cache */
    out[n++]=p7(0x26,0);
    out[n++]=p4(0x8400,7);out[n++]=0x10f03000;
    out[n++]=0;out[n++]=1135u<<8;out[n++]=0;out[n++]=2435u<<8;
    out[n++]=0;out[n++]=1135u|(2435u<<16);
    out[n++]=p4(0x8c00,2);out[n++]=0x10f03000;out[n++]=0;
    out[n++]=p4(0xacc0,1);out[n++]=0xf180;
    out[n++]=p4(0xb4c0,5);out[n++]=0x500030;out[n++]=1136u|(2436u<<15);
    out[n++]=(uint32_t)src;out[n++]=(uint32_t)(src>>32);out[n++]=(pitch>>6)<<9;
    out[n++]=p4(0x8c17,4);out[n++]=0x30;
    out[n++]=(uint32_t)dst;out[n++]=(uint32_t)(dst>>32);out[n++]=4544u>>6;
    out[n++]=p7(0x26,0);
    out[n++]=p4(0x8e04,1);out[n++]=0x04100000;
    out[n++]=p7(0x2c,1);out[n++]=3;
    out[n++]=p7(0x26,0);
    n+=event(out+n,0x1d,state,2); /* drain 2D CCU writes before mode restore */
    n+=event(out+n,4,state,3);
    out[n++]=p7(0x26,0);out[n++]=p7(0x12,0);
    n+=save_restore(out+n,state,1);
    out[n++]=p7(0x26,0);
    /* Read the restored registers back into a different GPU-written range.
     * A final backend TS fence and CPU invalidation precede comparison. */
    n+=save_restore(out+n,state+LMI_BLIT_READBACK_OFFSET,0);
    out[n++]=p7(0x12,0);out[n++]=p7(0x26,0);
    return n;
}
int lmi_blit_completed(const volatile uint32_t *state)
{
    for(unsigned i=0;i<LMI_BLIT_MARKER_COUNT;i++)
        if(state[LMI_BLIT_MARKER_OFFSET/4+i]!=0x680c0101u+i)return 0;
    for(unsigned i=0;i<LMI_BLIT_REGISTER_COUNT;i++)
        if(state[i]!=state[LMI_BLIT_READBACK_OFFSET/4+i])return 0;
    return 1;
}
