#include <assert.h>
#include <string.h>
#include <stdio.h>
#define LMI_GPU_CONTEXT_HOST
#include "lmi-gpu-context.c"
static ctx_u32 regs[0x10000/4],saved[0x10000/4];
static int writes,restore_fail,request_fail,transient,fsr_extra,fsr_bad_format;
#ifdef LMI_GPU_STAGE1_INIT
static int tlb_reads,tlb_timeout;
void delay(ctx_u32 n,ctx_u32 scale) {assert(n==1 && scale==1000);}
#endif
void log_line(const char *s) {(void)s;}
void log_hex(ctx_u64 n) {(void)n;}
ctx_u32 ctx_read(volatile ctx_u32 *p) {
#ifdef LMI_GPU_STAGE1_INIT
    if(p==&regs[0x87f4/4])return tlb_timeout || tlb_reads++<2;
#endif
    if(transient && writes==9 && p==&regs[0x8000/4])return *p ^ 2;
    if(p==&regs[0x8058/4] && regs[0x1800/4])
        return *p | (fsr_bad_format?0x200:0x400) | fsr_extra;
    return *p;
}
void ctx_write(volatile ctx_u32 *p,ctx_u32 value) {
    unsigned off=(unsigned)(p-regs)*4;
#ifdef LMI_GPU_STAGE1_INIT
    if(off==0x1000) {
        assert(value==0x1f300 && !(regs[0x8000/4]&1));
        *p=value;writes++;return;
    }
    if(off==0x8610 || off==0x87f0) {
        assert(regs[0x1000/4]==0x1f300 && !(regs[0x8000/4]&1));
        assert(value==(off==0x8610?1:0));
        writes++;return;
    }
#endif
    assert(off==0x1800||off==0x8010||off==0x8030||off==0x8020||
        off==0x8024||off==0x8028||off==0x802c||off==0x8038||off==0x803c);
    writes++;
    if(restore_fail && off==0x8020 && value==0x24680000)return;
    if(request_fail && off==0x8010 && value==0x38071)return;
    *p=value;
}
static void reset(void) {
    memset(regs,0,sizeof(regs));
    regs[0x20/4]=0x4c017e06;regs[0x24/4]=0x20000005;
    regs[0x8010/4]=0x4000c066;regs[0x8020/4]=0x24680000;
    regs[0x8024/4]=0x10001;regs[0x8030/4]=0x12345000;
    memcpy(saved,regs,sizeof(regs));writes=restore_fail=request_fail=transient=fsr_extra=fsr_bad_format=0;
#ifdef LMI_GPU_STAGE1_INIT
    tlb_reads=tlb_timeout=0;
#endif
}
int main(void) {
    reset();assert(lmi_gmu_root_probe(0x19e616000ULL,regs)==1);
    assert(writes==18 && !memcmp(saved,regs,sizeof(regs)));
    reset();request_fail=1;assert(lmi_gmu_root_probe(0x19e616000ULL,regs)==2);
    assert(writes==18 && !memcmp(saved,regs,sizeof(regs)));
    reset();restore_fail=1;assert(lmi_gmu_root_probe(0x19e616000ULL,regs)==0);
    assert(regs[0x8020/4]==0x9e616000);
    reset();transient=1;assert(lmi_gmu_root_probe(0x19e616000ULL,regs)==2);
    assert(writes==18 && !memcmp(saved,regs,sizeof(regs)));
    for(int bit=0;bit<32;bit++) {
        if(bit==10)continue;
        reset();fsr_extra=1u<<bit;
        assert(lmi_gmu_root_probe(0x19e616000ULL,regs)==2);
        assert(writes==18 && !memcmp(saved,regs,sizeof(regs)));
    }
    reset();fsr_bad_format=1;assert(lmi_gmu_root_probe(0x19e616000ULL,regs)==2);
    assert(writes==18 && !memcmp(saved,regs,sizeof(regs)));
    for(int n=0;n<9;n++) {
        reset();
        if(n==0)regs[0x8000/4]=1;
        if(n==1)regs[0x48/4]=1;
        if(n==2)regs[0x8058/4]=1;
        if(n==3)regs[0x800/4]=0x80000000;
        if(n==4)regs[0]=8;
        if(n==5)regs[0x20/4]=0;
        if(n==6)regs[0x24/4]=0;
        if(n==7)regs[0x1800/4]=1;
        ctx_u64 root=n==8?0x1000000000ULL:0x19e616000ULL;
        memcpy(saved,regs,sizeof(regs));
        assert(lmi_gmu_root_probe(root,regs)==2);
        assert(!writes && !memcmp(saved,regs,sizeof(regs)));
    }
    puts("PASS: full wired-root callback, exact readbacks, no CBAR/stream/SCTLR writes, restore failures and refusals");
}
