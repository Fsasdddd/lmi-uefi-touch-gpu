/* ASan/UBSan exercise the actual source-switch transaction, not real clocks. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-clock.c"
static u32 gcc[0x20000],cc[0x2400],g[0xc000];
static u32 writes,updates,missing,fail_write,sticky,foreign_vote,release_reset;
static u32 verbose;
#ifdef LMI_GPU_GMU_ROUTE
static u32 route_calls,route_result;
int lmi_gpu_gmu_route_probe(void) {
    assert(cc[0x1124/4]==0x100602 && !(cc[0x1120/4]&1) && gcc[0x52000/4]&DIV_GATE && g[0x14000/4]==1);
    route_calls++;return route_result;
}
#endif
u64 io_map(u64 address,u64 bytes) {
    if(address==0x100000) {assert(bytes==sizeof(gcc));return missing==1?0:(u64)gcc;}
    if(address==0x3d90000) {assert(bytes==sizeof(cc));return missing==2?0:(u64)cc;}
    assert(address==0x3d6a000 && bytes==sizeof(g));return missing==3?0:(u64)g;
}
u32 rsc_read(volatile u32 *word) {
    if(word==cc+0x1120/4 && updates && sticky!=updates)*word&=~1u;
    return *word;
}
void rsc_write(volatile u32 *word,u32 value) {
    assert(word==gcc+0x52000/4 || word==cc+0x1124/4 || word==cc+0x1120/4);
    /* Dropping the source gate is allowed only after XO UPDATE completed. */
    if(word==gcc+0x52000/4 && !(value&DIV_GATE))assert(cc[0x1124/4]==1 && !(cc[0x1120/4]&1));
    if(++writes==fail_write)return;
    *word=value;
    if(word==cc+0x1120/4) {
        updates++;
        if(updates==1 && release_reset)g[0x14000/4]=0;
        if(updates==2 && foreign_vote)gcc[0x52000/4]|=0x40;
    }
}
void delay(u32 amount,u32 unit) {assert(amount<=10 && unit==1000);}
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 value) {if(verbose)printf("%016llx\n",value);}
static void seed(void) {
    memset(gcc,0,sizeof(gcc));memset(cc,0,sizeof(cc));memset(g,0,sizeof(g));
    gcc[0]=0x80000001;gcc[1]=31;gcc[0x40/4]=0x4000;gcc[0xc/4]=0x100;gcc[0x38/4]=1;
    gcc[0x52000/4]=0x1a;cc[0x1124/4]=1;cc[0x1098/4]=cc[0x109c/4]=1;g[0x14000/4]=1;
    writes=updates=missing=fail_write=sticky=foreign_vote=release_reset=0;
#ifdef LMI_GPU_GMU_ROUTE
    route_calls=0;route_result=1;
#endif
}
static void restored(void) {
    assert(cc[0x1124/4]==1 && !(cc[0x1120/4]&1) && !(gcc[0x52000/4]&DIV_GATE));
    assert(gcc[0]==0x80000001 && gcc[1]==31 && gcc[0x40/4]==0x4000 && gcc[0xc/4]==0x100 && gcc[0x38/4]==1);
}
int main(void) {
    seed();verbose=1;assert(lmi_gpu_gmu_200mhz_probe()==1 && writes==6 && updates==2);restored();
    log_line("LMI_GPU_GMU_200MHZ_RESULT\n");log_hex(1);verbose=0;
    seed();gcc[0]=0xd810003d;gcc[0x38/4]=0;
    assert(lmi_gpu_gmu_200mhz_probe()==1 && gcc[0]==0xd810003d && !gcc[0x38/4] && cc[0x1124/4]==1);
    seed();gcc[0]=0x80100001;gcc[0x38/4]=0;assert(lmi_gpu_gmu_200mhz_probe()==0 && !writes);
    seed();gcc[0x52000/4]|=DIV_GATE;assert(lmi_gpu_gmu_200mhz_probe()==1 && gcc[0x52000/4]&DIV_GATE);
    seed();foreign_vote=1;assert(lmi_gpu_gmu_200mhz_probe()==1 && gcc[0x52000/4]==0x5a);restored();
    for(u32 n=1;n<=3;n++) {seed();missing=n;assert(lmi_gpu_gmu_200mhz_probe()==0 && !writes);}
    const u32 bad_gcc[]={0,4,0x40,0xc,0x38};
    for(u32 n=0;n<5;n++) {seed();gcc[bad_gcc[n]/4]=0;assert(lmi_gpu_gmu_200mhz_probe()==0 && !writes);}
    seed();cc[0x1124/4]=0x602;assert(lmi_gpu_gmu_200mhz_probe()==0 && !writes);
    seed();cc[0x1120/4]=1;assert(lmi_gpu_gmu_200mhz_probe()==0 && !writes);
    seed();g[0x14000/4]=0;assert(lmi_gpu_gmu_200mhz_probe()==0 && !writes);
    seed();g[0x14070/4]=1;assert(lmi_gpu_gmu_200mhz_probe()==0 && !writes);
    for(u32 n=0;n<2;n++) {seed();cc[(n?0x1098:0x109c)/4]=0x80000000;assert(lmi_gpu_gmu_200mhz_probe()==0 && !writes);}
    seed();fail_write=1;assert(lmi_gpu_gmu_200mhz_probe()==0 && writes==2);restored();
    seed();fail_write=2;assert(lmi_gpu_gmu_200mhz_probe()==0 && writes==6);restored();
    for(u32 n=1;n<=2;n++) {
        seed();sticky=n;assert(lmi_gpu_gmu_200mhz_probe()==2 && gcc[0x52000/4]&DIV_GATE);
        assert(updates==n && cc[0x1120/4]&1);
    }
    seed();fail_write=4;assert(lmi_gpu_gmu_200mhz_probe()==2 && cc[0x1124/4]==0x100602 && gcc[0x52000/4]&DIV_GATE);
    seed();fail_write=6;assert(lmi_gpu_gmu_200mhz_probe()==2 && cc[0x1124/4]==1 && gcc[0x52000/4]&DIV_GATE);
    seed();release_reset=1;assert(lmi_gpu_gmu_200mhz_probe()==2 && writes==3 && gcc[0x52000/4]&DIV_GATE);
#ifdef LMI_GPU_GMU_ROUTE
    assert(!route_calls);
    seed();route_result=0;assert(lmi_gpu_gmu_200mhz_probe()==0 && route_calls==1);restored();
    seed();route_result=2;assert(lmi_gpu_gmu_200mhz_probe()==2 && route_calls==1 && writes==3 && gcc[0x52000/4]&DIV_GATE);
#endif
#ifdef LMI_GPU_GMU_BOOT
    seed();route_result=3;assert(lmi_gpu_gmu_200mhz_probe()==3 && route_calls==1 && writes==3 && gcc[0x52000/4]&DIV_GATE && cc[0x1124/4]==0x100602);
#endif
    puts("PASS: PLL never written, source guards, owned gate only, both UPDATE timeouts and every restoration failure retain parents");
}
