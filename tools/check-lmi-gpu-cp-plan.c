#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-cp-plan.c"
static u32 g[0xc000],s[0x4000],gpu[0x10000],reads,verbose,missing;
u64 io_map(u64 a,u64 b) {if(a==0x3da0000) {assert(b==sizeof(s));return missing?0:(u64)s;}assert(a==0x3d00000 && b==sizeof(gpu));return (u64)gpu;}
u32 rsc_read(volatile u32 *p) {
    if(p>=gpu && p<gpu+0x10000) {assert(!(g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]&0xc0));reads++;return *p;}
    if(p>=g && p<g+0xc000)return *p;
    assert(p>=s && p<s+0x4000);return *p;
}
void log_line(const char *p) {if(verbose)fputs(p,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
static void seed(void) {memset(g,0,sizeof(g));memset(s,0,sizeof(s));memset(gpu,0,sizeof(gpu));s[0x20/4]=0x4c017e06;s[0x24/4]=0x20000005;s[0x800/4]=0x84000005;reads=missing=0;}
int main(void) {
    seed();verbose=1;assert(lmi_gpu_cp_plan(g) && reads==17);verbose=0;
    for(u32 n=0;n<7;n++) {seed();if(n==0)missing=1;if(n==1)g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=0xc0;if(n==2)g[BOOT_GMU_GMU2HOST_INTR_INFO/4]=1;if(n==3)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;if(n==4)s[0x20/4]=0;if(n==5)s[0x24/4]=0;if(n==6)s[0x800/4]=0;assert(!lmi_gpu_cp_plan(g) && !reads);}
    for(u32 n=1;n<6;n++) {seed();s[0x800/4+n]=0x80000000;assert(!lmi_gpu_cp_plan(g));}
    seed();s[0x9000/4]=1;assert(!lmi_gpu_cp_plan(g));seed();s[0x9058/4]=2;assert(!lmi_gpu_cp_plan(g));seed();s[0x48/4]=1;assert(!lmi_gpu_cp_plan(g));
    puts("PASS: read-only CP census gated by GX, valid GMU mapping and clean idle CB1; no write imports");
}
