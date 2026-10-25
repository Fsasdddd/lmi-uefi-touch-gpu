/* Production PERF transaction with separately modeled CPU cache and device. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-hfi-perf.c"
static unsigned char pool[196608] __attribute__((aligned(4096))),dma[20480];
static u32 g[0xc000],line_size,stage,ticks,scenario,fail_cache,caches,verbose;
static u64 base;
static u32 *dev(void) {return (u32 *)dma;}
u64 io_map_memory(u64 pa,u64 bytes) {assert(pa==0x80860000 && bytes==0x20000);return 1;}
int lmi_gpu_prepare_perf(const void *db,u32 bytes,struct lmi_gpu_perf_table *t) {
    assert(db==(void *)1 && bytes==0x20000);memset(t,0,sizeof(*t));t->gx_count=8;t->cx_count=2;
    const u32 votes[]={0,0x400202,0x800203,0x900304,0xc00305,0xe00406,0x1000507,0x1400608};
    const u32 freqs[]={0,305000,400000,441600,490000,525000,587000,670000};
    for(u32 n=0;n<8;n++) {t->gx[n][0]=votes[n];t->gx[n][1]=0xffffffff;t->gx[n][2]=freqs[n];}
    t->cx[1][0]=0x400202;t->cx[1][1]=200000;return scenario!=13;
}
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
int cache_sync(u64 address,u32 bytes,int publish) {
    assert(address>=base && address+bytes<=base+20480);
    if(++caches==fail_cache)return 0;
    u32 begin=(u32)(address-base)&~(line_size-1),end=((u32)(address-base)+bytes+line_size-1)&~(line_size-1);
    unsigned char *cpu=(void *)base;
    if(publish) {
        assert(begin>=256 || end<=128);
        if(stage==0) {assert(address==base+272 && bytes==240);dev()[41]=8;stage=1;}
        else if(stage==1) {assert(address==base+64 && bytes==4);stage=2;}
        else {assert(stage==3 && address==base+112 && bytes==4 && dev()[16]==64 && dev()[29]==8);stage=4;}
        for(u32 n=begin/4;n<end/4;n++)if(stage==4 && n!=28)assert(((u32 *)cpu)[n]==dev()[n]);
        memcpy(dma+begin,cpu+begin,end-begin);
    } else memcpy(cpu+begin,dma+begin,end-begin);
    return 1;
}
u32 rsc_read(volatile u32 *word) {assert(word>=g && word<g+0xc000);return *word;}
void rsc_write(volatile u32 *word,u32 value) {
    assert(value==1);
    if(word==g+BOOT_GMU_HOST2GMU_INTR_SET/4) {
        assert(stage==2 && dev()[17]==64 && dev()[16]==4 && dev()[29]==4);
        struct lmi_gpu_perf_table t;assert(lmi_gpu_prepare_perf((void *)1,0x20000,&t));t.hdr=0x203b04;
        assert(!memcmp(dev()+68,&t,sizeof(t)) && dev()[127]==0xfafafafa && dev()[41]==8);stage=3;
    } else {
        assert(word==g+BOOT_GMU_GMU2HOST_INTR_CLR/4 && stage==4 && dev()[28]==8);
        stage=5;if(scenario!=12)g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0;
    }
}
void delay(u32 n,u32 unit) {
    assert(n==100 && unit==1000 && ++ticks<=1000);
    if(scenario==1 || ticks<2)return;
    u32 *d=dev();d[16]=64;d[29]=8;d[1092]=0x10304;d[1093]=0x203b04;d[1094]=0;
    g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=1;d[41]=16;
    switch(scenario) {
    case 2:d[1093]^=0x100000;break;
    case 3:d[1094]=0xffffffff;break;
    case 4:d[1092]^=0x10000;break;
    case 5:d[1092]^=0x100;break;
    case 6:d[29]=1024;break;
    case 7:d[16]=1024;break;
    case 8:g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0x8001;break;
    case 9:g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0;break;
    case 10:d[28]=8;break;
    case 11:d[17]=4;break;
    }
}
static void seed(void) {
    memset(pool,0,sizeof(pool));memset(g,0,sizeof(g));memset(dma,0,sizeof(dma));base=(u64)pool+37*4096;
    dev()[16]=dev()[17]=dev()[28]=dev()[29]=4;memset((void *)base,0xa5,20480);
    stage=ticks=scenario=fail_cache=caches=0;
}
int main(void) {
    for(line_size=64;line_size<=128;line_size*=2) {
        seed();verbose=line_size==64;assert(lmi_gpu_hfi_perf((u64)pool,sizeof(pool),g));verbose=0;
        assert(stage==5 && dev()[28]==8 && dev()[41]==16);
        for(u32 n=1;n<=13;n++) {seed();scenario=n;assert(!lmi_gpu_hfi_perf((u64)pool,sizeof(pool),g));assert(n==12?stage==5:stage<4);}
        for(u32 n=1;n<=8;n++) {seed();fail_cache=n;assert(!lmi_gpu_hfi_perf((u64)pool,sizeof(pool),g));}
        seed();dev()[17]=0;assert(!lmi_gpu_hfi_perf((u64)pool,sizeof(pool),g) && stage==0);
    }
    puts("PASS: PERF payload/publication, independent DMA cache, debug updates, echo/status/type/size/index/IRQ negatives and timeout");
}
