#include "lmi-display-direct-plan.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char swap[0x46c];
static struct lmi_direct_surface_view surfaces[4];
static void put(unsigned at,uint32_t v){memcpy(swap+at,&v,4);}
static void init(void) {
    memset(swap,0,sizeof(swap));memset(surfaces,0,sizeof(surfaces));
    surfaces[0]=(struct lmi_direct_surface_view){.allocation=0x100000000ull,.sid=42,.allocation_bytes=4544*2436,
        .width=1125,.height=2436,.pitch=4544,.format=0x42475241,.element_bytes=4};
    put(0x54,42);put(0x104,1);
    put(0x6c,1125);put(0x70,2436);put(0xcc,1125);put(0xd0,2436);
}
int main(void) {
    struct lmi_direct_plan p;unsigned checks=0;
    init();assert(lmi_direct_plan(swap,sizeof(swap),surfaces,&p));
    assert(p.pixels==surfaces[0].allocation && p.bytes==4544*2436 && p.sid==42);checks++;
    for(unsigned n=0;n<20;n++) {
        init();
        if(n==0)put(0x54,43);if(n==1)put(0x104,0);if(n==2)put(0x58,1);
        if(n==3)surfaces[1].allocation=1;if(n==4)surfaces[2].sid=1;
        if(n==5)surfaces[0].client_backed=1;if(n==6)surfaces[0].format=0x52474241;
        if(n==7)surfaces[0].planes=1;if(n==8)surfaces[0].element_bytes=3;
        if(n==9)surfaces[0].pitch=4608;if(n==10)surfaces[0].allocation_bytes--;
        if(n==11)surfaces[0].offset=surfaces[0].allocation_bytes+1;
        if(n==12)surfaces[0].allocation=UINTPTR_MAX-4095;
        if(n==13)surfaces[0].allocation+=64;if(n==14)put(0x64,1);
        if(n==15)put(0xc4,1);if(n==16)put(0x6c,1124);if(n==17)put(0xcc,1124);
        if(n==18)surfaces[0].width=1124;if(n==19)surfaces[0].height=2435;
        memset(&p,0xff,sizeof(p));assert(!lmi_direct_plan(swap,sizeof(swap),surfaces,&p));
        assert(!p.pixels && !p.bytes && !p.sid);checks++;
    }
    for(unsigned n=0;n<4;n++) {
        init();put(n<2?0x6c:0xcc,n&1?0xffffffffu:0);
        assert(lmi_direct_plan(swap,sizeof(swap),surfaces,&p));checks++;
    }
    init();assert(!lmi_direct_plan(swap,sizeof(swap)-1,surfaces,&p));checks++;
    printf("PASS: %u direct-plan eligibility/bounds cases; no DMA or runtime integration\n",checks);
}
