#include <assert.h>
#include <stdio.h>
#include <string.h>
#define LMI_GPU_CP_CONFIG_READY
#include "lmi-gpu-cp.c"
#include "lmi-gpu-tile.c"
static unsigned char pool[81920] __attribute__((aligned(4096))),dma[81920];
static u32 gpu[0x10000],g[0xc000],s[0x4000],test,sent,ticks,invalidates,published_scratch,published_ring,verbose;
void log_line(const char *p) {if(verbose)fputs(p,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
int boot_arg(const char *key,void *out,int bytes) {assert(!strcmp(key,"lmi_gpu_tile") && bytes==4);*(u32 *)out=test==33?2:test==34?0:1;return test!=32;}
u32 lmi_gpu_firmware_crc(const void *p,u32 bytes) {
    const unsigned char *b=p;u32 c=~0u;
    for(u32 i=0;i<bytes;i++) {c^=b[i];for(u32 k=0;k<8;k++)c=(c>>1)^(0xedb88320u&-(c&1));}
    return ~c;
}
u64 io_map(u64 pa,u64 size) {
    if(pa==0x3d00000) {assert(size==sizeof(gpu));return test==5?0:(u64)gpu;}
    assert(pa==0x3da0000 && size==sizeof(s));return test==6?0:(u64)s;
}
u32 rsc_read(volatile u32 *p) {
    assert((p>=gpu && p<gpu+0x10000) || (p>=g && p<g+0xc000) || (p>=s && p<s+0x4000));return *p;
}
int cache_sync(u64 address,u32 bytes,int publish) {
    if(address==(u64)pool) {
        assert(publish && bytes==384 && published_scratch && !published_ring && !sent);
        if(test==17)return 0;
        memcpy(dma,pool,bytes);published_ring=1;return 1;
    }
    assert(address==(u64)pool+65536 && bytes==1536);
    if(publish) {
        assert(invalidates==1 && !published_scratch && !published_ring && !sent);
        const u32 *cpu=(void *)(pool+65536);
        for(u32 n=0;n<384;n++)assert(cpu[n]==(n==0?0x650c0de1:n==1?0x650c0de2:
            (n>=32 && n<64) || (n>=320 && n<352)?0xa55aa55a:0));
        if(test==16)return 0;
        memcpy(dma+65536,pool+65536,bytes);published_scratch=1;
    } else {
        invalidates++;
        if((test==15 && invalidates==1) || (test==25 && invalidates==2))return 0;
        memcpy(pool+65536,dma+65536,bytes);
    }
    return 1;
}
void rsc_write(volatile u32 *p,u32 value) {
    assert(p==gpu+0x807 && value==68 && !sent && published_scratch && published_ring);
    const u32 *cpu=(void *)(pool+65536);
    for(u32 n=64;n<320;n++)assert(cpu[n]==0); // CPU has not drawn any pixels.
    for(u32 n=2;n<5;n++)assert(cpu[n]==0);    // Nor supplied GPU fences.
    sent=value;gpu[0x807]=value;
}
static void execute_dma(void) {
    const u32 *ring=(void *)dma;u32 registers[0xc000]={0},n=19,blits=0,events=0,writes=0;
    u32 *scratch=(void *)(dma+65536);
    while(n<68) {
        u32 h=ring[n++],type=h>>28,count,op;
        if(type==4) {
            count=h&0x7f;op=(h>>8)&0x3ffff;
            assert(((h>>7)&1)==(1^__builtin_parity(count)) && ((h>>27)&1)==(1^__builtin_parity(op)));
            assert(n+count<=68);
            for(u32 j=0;j<count;j++) {
                u32 at=op+j;
                assert(at==0x8e07 || (at>=0x8405 && at<=0x8406) || (at>=0x8c2c && at<=0x8c2f) ||
                    at==0x8c00 || at==0x8400 || at==0xacc0 || at==0x8c01 ||
                    (at>=0x8c17 && at<=0x8c1a) || at==0x8e04);
                registers[at]=ring[n++];
            }
        } else {
            assert(type==7);count=h&0x3fff;op=(h>>16)&0x7f;
            assert(((h>>15)&1)==(1^__builtin_parity(count)) && ((h>>23)&1)==(1^__builtin_parity(op)));
            assert(n+count<=68);
            if(op==0x65)assert(count==1 && ring[n]==12 && n==20);
            else if(op==0x26)assert(!count);
            else if(op==0x2c) {
                assert(count==1 && ring[n]==3 && !blits++);
                assert(registers[0x8e07]==0x18000000 && registers[0x8e04]==0x04100000);
                assert(registers[0x8405]==0 && registers[0x8406]==0xf000f);
                assert(registers[0x8c00]==0x10f03080 && registers[0x8400]==registers[0x8c00]);
                assert(registers[0xacc0]==0xf180 && !registers[0x8c01]);
                assert(registers[0x8c17]==0x430 && registers[0x8c18]==0x1010100 && !registers[0x8c19] && registers[0x8c1a]==1);
                u32 pixel=(registers[0x8c2f]<<24)|(registers[0x8c2c]<<16)|(registers[0x8c2d]<<8)|registers[0x8c2e];
                for(u32 y=0;y<16;y++)for(u32 x=0;x<16;x++)scratch[64+y*16+x]=pixel;
            } else if(op==0x46) {
                assert(count==4 && blits==1 && events<2 && !registers[0x8e04]);
                assert(ring[n]==(events?4:0x1d) && ring[n+1]==0x1010008+4*events && !ring[n+2]);
                assert(ring[n+3]==0x650c0101+events);scratch[2+events]=ring[n+3];events++;
            } else {
                assert(op==0x3d && count==3 && events==2 && !writes++);
                assert(ring[n]==0x1010010 && !ring[n+1] && ring[n+2]==0x650c0de3);
            }
            n+=count;
        }
    }
    assert(n==68 && blits==1 && events==2 && writes==1);
    scratch[4]=0x650c0de3;
    if(test==20)scratch[64+113]^=1;if(test==21)scratch[32]^=1;if(test==22)scratch[351]^=1;
    if(test==23)scratch[4]=0;if(test==24)scratch[0]=0;if(test==28)scratch[2]=0;
    if(test==29)scratch[383]=1;if(test==30)scratch[1]=0;if(test==31)scratch[319]=0;
}
void delay(u32 amount,u32 unit) {
    assert(amount==100 && unit==1000 && sent==68 && ++ticks<=1000);
    if(test==18 || ticks<2)return;
    if(test==19) {s[0x9058/4]|=2;return;}
    if(test==27) {gpu[0x821]=1;return;}
    execute_dma();gpu[0x806]=68;
}
static void seed(u32 t) {
    memset(pool,0,sizeof(pool));memset(dma,0,sizeof(dma));memset(gpu,0,sizeof(gpu));memset(g,0,sizeof(g));memset(s,0,sizeof(s));
    test=t;sent=ticks=invalidates=published_scratch=published_ring=0;
    gpu[0x806]=gpu[0x807]=19;gpu[0x808]=1;gpu[0x210]=1;s[0x9058/4]=0x400;
    u32 *scratch=(void *)(dma+65536);scratch[0]=0x650c0de1;scratch[1]=0x650c0de2;
    if(t==7)gpu[0x806]=18;if(t==8)gpu[0x807]=18;if(t==9)gpu[0x808]=0;
    if(t==10)s[0x9058/4]|=2;if(t==11)scratch[0]=0;if(t==12)scratch[1]=0;
    if(t==13)scratch[100]=55;if(t==14)((u32 *)pool)[19]=1;if(t==26)gpu[0x823]=1;
}
int main(void) {
    assert(lmi_gpu_tile_canary(0x1badb002)==0x7eabe04b);
    for(u32 t=0;t<35;t++) {
        seed(t);verbose=t==0;
        int ok=lmi_gpu_tile_opt(t==1?0:(u64)pool+(t==2),t==3?81919:81920,t==4?0:g);
        assert(ok==(t==0));
        if((t>=1 && t<=17) || t==26 || t>=32)assert(!sent);else assert(sent==68);
    }
    puts("PASS: 35 tile scenarios; independently decoded DMA commands, no CPU pixels/fences, all pixels/guards/fences checked, cache ordering, explicit bootarg and bounded faults/timeouts");
}
