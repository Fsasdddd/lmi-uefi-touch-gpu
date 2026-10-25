#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-core-access.c"
static u32 cc[0x9000/4],gpu[0x40000/4],g[0x30000/4],reads,logs,missing,inject,verbose=1;
u64 io_map(u64 a,u64 b) {
    if(missing)return 0;
    if(a==0x3d90000) {assert(b==sizeof(cc));return (u64)cc;}
    assert(a==0x3d00000 && b==sizeof(gpu));return (u64)gpu;
}
u32 rsc_read(volatile u32 *p) {
    reads++;
    if(p>=cc && p<cc+sizeof(cc)/4)return *p;
    if(p>=gpu && p<gpu+sizeof(gpu)/4)return *p;
    assert(p>=g && p<g+sizeof(g)/4);
    if(inject && logs==47)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
    return *p;
}
void log_line(const char *p) {if(verbose)fputs(p,stdout);}
void log_hex(u64 v) {logs++;if(verbose)printf("%016llx\n",v);}
int main(void) {
    assert(lmi_gpu_core_access(g) && reads==55 && logs==47);
    verbose=0;logs=reads=0;inject=1;assert(!lmi_gpu_core_access(g) && logs==47);inject=0;memset(g,0,sizeof(g));
    reads=logs=0;missing=1;assert(!lmi_gpu_core_access(g) && !logs);missing=0;
    const u32 offsets[]={BOOT_GMU_SPTPRAC_PWR_CLK_STATUS,BOOT_GMU_GMU2HOST_INTR_INFO,
        BOOT_GMU_AHB_FENCE_STATUS,BOOT_GMU_AO_HOST_INTERRUPT_STATUS};
    const u32 masks[]={0xc0,1,1,0x29};
    for(u32 n=0;n<4;n++) {memset(g,0,sizeof(g));g[offsets[n]/4]=masks[n];assert(!lmi_gpu_core_access(g));}
    assert(!lmi_gpu_core_access(0));
    puts("PASS: read-only mapped census, GX/GMU fault guards and missing mappings; no write symbols linked");
}
