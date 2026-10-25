/* ASan/UBSan tests actual transaction, including every failed write/restore. */
#define LMI_GPU_RSC_INIT_HOST
#include "lmi-gpu-rsc-init.c"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static u32 r[0x10000/4],g[0x30000/4],p[0x10000/4],r_before[0x10000/4],p_before[0x10000/4];
static u32 writes,fail_write,fail_map,post_busy,verbose;
#ifdef LMI_GPU_RSC_PDC_VOTE
static u32 votes,vote_result;
#ifdef LMI_GPU_GMU_200MHZ
static u32 clock_calls,clock_result;
int lmi_gpu_gmu_200mhz_probe(void) {
    assert(votes==1 && vote_result==1 && writes==PROGRAM_COUNT && p[0x4500/4]==0x80000001);
    clock_calls++;return clock_result;
}
#endif
int lmi_gpu_arc_min_votes(volatile u32 *rscc) {
    assert(rscc==r && writes==PROGRAM_COUNT && (!fail_write || fail_write>PROGRAM_COUNT));
    for(u32 i=0;i<19;i++)assert((i<17?r:p)[offsets[i]/4]==((i==0 || i>=12)?requested[i]:expected[i]));
    votes++;
    if(verbose)log_line("LMI_GPU_RPMH_REQUEST_ADDRESS\n");
    return vote_result;
}
#endif
#ifdef LMI_GPU_PDC_ENABLE
static const u32 test_indices[]={0,12,13,14,15,16,17,18};
#elif defined(LMI_GPU_RSC_SEQUENCE)
static const u32 test_indices[]={0,12,13,14,15,16};
#else
static const u32 test_indices[]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18};
#endif
u64 io_map(u64 address,u64 bytes) {
    if(address==0x3de0000) {assert(bytes==sizeof(r));return fail_map==1?0:(u64)r;}
    if(address==0x3d6a000) {assert(bytes==sizeof(g));return fail_map==2?0:(u64)g;}
    assert(address==0xb290000 && bytes==sizeof(p));return fail_map==3?0:(u64)p;
}
u32 rsc_read(volatile u32 *word) {
    if(post_busy && writes && word==r+0x404/4)return 1;
    return *word;
}
void rsc_write(volatile u32 *word,u32 value) {
    u32 ordinal=writes<PROGRAM_COUNT?writes:2*PROGRAM_COUNT-1-writes;
    /* On an early failed programming write, reverse restore starts there. */
    if(fail_write && fail_write<=PROGRAM_COUNT && writes>=fail_write)ordinal=2*fail_write-1-writes;
    assert(ordinal<sizeof(test_indices)/sizeof(test_indices[0]));
    u32 index=test_indices[ordinal];
    assert(word==(index<17?r:p)+offsets[index]/4);
    writes++;
    if(writes!=fail_write)*word=value;
}
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
static void seed(void) {
    memset(r,0,sizeof(r));memset(g,0,sizeof(g));memset(p,0,sizeof(p));
    g[0x14000/4]=1;r[3]=0x4000000a;
    for(u32 i=0;i<10;i++)r[(0xd18+i*0x2a0)/4]=1;
    for(u32 i=0;i<19;i++)(i<17?r:p)[offsets[i]/4]=expected[i];
    memcpy(r_before,r,sizeof(r));memcpy(p_before,p,sizeof(p));
    writes=fail_write=fail_map=post_busy=0;
#ifdef LMI_GPU_RSC_PDC_VOTE
    votes=0;vote_result=1;
#ifdef LMI_GPU_GMU_200MHZ
    clock_calls=0;clock_result=1;
#endif
#endif
}
static void unchanged(void) {assert(!memcmp(r,r_before,sizeof(r)) && !memcmp(p,p_before,sizeof(p)));}
int main(void) {
    seed();verbose=1;assert(lmi_gpu_rsc_init()==1 && writes==2*PROGRAM_COUNT);
    log_line("LMI_GPU_RSC_INIT_RESULT\n");log_hex(1);verbose=0;unchanged();
    for(u32 i=1;i<=3;i++) {seed();fail_map=i;assert(!lmi_gpu_rsc_init() && !writes);unchanged();}
    for(u32 i=0;i<19;i++) {
        seed();(i<17?r:p)[offsets[i]/4]^=1;
        assert(!lmi_gpu_rsc_init() && !writes);
    }
    for(u32 slot=0;slot<10;slot++)for(u32 field=0;field<4;field++) {
        const u32 off[]={0x18,0x14,0x10,0x1c};
        seed();r[(0xd00+slot*0x2a0+off[field])/4]^=1;
        assert(!lmi_gpu_rsc_init() && !writes);
    }
    const u32 guards[]={0x14000,0x14070,0x143a0,0x24c1c,0x24c20};
    for(u32 i=0;i<5;i++) {seed();g[guards[i]/4]^=1;assert(!lmi_gpu_rsc_init() && !writes);}
    const u32 rguards[]={0xc,0x404,0xd04};
    for(u32 i=0;i<3;i++) {seed();r[rguards[i]/4]^=1;assert(!lmi_gpu_rsc_init() && !writes);}
    /* Failed programming writes that actually change the original value. */
    for(u32 i=0;i<PROGRAM_COUNT;i++)if(requested[test_indices[i]]!=expected[test_indices[i]]) {
        seed();fail_write=i+1;assert(lmi_gpu_rsc_init()==0 && writes==2*(i+1));unchanged();
    }
    for(u32 i=0;i<PROGRAM_COUNT;i++)if(requested[test_indices[i]]!=expected[test_indices[i]]) {
        seed();fail_write=2*PROGRAM_COUNT-i;assert(lmi_gpu_rsc_init()==2 && writes==2*PROGRAM_COUNT);
    }
    seed();post_busy=1;assert(lmi_gpu_rsc_init()==2 && writes==PROGRAM_COUNT);
    assert(r[0x600/4]==0xeaaae5a0);
#ifdef LMI_GPU_PDC_ENABLE
    assert(p[0x4500/4]==0x80000001 && r[0x34/4]==0x82204514 && r[0x48/4]==0);
#elif defined(LMI_GPU_RSC_SEQUENCE)
    assert(p[0x4500/4]==0x100 && r[0x34/4]==0x82204514 && r[0x48/4]==0);
#else
    assert(p[0x4500/4]==0x80000001);
#endif
    fputs("PASS: exact vendor writes/reverse restore, refusal for every slot/guard, injected failures retain dependencies\n",stderr);
#ifdef LMI_GPU_RSC_PDC_VOTE
    seed();vote_result=0;assert(lmi_gpu_rsc_init()==0 && votes==1);unchanged();
    const u32 pending[]={2,3,4,5,6,7,8,9};
    for(u32 i=0;i<8;i++) {
        seed();vote_result=pending[i];assert(lmi_gpu_rsc_init()==2 && votes==1 && writes==PROGRAM_COUNT);
        assert(p[0x4500/4]==0x80000001 && r[0x600/4]==0xeaaae5a0 && r[0x10/4]==0x1000000);
    }
    fputs("PASS: held RSC/PDC precedes requests; every uncertain RPMh result retains complete initialization\n",stderr);
#ifdef LMI_GPU_GMU_200MHZ
#ifdef LMI_GPU_GMU_BOOT
    seed();clock_result=3;assert(lmi_gpu_rsc_init()==3 && clock_calls==1 && writes==PROGRAM_COUNT && p[0x4500/4]==0x80000001 && r[0x600/4]==requested[12]);
#endif
    seed();clock_result=0;assert(lmi_gpu_rsc_init()==0 && clock_calls==1);unchanged();
    seed();clock_result=2;assert(lmi_gpu_rsc_init()==2 && clock_calls==1 && writes==PROGRAM_COUNT && p[0x4500/4]==0x80000001);
    seed();vote_result=0;assert(lmi_gpu_rsc_init()==0 && !clock_calls);unchanged();
    seed();vote_result=4;assert(lmi_gpu_rsc_init()==2 && !clock_calls);
    fputs("PASS: 200MHz callback only after both votes; uncertain clock restoration retains RSC/PDC\n",stderr);
#endif
#endif
}
