#include <assert.h>
#include <stdio.h>
#include <string.h>
#define LMI_GPU_CP_CONFIG_READY
#include "lmi-gpu-cp.c"
#include "lmi-gpu-unsecure.c"
static unsigned char pool[81920] __attribute__((aligned(4096))),dma[81920];
static u32 g[0xc000],s[0x4000],gpu[0x10000],scenario,sent,publishes,invalidates,ticks,verbose,clock_writes,clock_settled,pending_clock;
static u32 address_writes,address_settled;
void log_line(const char *p) {if(verbose)fputs(p,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
u64 io_map(u64 a,u64 bytes) {
    if(a==0x3d00000) {assert(bytes==sizeof(gpu));return scenario==5?0:(u64)gpu;}
    assert(a==0x3da0000 && bytes==sizeof(s));return scenario==6?0:(u64)s;
}
u32 rsc_read(volatile u32 *p) {
    assert((p>=g && p<g+0xc000) || (p>=s && p<s+0x4000) || (p>=gpu && p<gpu+0x10000));return *p;
}
int cache_sync(u64 address,u32 bytes,int publish) {
    assert(bytes==128);
    if(publish) {
        assert(address==(u64)pool && sent!=19);publishes++;
        if((scenario==18 && publishes==1) || (scenario==21 && publishes==2))return 0;
        memcpy(dma,pool,bytes);
    } else {
        assert(address==(u64)pool+65536);invalidates++;
        if((scenario==17 && invalidates==1) || (scenario==25 && invalidates==2))return 0;
        memcpy(pool+65536,dma+65536,bytes);
    }
    return 1;
}
void rsc_write(volatile u32 *p,u32 v) {
    for(u32 n=1;n<11;n++)if(p==gpu+diag_words[n]) {
        assert(!sent && !publishes && !invalidates && !clock_writes && v==1);
        address_writes++;
        if(scenario!=33 && !(scenario==32 && n==1))*p=v;
        return;
    }
    if(p==g+BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4) {
        assert(!sent && !publishes && !clock_writes && v==(*p|1));clock_writes++;
        if(scenario==31)pending_clock=v;
        else if(scenario!=28)*p=v;return;
    }
    assert(p==gpu+0x807 && (v==15 || v==19));
    const u32 *d=(void *)dma;
    assert(d[13]==0x70e60001 && d[14]==0);
    if(v==15) {assert(!sent && publishes==1 && gpu[0x806]==13);for(u32 n=15;n<19;n++)assert(!d[n]);}
    else {assert(sent==15 && gpu[0x806]==15 && publishes==2);assert(d[15]==0x703d8003 && d[16]==0x1010004 && !d[17] && d[18]==0x650c0de2);}
    assert(((u32 *)(pool+65536))[1]==0);sent=v;ticks=0;*p=v;
}
void delay(u32 amount,u32 unit) {
    if(address_writes && !address_settled) {
        assert(address_writes==10 && amount==100 && unit==1000 && !sent && !publishes && !clock_writes);
        address_settled=1;
        if(scenario==33)for(u32 n=1;n<11;n++)gpu[diag_words[n]]=1;
        if(scenario==34)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
        return;
    }
    if(clock_writes && !clock_settled) {
        assert(amount==100 && unit==1000 && !sent && !publishes && !invalidates);
        clock_settled=1;
        if(scenario==31) {assert(!g[BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4] && pending_clock==1);g[BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4]=pending_clock;}
        if(scenario==42)gpu[0xae]=0;
        if(scenario==43)g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=0x10;
        return;
    }
    assert(amount==100 && unit==1000 && ++ticks<=1000 && (sent==15 || sent==19 || (!sent && scenario==27)));
    if(!sent)return;
    if((scenario==19 && sent==15) || (scenario==22 && sent==19) || ticks<2)return;
    if(scenario==20 && sent==15) {s[0x9058/4]|=2;return;}
    gpu[0x806]=sent;
    if(sent==19) {
        ((u32 *)(dma+65536))[1]=scenario==23?0:0x650c0de2;
        if(scenario==24)((u32 *)(dma+65536))[0]=0;
    }
}
static void seed(u32 n) {
    memset(pool,0,sizeof(pool));memset(dma,0,sizeof(dma));memset(g,0,sizeof(g));memset(s,0,sizeof(s));memset(gpu,0,sizeof(gpu));
    scenario=n;sent=publishes=invalidates=ticks=clock_writes=clock_settled=pending_clock=0;
    address_writes=address_settled=0;gpu[0x842]=1;
    gpu[0xae]=0x8aa8aa82;
    gpu[0x806]=gpu[0x807]=13;gpu[0x808]=1;gpu[0x210]=1;s[0x9058/4]=0x400;
    ((u32 *)(dma+65536))[0]=n==14?0:0x650c0de1;
    if(n==7)gpu[0x806]=12;if(n==8)gpu[0x807]=12;if(n==9)gpu[0x808]=0;
    if(n==10)s[0x9058/4]|=2;if(n==11)gpu[0x821]=1;if(n==12)gpu[0x823]=1;
    if(n==13)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;if(n==15)((u32 *)(dma+65536))[1]=1;
    if(n==16)((u32 *)pool)[18]=1;if(n==26)s[0x48/4]=1;if(n==27)gpu[0x210]=2;
    if(n==29 || n==30)g[BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4]=n==29?0xa4:0xa5;
    if(n==35)gpu[diag_words[10]]=3;
    if(n>=36 && n<=41)gpu[0xae]=0;
    if(n==37)g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=0x10;
    if(n==38)g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=0x80;
    if(n==39)g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=1;
    if(n==40)gpu[0xae]=0x1234;
    if(n==41)g[BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4]=0xa4;
}
int main(int argc,char **argv) {
    (void)argv;
    assert(lmi_gpu_normal_canary(0x1badb002)==0x7eabe044);
    assert(lmi_gpu_normal_diag_canary(0x1badb002)==0x7eabe04a);
    /* Check header parity independently of the production packet constants. */
    u32 op=0x66,count=1;assert((0x70000000u|count|((1^__builtin_parity(count))<<15)|(op<<16)|((1^__builtin_parity(op))<<23))==0x70e60001);
    for(u32 n=0;n<=43;n++) {
        seed(n);verbose=n==(argc>1?36:0);
        int ok=lmi_gpu_unsecure(n==1?0:(u64)pool+(n==2),n==3?81919:81920,n==4?0:g);
        assert(ok==(n==0 || n==29 || n==30 || n==31 || n==33 || n==36));
        if(ok) {
            assert(sent==19 && gpu[0x806]==19 && ((u32 *)(pool+65536))[1]==0x650c0de2);
            assert(clock_writes==(n!=36) && clock_settled==(n!=36));
            assert(g[BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4]==(n==36?0:n==29 || n==30?0xa5:1));
            assert(address_writes==10 && address_settled);
            for(u32 k=1;k<11;k++)assert(gpu[diag_words[k]]==1);
        }
        if(n>=1 && n<=18)assert(!sent);
        if(n==19 || n==20 || n==21)assert(sent==15);
        if(n>=22 && n<=25)assert(sent==19);
        if(n>=26 && n<=28)assert(!sent);
        if(n==32 || n==34 || n==35)assert(!sent && !clock_writes);
        if(n==35)assert(!address_writes);
        if(n>=37)assert(!sent);
        if(n>=37 && n<=41)assert(!clock_writes);
    }
    puts("PASS: parity, exact packets/order, independent DMA cache model, fresh GPU-only fence, prior fence preserved, nonsecure address modes exact/delayed, SP bit0 exact/preserved readback, faults/timeouts and allowlisted writes");
}
