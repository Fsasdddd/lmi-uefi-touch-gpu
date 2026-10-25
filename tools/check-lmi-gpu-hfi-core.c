#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-hfi-perf.c"
#include "lmi-gpu-hfi-core.c"
static unsigned char pool[196608] __attribute__((aligned(4096))),dma[20480];
static u32 g[0xc000],line_size,stage,transaction,ticks,scenario,verbose,bad_db;
static u64 base;
static u32 cmd_start,msg_start,cmd_end,expected_header;
static u32 *dev(void) {return (u32 *)dma;}
u64 io_map_memory(u64 pa,u64 bytes) {assert(pa==0x80860000 && bytes==0x20000);return 1;}
int lmi_gpu_prepare_perf(const void *db,u32 bytes,struct lmi_gpu_perf_table *t) {(void)db;(void)bytes;(void)t;return 0;}
u32 lmi_gpu_bcm_address(const void *db,u32 bytes,const char *id) {
    assert(db==(void *)1 && bytes==0x20000);
    if(bad_db)return 0;
    if(!strcmp(id,"MC0"))return 0x50000;if(!strcmp(id,"SH0"))return 0x50004;
    if(!strcmp(id,"ACV"))return 0x5007c;assert(!strcmp(id,"CN0"));return 0x50074;
}
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
int cache_sync(u64 address,u32 bytes,int publish) {
    assert(address>=base && address+bytes<=base+20480);
    u32 begin=(u32)(address-base)&~(line_size-1),end=((u32)(address-base)+bytes+line_size-1)&~(line_size-1);
    unsigned char *cpu=(void *)base;
    if(publish) {
        assert(begin>=256 || end<=128);
        if(stage==0) {assert(address==base+256+4*cmd_start && bytes==4*(cmd_end-cmd_start));dev()[41]++;stage=1;}
        else if(stage==1) {assert(address==base+64 && bytes==4);stage=2;}
        else {assert(stage==3 && address==base+112 && bytes==4 && dev()[16]==cmd_end && dev()[29]==msg_start+4);stage=4;}
        for(u32 n=begin/4;n<end/4;n++)if(stage==4 && n!=28)assert(((u32 *)cpu)[n]==dev()[n]);
        memcpy(dma+begin,cpu+begin,end-begin);
    } else memcpy(cpu+begin,dma+begin,end-begin);
    return 1;
}
u32 rsc_read(volatile u32 *word) {assert(word>=g && word<g+0xc000);return *word;}
void rsc_write(volatile u32 *word,u32 value) {
    assert(value==1);
    if(word==g+BOOT_GMU_HOST2GMU_INTR_SET/4) {
        assert(stage==2 && dev()[17]==cmd_end && dev()[16]==cmd_start && dev()[29]==msg_start);
        assert(dev()[64+cmd_start]==expected_header);
        if(!transaction) {
            struct lmi_gpu_bw_table t;assert(lmi_gpu_prepare_bw((void *)1,0x20000,&t));t.hdr=expected_header;
            assert(!memcmp(dev()+128,&t,sizeof(t)));
        } else assert(!dev()[64+cmd_start+1] && dev()[64+cmd_start+2]==0xfafafafa);
        stage=3;
    } else {
        assert(word==g+BOOT_GMU_GMU2HOST_INTR_CLR/4 && stage==4 && dev()[28]==msg_start+4);
        g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=0;transaction++;
        cmd_start=224;msg_start=12;cmd_end=228;expected_header=0x40020e;stage=ticks=0;
    }
}
void delay(u32 n,u32 unit) {
    assert(n==100 && unit==1000 && ++ticks<=1000);
    if((scenario==1 && !transaction) || (scenario==2 && transaction) || ticks<2)return;
    u32 *d=dev();d[16]=cmd_end;d[29]=msg_start+4;d[1088+msg_start]=0x10300|(expected_header&255);
    d[1089+msg_start]=expected_header;d[1090+msg_start]=0;g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=1;
    if(scenario==3 && !transaction)d[1090+msg_start]=0xffffffff;
    if(scenario==4 && transaction)d[1089+msg_start]^=0x100000;
    if(scenario==5 && !transaction)g[BOOT_GMU_GMU2HOST_INTR_INFO/4]|=0x8000;
    if(scenario==6 && transaction)d[1088+msg_start]^=0x100;
}
static void seed(void) {
    memset(pool,0,sizeof(pool));memset(dma,0,sizeof(dma));memset(g,0,sizeof(g));base=(u64)pool+37*4096;
    dev()[16]=dev()[17]=64;dev()[28]=dev()[29]=8;memset((void *)base,0xa5,20480);
    cmd_start=64;msg_start=8;cmd_end=224;expected_header=0x30a003;stage=transaction=ticks=scenario=bad_db=0;
}
int main(void) {
    for(line_size=64;line_size<=128;line_size*=2) {
        seed();verbose=line_size==64;assert(lmi_gpu_hfi_core((u64)pool,sizeof(pool),g));verbose=0;
        assert(transaction==2 && dev()[16]==228 && dev()[28]==16);
        for(u32 n=1;n<=6;n++) {seed();scenario=n;assert(!lmi_gpu_hfi_core((u64)pool,sizeof(pool),g));assert(transaction==(n==2 || n==4 || n==6?1:0));}
        seed();bad_db=1;assert(!lmi_gpu_hfi_core((u64)pool,sizeof(pool),g) && !transaction && !stage);
    }
    puts("PASS: exact640B off BW table, CORE only after BW ACK, isolated caches, DMA errors/timeouts and write whitelist");
}
