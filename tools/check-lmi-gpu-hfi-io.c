/* Execute production C with distinct CPU-cache and DMA backing. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define LMI_GPU_HFI_IO_HOST
#include "lmi-gpu-hfi-io.c"
#include "lmi-gpu-hfi.c"
static unsigned char pool[196608] __attribute__((aligned(4096))),dma[20480];
static u32 g[0xc000],line_size,doorbell,cleared,stage,ticks,scenario,verbose,fail_cache,caches;
static u64 base;
static u32 *device(void) {return (u32 *)dma;}
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
int cache_sync(u64 address,u32 bytes,int publish) {
    assert(address>=base && address+bytes<=base+20480);
    if(++caches==fail_cache)return 0;
    u32 begin=(u32)(address-base)&~(line_size-1),end=((u32)(address-base)+bytes+line_size-1)&~(line_size-1);
    unsigned char *cpu=(unsigned char *)base;
    if(publish) {
        /* DBG can write its header even while CMD is idle. A CMD clean must
         * never write back that line: exercise this at payload publication. */
        if(!doorbell && stage==0)device()[41]=8;
        assert(begin>=256 || end<=128);
        if(!doorbell) {
            assert((address==base+256 && bytes==16 && stage==0) ||
                   (address==base+64 && bytes==4 && stage==1));
            stage++;
        } else {
            assert(stage==3 && address==base+112 && bytes==4 && device()[16]==4 && device()[29]==4);
            /* Reject cache-line writeback that destroys a firmware word. */
            for(u32 n=begin/4;n<end/4;n++)if(n!=28)assert(((u32 *)cpu)[n]==device()[n]);
            stage=4;
        }
        memcpy(dma+begin,cpu+begin,end-begin);
    } else memcpy(cpu+begin,dma+begin,end-begin);
    return 1;
}
u32 rsc_read(volatile u32 *word) {assert(word>=g && word<g+0xc000);return *word;}
void rsc_write(volatile u32 *word,u32 value) {
    assert(value==1);
    if(word==g+BOOT_GMU_HOST2GMU_INTR_SET/4) {
        assert(stage==2 && !doorbell && device()[17]==4 && !device()[16] && !device()[29]);
        const u32 request[]={0x00100201,0x20000000,0xfafafafa,0xfafafafa};
        assert(!memcmp(device()+64,request,sizeof(request)));doorbell=1;stage=3;
    } else {
        assert(word==g+BOOT_GMU_GMU2HOST_INTR_CLR/4 && stage==4 && !cleared && device()[28]==4);
        cleared=1;if(scenario!=12)g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0;
    }
}
void delay(u32 n,u32 unit) {
    assert(n==100 && unit==1000 && ++ticks<=1000);
    if(scenario==1 || ticks<2)return;
    u32 *d=device();d[16]=4;d[29]=4;
    d[1088]=0x10400;d[1089]=0x00100201;d[1090]=0;d[1091]=0x20010008;
    g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=1;
    /* A firmware debug index may advance independently; CPU never cleans it. */
    d[41]=16;
    switch(scenario) {
    case 2:d[1089]^=0x100000;break;
    case 3:d[1090]=0xffffffff;break;
    case 4:d[1091]^=1;break;
    case 5:d[1088]^=0x10000;break;
    case 6:d[1088]^=0x100;break;
    case 7:d[29]=1024;break;
    case 8:d[16]=1025;break;
    case 9:g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0x8001;break;
    case 10:g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0;break;
    case 11:d[28]=4;break;
    }
}
static void seed(void) {
    memset(pool,0,sizeof(pool));memset(g,0,sizeof(g));base=(u64)pool+37*4096;
    assert(lmi_hfi_prepare((void *)base,20480,0x60001000));memcpy(dma,(void *)base,sizeof(dma));
    /* Deliberately stale CPU view: production must invalidate before reading. */
    memset((void *)base,0xa5,20480);
    g[0x14070/4]=0x100;g[0x14600/4]=1;g[0x14604/4]=0x20000001;
    g[0xafe0/4]=0x20010008;g[0xaff0/4]=0x20000001;
    doorbell=cleared=stage=ticks=scenario=fail_cache=caches=0;
}
int main(void) {
    for(line_size=64;line_size<=128;line_size*=2) {
        seed();verbose=line_size==64;assert(lmi_gpu_hfi_version((u64)pool,sizeof(pool),g)==1);
        verbose=0;assert(doorbell && cleared && device()[28]==4 && device()[41]==16);
        for(u32 n=1;n<=12;n++) {
            seed();scenario=n;assert(!lmi_gpu_hfi_version((u64)pool,sizeof(pool),g));
            assert(doorbell && (n==12?cleared:!cleared));
        }
        for(u32 n=1;n<=4;n++) {
            seed();device()[n==1?16:n==2?17:n==3?28:29]=4;
            assert(!lmi_gpu_hfi_version((u64)pool,sizeof(pool),g) && !doorbell);
        }
        seed();g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=1;
        assert(!lmi_gpu_hfi_version((u64)pool,sizeof(pool),g) && !doorbell);
        for(u32 n=1;n<=8;n++) {
            seed();fail_cache=n;assert(!lmi_gpu_hfi_version((u64)pool,sizeof(pool),g));
        }
        seed();assert(!lmi_gpu_hfi_version((u64)pool+4,sizeof(pool),g) && !caches);
        seed();assert(!lmi_gpu_hfi_version((u64)pool,47*4096-1,g) && !caches);
    }
    puts("PASS: 64/128B noncoherent DMA, publication order, stale cache/ACK/indices/IRQ, faults, timeout and cache failures");
}
