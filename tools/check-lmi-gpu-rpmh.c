#include <assert.h>
#include <stdio.h>
#include <string.h>
#define LMI_GPU_RPMH_HOST
#include "lmi-gpu-rpmh.c"
static arc_u32 regs[0x10000/4],timeout,bad_status,triggered,delays;
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
static arc_u32 gmuregs[0x30000/4];
static arc_u32 interface_write_fault;
vote_u64 io_map(vote_u64 pa,vote_u64 bytes) {assert(pa==0x3d6a000 && bytes==sizeof(gmuregs));return (vote_u64)gmuregs;}
#endif
#define TEST_TCS(off) (((off)+VOTE_SLOT*0x2a0)/4)
static arc_u32 addresses[2],selectors[2],writes;
static char logbuf[4096];
arc_u32 vote_read(volatile arc_u32 *p) {
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
    if((vote_u64)p>=(vote_u64)gmuregs && (vote_u64)p<(vote_u64)(gmuregs+0xc000))return *p;
#endif
    assert(p>=regs && p<regs+0x4000);return *p;
}
void vote_write(volatile arc_u32 *p,arc_u32 v) {
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
    if((vote_u64)p>=(vote_u64)gmuregs && (vote_u64)p<(vote_u64)(gmuregs+0xc000)) {
        assert(p==gmuregs+0x143a0/4 && (v==0 || v==0xf11));writes++;
        if((interface_write_fault==1 && v==0xf11) || (interface_write_fault==2 && !v))return;
        *p=v;return;
    }
#endif
    unsigned absolute=(unsigned)(p-regs)*4;
    unsigned at=absolute;
    if(at>=0xd10+VOTE_SLOT*0x2a0)at-=VOTE_SLOT*0x2a0;
    assert(at==0x10 || (at>=0xd00 && at<=0xd38 && at!=0xd04 && at!=0xd18));
    if(at==0x10)assert(v==0 || v==0x1000000);
    writes++;
    if(at==0xd08) {assert(v==VOTE_IRQ);regs[0xd04/4]&=~VOTE_IRQ;return;}
    *p=v;
    if(at==0xd14 && v==0x1010000) {
        assert(triggered<2);assert(regs[TEST_TCS(0xd30)]==0x10108);
        assert(regs[TEST_TCS(0xd10)]==1 && regs[TEST_TCS(0xd1c)]==1);
        addresses[triggered]=regs[TEST_TCS(0xd34)];selectors[triggered++]=regs[TEST_TCS(0xd38)];
        if(timeout) {regs[TEST_TCS(0xd18)]=0;return;}
        regs[0xd04/4]|=VOTE_IRQ;regs[TEST_TCS(0xd3c)]=bad_status?0x100:0x10100;
    }
}
void log_line(const char *s) {assert(strlen(logbuf)+strlen(s)<sizeof(logbuf));strcat(logbuf,s);}
void log_hex(vote_u64 v) {(void)v;}
void delay(arc_u32 a,arc_u32 b) {assert(a<=100 && b==1000);delays++;}
static void seed(void) {
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
    memset(gmuregs,0,sizeof(gmuregs));gmuregs[0x14000/4]=1;
    interface_write_fault=0;
#endif
    memset(regs,0,sizeof(regs));regs[3]=0x4000000a;regs[0x2c/4]=1;
    regs[0xd18/4]=1;regs[TEST_TCS(0xd18)]=1;regs[0xd00/4]=0x20;
    for(unsigned slot=1;slot<10;slot++)regs[(0xd18+slot*0x2a0)/4]=1;
    regs[TEST_TCS(0xd30)]=0x10203;regs[TEST_TCS(0xd34)]=0x50000;regs[TEST_TCS(0xd38)]=7;
    timeout=bad_status=triggered=delays=writes=0;logbuf[0]=0;
}
int main(void) {
    struct lmi_arc_resource cx={.address=0x30000,.count=9,.min_svs_index=2,.levels={0,16,64,128,192,256,320,384,416}};
    struct lmi_arc_resource mx={.address=0x30010,.count=9,.min_svs_index=2,.levels={0,16,128,192,224,256,320,384,416}};
    seed();assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==1);
    assert(triggered==2 && addresses[0]==mx.address && addresses[1]==cx.address && selectors[0]==2 && selectors[1]==2);
    assert(regs[TEST_TCS(0xd30)]==0x10203 && regs[TEST_TCS(0xd34)]==0x50000 && regs[TEST_TCS(0xd38)]==7 && regs[0xd00/4]==0x20);
    assert(!regs[0x10/4]);
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
    assert(!gmuregs[0x143a0/4] && strstr(logbuf,"INTERFACE_RESTORED"));
#endif
    assert(strstr(logbuf,"VOTES_RETAINED_UNTIL_RESET") && strstr(logbuf,"MIN_VOTES_COMPLETE"));
    unsigned fail_offsets[]={0xc,0x10,0x404,0xd18,0xd14,0xd10,0xd1c,0xd04};
    for(unsigned n=0;n<sizeof(fail_offsets)/sizeof(*fail_offsets);n++) {
        seed();unsigned off=fail_offsets[n];regs[(off>=0xd10?off+VOTE_SLOT*0x2a0:off)/4]=off==0x10?0x10000:off==0xd18?0:off==0xd04?VOTE_IRQ:1;
        assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==0 && !writes && !triggered);
    }
    for(unsigned slot=0;slot<10;slot++) {
        for(unsigned which=0;which<4;which++) {
            seed();unsigned off=0xd00+slot*0x2a0;
            regs[(off+(unsigned[]){0x18,0x14,0x1c,0x10}[which])/4]=which?1:0;
            assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==0 && !writes && !triggered);
        }
    }
    seed();timeout=1;assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==4);
    assert(triggered==1 && addresses[0]==mx.address && !regs[TEST_TCS(0xd18)] && regs[TEST_TCS(0xd14)]==0x1010000 && regs[TEST_TCS(0xd34)]==mx.address);
    assert(delays==2000 && !strstr(logbuf,"STORAGE_RESTORED"));
#ifdef LMI_GPU_RSCC_SDE_PROBE
    assert(regs[0x10/4]==0x1000000);
#endif
#ifdef LMI_GPU_RPMH_INTERFACE_PROBE
    assert(gmuregs[0x143a0/4]==0xf11);
    seed();gmuregs[0x14000/4]=0;assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==0 && !writes);
    seed();gmuregs[0x14070/4]=1;assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==0 && !writes);
    seed();gmuregs[0x143a0/4]=0x80000000;assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==0 && !writes);
    seed();interface_write_fault=1;assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==9 && !triggered && regs[0x10/4]==0x1000000);
    seed();interface_write_fault=2;assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==9 && triggered==2 && gmuregs[0x143a0/4]==0xf11 && regs[0x10/4]==0x1000000);
#endif
    seed();bad_status=1;assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==0 && triggered==1);
    assert(regs[TEST_TCS(0xd30)]==0x10203 && !strstr(logbuf,"MIN_VOTES_COMPLETE"));
    seed();mx.levels[2]=48;assert(lmi_gpu_rscc_min_votes(regs,&cx,&mx)==0 && !writes);
    puts("PASS: GPU DRV0 requests parent MX before CX, refuses busy/unknown layout, retains pending transaction, restores TCS storage only");
}
