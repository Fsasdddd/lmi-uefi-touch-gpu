/* Production HFI + OOB transaction under separate CPU/device cache models. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-hfi-perf.c"
#include "lmi-gpu-gx-v57.c"
static unsigned char pool[196608] __attribute__((aligned(4096))),dma[20480];
static u32 g[0xc000],line_size,stage,transaction,ticks,scenario,verbose,oob,held;
static u64 base;
static u32 cmd_start,msg_start,cmd_end,expected_header;
static u32 *dev(void) {return (u32 *)dma;}
u64 io_map_memory(u64 pa,u64 bytes) {(void)pa;(void)bytes;assert(0);return 0;}
int lmi_gpu_prepare_perf(const void *db,u32 bytes,struct lmi_gpu_perf_table *t) {(void)db;(void)bytes;(void)t;return 0;}
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
int cache_sync(u64 address,u32 bytes,int publish) {
    assert(address>=base && address+bytes<=base+20480);
    u32 begin=(u32)(address-base)&~(line_size-1),end=((u32)(address-base)+bytes+line_size-1)&~(line_size-1);
    unsigned char *cpu=(void *)base;
    if(publish) {
        assert(begin>=256 || end<=128);
        if(stage==0) {assert(address==base+256+4*cmd_start && bytes==16);dev()[41]++;stage=1;}
        else if(stage==1) {assert(address==base+64 && bytes==4);stage=2;}
        else {assert(stage==3 && address==base+112 && bytes==4 && dev()[16]==cmd_end && dev()[29]==msg_start+4);stage=4;}
        for(u32 n=begin/4;n<end/4;n++)if(stage==4 && n!=28)assert(((u32 *)cpu)[n]==dev()[n]);
        memcpy(dma+begin,cpu+begin,end-begin);
    } else memcpy(cpu+begin,dma+begin,end-begin);
    return 1;
}
u32 rsc_read(volatile u32 *word) {
    assert(word>=g && word<g+0xc000);
    if(word==g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4 && transaction==2 && !oob) {
        if(scenario==7)g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0x80000000;
        if(scenario==8)g[BOOT_GMU_AO_HOST_INTERRUPT_STATUS/4]=0x20;
        if(scenario==9)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
    }
    return *word;
}
void rsc_write(volatile u32 *word,u32 value) {
    if(word==g+BOOT_GMU_HOST2GMU_INTR_SET/4 && value==0x40000000) {
        assert(transaction==2 && !oob && !g[BOOT_GMU_GMU2HOST_INTR_INFO/4]);oob=held=1;ticks=0;return;
    }
    if(word==g+BOOT_GMU_GMU2HOST_INTR_CLR/4 && value==0x80000000) {
        assert(held && oob==1 && g[BOOT_GMU_GMU2HOST_INTR_INFO/4]==value);oob=2;
        if(scenario!=13)g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0;
        if(scenario==14)g[BOOT_GMU_AO_HOST_INTERRUPT_STATUS/4]=0x8;
        if(scenario==15)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
        return;
    }
    assert(value==1 && transaction<2 && !oob);
    if(word==g+BOOT_GMU_HOST2GMU_INTR_SET/4) {
        assert(stage==2 && dev()[17]==cmd_end && dev()[16]==cmd_start && dev()[29]==msg_start);
        assert(dev()[64+cmd_start]==expected_header);
        if(!transaction)for(u32 n=1;n<4;n++)assert(dev()[64+cmd_start+n]==0xfafafafa);
        else {assert(dev()[65+cmd_start]==1 && dev()[66+cmd_start]==7 && dev()[67+cmd_start]==0xff);}
        stage=3;
    } else {
        assert(word==g+BOOT_GMU_GMU2HOST_INTR_CLR/4 && stage==4 && dev()[28]==msg_start+4);
        g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0;transaction++;
        cmd_start=232;msg_start=20;cmd_end=236;expected_header=0x60041e;stage=ticks=0;
    }
}
void delay(u32 n,u32 unit) {
    assert(n==100 && unit==1000 && ++ticks<=1000);
    if(ticks<2)return;
    if(oob) {
        if(scenario==10)return;
        g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=scenario==11?0x80000001:0x80000000;
        g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=scenario==12?0x40:0x28;return;
    }
    if((scenario==1 && !transaction) || (scenario==2 && transaction))return;
    u32 *d=dev();d[16]=cmd_end;d[29]=msg_start+4;d[1088+msg_start]=0x10300|(expected_header&255);
    d[1089+msg_start]=expected_header;d[1090+msg_start]=0;g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=1;
    if(scenario==3 && !transaction)d[1090+msg_start]=0xffffffff;
    if(scenario==4 && transaction)d[1089+msg_start]^=0x100000;
    if(scenario==5 && !transaction)g[BOOT_GMU_GMU2HOST_INTR_INFO/4]|=0x8000;
    if(scenario==6 && transaction)d[1088+msg_start]^=0x100;
}
static void seed(void) {
    memset(pool,0,sizeof(pool));memset(dma,0,sizeof(dma));memset(g,0,sizeof(g));base=(u64)pool+37*4096;
    dev()[16]=dev()[17]=228;dev()[28]=dev()[29]=16;memset((void *)base,0xa5,20480);
    cmd_start=228;msg_start=16;cmd_end=232;expected_header=0x50010a;stage=transaction=ticks=scenario=oob=held=0;
    g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=0xf4;
}
int main(void) {
    for(line_size=64;line_size<=128;line_size*=2) {
        seed();verbose=line_size==64;assert(lmi_gpu_gx((u64)pool,sizeof(pool),g));verbose=0;
        assert(transaction==2 && held && oob==2 && dev()[16]==236 && dev()[28]==24);
        for(u32 n=1;n<=15;n++) {
            seed();scenario=n;assert(!lmi_gpu_gx((u64)pool,sizeof(pool),g));
            assert(held==(n>=10));assert(transaction==(n<=6?(n%2==0?1:0):2));
        }
        seed();g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0x80000000;assert(!lmi_gpu_gx((u64)pool,sizeof(pool),g) && !transaction && !held);
    }
    puts("PASS: START/DCVS DMA, fresh bounded OOB, GX status and AO/fence guards, retained keepalive, strict MMIO whitelist, 64/128B cache isolation");
}
