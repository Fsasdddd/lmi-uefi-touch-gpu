/* Actual route transaction under simulated MMIO with an owned live root. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-route.c"
static u32 smmu[0x4000],gmu[0xc000],before[0x4000];
static u32 writes,fail_write,missing,syncs,sticky,owned,frees,calls,verbose,actor;
static u32 write_offset[64],write_value[64],write_before[64];
static u64 root=0x123450000ull;
u64 io_map(u64 address,u64 bytes) {
    if(address==0x3da0000) {assert(bytes==sizeof(smmu));return missing==1?0:(u64)smmu;}
    assert(address==0x3d6a000 && bytes==sizeof(gmu));return missing==2?0:(u64)gmu;
}
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
void delay(u32 amount,u32 unit) {assert(amount<=100 && unit==1000);}
u32 rsc_read(volatile u32 *word) {
    if(word==smmu+0x8058/4)return smmu[0x1800/4]&1?0x400:0;
    if(word==smmu+0x87f4/4 && sticky!=syncs)*word=0;
    return *word;
}
void rsc_write(volatile u32 *word,u32 value) {
    assert(owned && word>=smmu && word<smmu+0x4000);
    u32 off=(u32)(word-smmu)*4,allowed=off==0x8610 || off==0x87f0;
    for(u32 n=0;n<13;n++)allowed|=off==offsets[n];
    assert(allowed && writes<64);
    if(off==0x1000)assert(value==0x1f300);
    if(off==0x800 && value&0x80000000u) {
        assert(value==0x84000005 && smmu[0x8000/4]==0xc000e7 && syncs==1 && !smmu[0x87f4/4]);
        assert(smmu[0x8020/4]==(u32)root && smmu[0x8024/4]==(0x10000|(u32)(root>>32)));
    }
    /* Once published, tables cannot change until route revocation and sync. */
    if(off>=0x8010 && off<=0x803c && syncs)assert(!smmu[0x800/4]);
    write_offset[writes]=off;write_value[writes]=value;write_before[writes]=*word;
    if(++writes==fail_write)return;
    *word=value;
    if(off==0x8610)assert(value==1);
    if(off==0x87f0) {
        assert(value==0);syncs++;smmu[0x87f4/4]=1;
        if(actor && syncs==1)gmu[0x14000/4]=0;
    }
}
int lmi_gpu_ram_consume(int (*consumer)(u64,void *),void *context) {
    assert(!owned);owned=1;calls++;
#ifdef LMI_GPU_GMU_BOOT
    struct lmi_gpu_live_backing live={context,0xfffffff080000000ull,196608};
    int result=consumer(root,&live);
#else
    int result=consumer(root,context);
#endif
    if(result>0 && result!=3) {
        assert(!(smmu[0x800/4]&0x80000000u) && !(smmu[0x8000/4]&1) && !smmu[0x87f4/4]);
        owned=0;frees++;
    }
    return result;
}
static void seed(void) {
    memset(smmu,0,sizeof(smmu));memset(gmu,0,sizeof(gmu));
    smmu[0x20/4]=0x4c017e06;smmu[0x24/4]=0x20000005;smmu[0]=0x260406;
    for(u32 n=0;n<6;n++)smmu[(0xc00+4*n)/4]=0x27bee3ff;
    for(u32 n=1;n<10;n++)smmu[offsets[n]/4]=0x2000+32*n;
    smmu[0x8000/4]=0x1a69050a;gmu[0x14000/4]=1;
    memcpy(before,smmu,sizeof(smmu));
    writes=fail_write=missing=syncs=sticky=owned=frees=calls=actor=0;root=0x123450000ull;
}
#ifdef LMI_GPU_GMU_BOOT
static int boot_result,boot_calls;
int lmi_gpu_gmu_boot(u64 got_root,u64 pool,u32 bytes) {
    assert(got_root==root && pool==0xfffffff080000000ull && bytes==196608 && owned && !frees);
    assert(syncs==1 && smmu[0x800/4]==0x84000005 && smmu[0x8000/4]==0xc000e7);
    boot_calls++;return boot_result;
}
int main(void) {
    seed();boot_result=3;boot_calls=0;assert(lmi_gpu_gmu_route_probe()==3 && owned && !frees && boot_calls==1 && syncs==1 && smmu[0x800/4]==0x84000005);
    seed();boot_result=0;boot_calls=0;assert(lmi_gpu_gmu_route_probe()==2 && owned && !frees && boot_calls==1 && syncs==1 && smmu[0x800/4]==0x84000005);
    seed();boot_result=2;boot_calls=0;assert(lmi_gpu_gmu_route_probe()==0 && !owned && frees==1 && boot_calls==1 && syncs==2 && smmu[0x800/4]==0);
    puts("PASS: firmware active/uncertain preserves root/backing/context and all parents; prerefusal safely detaches");
}
#else
int main(void) {
    seed();verbose=1;assert(lmi_gpu_gmu_route_probe()==1 && frees==1 && !owned && syncs==2);
    log_line("LMI_GPU_GMU_ROUTE_RESULT\n");log_hex(1);verbose=0;
    for(u32 n=0;n<12;n++)assert(smmu[offsets[n]/4]==before[offsets[n]/4]);
    assert(smmu[0x1000/4]==0x1f300);
    u32 count=writes,at[64],values[64],originals[64];
    memcpy(at,write_offset,sizeof(at));memcpy(values,write_value,sizeof(values));memcpy(originals,write_before,sizeof(originals));
    for(u32 n=0;n<count;n++) {
        if(at[n]==0x8610 || at[n]==0x87f0 || values[n]==originals[n])continue;
        seed();fail_write=n+1;int result=lmi_gpu_gmu_route_probe();
        assert(result!=1);
        if(result==2)assert(owned && !frees);else assert(!owned && frees==1);
    }
    for(u32 n=1;n<=2;n++) {seed();missing=n;assert(!lmi_gpu_gmu_route_probe() && !writes && !calls);}
    for(u32 n=1;n<=2;n++) {seed();sticky=n;assert(lmi_gpu_gmu_route_probe()==2 && owned && !frees);}
    seed();actor=1;assert(lmi_gpu_gmu_route_probe()==2 && owned && !frees);
    seed();root|=1;assert(!lmi_gpu_gmu_route_probe() && !writes && frees==1);
    seed();smmu[0x8000/4]|=1;/* pre-existing active context never ours to free */
    owned=1;struct route_context c={smmu,gmu};assert(route_consumer(root,&c)==2 && !writes);owned=0;
    for(u32 n=0;n<6;n++) {seed();smmu[(0x800+4*n)/4]=0x80000001;owned=1;assert(route_consumer(root,&c)==2 && !writes);owned=0;}
    puts("PASS: real route enable/attach/detach, both sync timeouts, every changing write failure, backing retention, no ATOS/global writes");
}

#endif
