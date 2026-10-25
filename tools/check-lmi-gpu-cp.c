#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-cp.c"
static unsigned char pool[81920] __attribute__((aligned(4096))),dma[81920];
static u32 g[0xc000],s[0x4000],gpu[0x10000],scenario,writes,configs,started,sent,ticks,verbose,line_size,settled,pending_roq;
void log_line(const char *p) {if(verbose)fputs(p,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
u64 io_map(u64 a,u64 b) {if(a==0x3da0000) {assert(b==sizeof(s));return (u64)s;}assert(a==0x3d00000 && b==sizeof(gpu));return (u64)gpu;}
u32 rsc_read(volatile u32 *p) {if(p>=g && p<g+0xc000)return *p;if(p>=s && p<s+0x4000)return *p;assert(p>=gpu && p<gpu+0x10000);return *p;}
int cache_sync(u64 address,u32 bytes,int publish) {
    u32 off=(u32)(address-(u64)pool);assert((off==0 && publish) || (off==65536 && !publish));assert(bytes==128);
    if(publish) {assert(!started || sent==9);memcpy(dma+off,pool+off,bytes);}
    else memcpy(pool+off,dma+off,bytes);
    return 1;
}
void rsc_write(volatile u32 *p,u32 value) {
#ifdef LMI_GPU_CP_SP_CLOCK
    if(p==g+BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4) {assert(!writes && !configs && !started && value==(*p|1));if(scenario!=10)*p=value;return;}
#endif
#ifdef LMI_GPU_CP_FENCE
    if(p==g+BOOT_GMU_AO_AHB_FENCE_CTRL/4) {assert(!writes && !configs && !started && !value);if(scenario!=9)*p=0;return;}
#endif
    assert(p>=gpu && p<gpu+0x10000);writes++;
    if(configs<11) {
        assert(!started && p==gpu+settings[configs].word && value==settings[configs].value);
        configs++;if(scenario==configs+19)return;
#ifdef LMI_GPU_CP_CONFIG_READY
        if(p==gpu+0x8c2 && (scenario==40 || scenario==41)) {pending_roq=value;return;}
        if(p==gpu+0x8c2 && scenario==42) {*p=value^1;return;}
#endif
    } else if(p==gpu+0x808) {
        assert(configs==11 && !started && value==1);
#ifdef LMI_GPU_CP_CONFIG_READY
        assert(settled==1 && !gpu[0x806] && !gpu[0x807] && !gpu[0x808]);
        for(u32 n=0;n<11;n++)assert(gpu[settings[n].word]==settings[n].value);
#endif
        started=1;
    }
    else {
        assert(p==gpu+0x807 && started && (value==9 || value==13));ticks=0;
        const u32 *d=(void *)dma;
        if(value==9) {const u32 expected[]={0x70c80008,0x2f,3,0x20000000,0,0,0,0,0};assert(!sent && !memcmp(d,expected,sizeof(expected)));}
        else {assert(sent==9 && d[9]==0x703d8003 && d[10]==0x1010000 && !d[11] && d[12]==0x650c0de1);}
        sent=value;
    }
    *p=value;
}
void delay(u32 amount,u32 unit) {
#ifdef LMI_GPU_CP_CONFIG_READY
    if(!started) {
        assert(amount==100 && unit==1000 && configs==11 && !sent && !settled);
        settled=1;
        if(scenario==40) {assert(!gpu[0x8c2] && pending_roq==0x02000140);gpu[0x8c2]=pending_roq;}
        if(scenario==43)s[0x9058/4]|=2;
        if(scenario==44)s[0x48/4]=1;
        if(scenario==45)gpu[0x821]=1;
        if(scenario==46)gpu[0x823]=1;
        if(scenario==47)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
        if(scenario==48)gpu[0x808]=1;
        if(scenario==49)gpu[0x807]=1;
        if(scenario==50)gpu[0x806]=1;
        return;
    }
#endif
#ifdef LMI_GPU_CP_CONFIG_PLAN
    assert(amount==100 && unit==1000 && !started && !sent && configs==11);
    if(scenario==3)s[0x9058/4]|=2;
    if(scenario==4)gpu[0x821]=1;
    if(scenario==5)gpu[0x823]=1;
    if(scenario==6)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
    return;
#endif
    assert(amount==100 && unit==1000 && ++ticks<=1000 && started && sent);
    if(ticks<2 || scenario==1 || (scenario==2 && sent==13))return;
    if(scenario==3) {s[0x9058/4]|=2;return;}
    if(scenario==4) {gpu[0x821]=1;return;}
    if(scenario==5) {gpu[0x823]=1;return;}
    if(scenario==6) {g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;return;}
    gpu[0x806]=sent;
    if(sent==13)((u32 *)(dma+65536))[0]=scenario==7?0:0x650c0de1;
}
static void seed(void) {memset(g,0,sizeof(g));memset(s,0,sizeof(s));memset(gpu,0,sizeof(gpu));memset(pool,0,sizeof(pool));memset(dma,0xa5,sizeof(dma));memset(dma+65536,0,128);s[0x804/4]=0x84010000;s[0x9000/4]=0xc000e7;s[0x9058/4]=0x400;gpu[0x210]=1;scenario=writes=configs=started=sent=ticks=settled=pending_roq=0;}
int main(void) {
#ifdef LMI_GPU_CP_CONFIG_PLAN
    line_size=64;seed();verbose=1;assert(lmi_gpu_cp((u64)pool,sizeof(pool),g) && !started && !sent && configs==11);verbose=0;
    for(u32 n=20;n<=30;n++) {seed();scenario=n;assert(lmi_gpu_cp((u64)pool,sizeof(pool),g) && !started && !sent && configs==11);}
    for(u32 n=3;n<=6;n++) {seed();scenario=n;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !started && !sent);}
    seed();gpu[0x808]=1;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !writes);
    seed();gpu[0x807]=1;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !writes);
    puts("PASS: inert CP configuration census, delayed readback, every config mismatch accepted as observation only, no SQE/WPTR start, fault stops");return 0;
#endif
    for(line_size=64;line_size<=128;line_size*=2) {
#ifdef LMI_GPU_CP_CONFIG_READY
        seed();scenario=40;verbose=line_size==64;
        assert(lmi_gpu_cp((u64)pool,sizeof(pool),g) && settled==1 && pending_roq==0x02000140 && started && sent==13);
        assert(((u32 *)(pool+65536))[0]==0x650c0de1);verbose=0;
        for(u32 n=41;n<=50;n++) {
            seed();scenario=n;
            assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !started && !sent && writes==11 && settled==1);
        }
#endif
        seed();verbose=line_size==64;assert(lmi_gpu_cp((u64)pool,sizeof(pool),g));verbose=0;assert(started && sent==13 && gpu[0x806]==13 && ((u32 *)(pool+65536))[0]==0x650c0de1);
        for(u32 n=1;n<=7;n++) {seed();scenario=n;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && started);}
        for(u32 n=20;n<=30;n++) {seed();scenario=n;int ok=lmi_gpu_cp((u64)pool,sizeof(pool),g);if(ok)assert(n==27 || n==29);else assert(!started);}
        seed();g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=0xc0;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !writes);
        seed();gpu[0x808]=1;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !writes);
        seed();s[0x804/4]=0;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !writes);
        seed();((u32 *)pool)[0]=1;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !writes);
#ifdef LMI_GPU_CP_FENCE
        seed();scenario=9;g[BOOT_GMU_AO_AHB_FENCE_CTRL/4]=1;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !writes);
#endif
#ifdef LMI_GPU_CP_SP_CLOCK
        seed();scenario=10;assert(!lmi_gpu_cp((u64)pool,sizeof(pool),g) && !writes);
        seed();g[BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4]=0xa4;assert(lmi_gpu_cp((u64)pool,sizeof(pool),g) && g[BOOT_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL/4]==0xa5);
#endif
    }
    puts("PASS: source CP packets, cache publication before WPTR, GPU-only fence writeback, config guards, bounded faults/timeouts, preserved SP control bits, no secure/SMMU writes");
}
