#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#define LMI_GPU_ZAP_HOST
#define memcpy zap_copy
#define memset zap_zero
#include "lmi-gpu-zap-metadata.c"
#undef memcpy
#undef memset
static unsigned char fw[6860];
static u64 pool,allocated,physical=0x123450000ull;
static u32 scenario,allocs,attrs[2],sets,calls,resumed,protected,verbose;
u64 kernel_map_value=0xf00,g_phys_base=0x100000000ull,g_phys_size=0x180000000ull,xnu_page_size=16384;
u32 xnu_page_shift=14;
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
const unsigned char *image_file(const char *dir,const char *name,u64 *size,int *disk) {
    assert(!strcmp(dir,"fw") && !strcmp(name,"a650_zap.mdt"));*size=scenario==3?6861:6860;*disk=1;return fw;
}
u32 lmi_gpu_firmware_crc(const unsigned char *p,u32 bytes) {
    assert(bytes==6860 && !protected);
    if(p==fw)return scenario==2?0:0x2361d154;
    assert((u64)p==pool);return memcmp(p,fw,6860)?0:0x2361d154;
}
void *zap_copy(void *d,const void *p,u64 n) {assert((u64)d==pool && p==fw && n==6860 && !sets && !calls);return memcpy(d,p,n);}
void *zap_zero(void *d,int c,u64 n) {assert((u64)d==pool && !c && n==allocated && !sets && !calls);return memset(d,c,n);}
struct kmem_result kmem_alloc_tagged(u64 map,u64 bytes,u64 mask,u32 flags,u64 guard,void *callback) {
    assert(map==kernel_map_value && !mask && !flags && guard==3 && !callback && !pool);allocs++;
    if(scenario==5)return (struct kmem_result){3,0};
    allocated=bytes;pool=(u64)aligned_alloc(xnu_page_size,bytes);assert(pool);memset((void *)pool,0xa5,bytes);return (struct kmem_result){0,pool};
}
u64 pa_of(u64 va) {
    assert(pool && va>=pool && va<pool+allocated && !sets && !calls);
    u64 at=va-pool;
    if(scenario==6)return g_phys_base+g_phys_size+at;
    if(scenario==7 && at>=4096)return physical+at+4096;
    if(scenario==8 && at==4095)return physical+at+1;
    return physical+at;
}
u32 pmap_cache_attributes(u32 pn) {
    assert(!calls && pn>=(physical>>xnu_page_shift) && pn<(physical>>xnu_page_shift)+allocated/xnu_page_size);
    return scenario==9?7:attrs[pn-(physical>>xnu_page_shift)];
}
void pmap_set_cache_attributes(u32 pn,u32 attr) {
    assert(!calls && attr==6 && pn==(physical>>xnu_page_shift)+sets);
    assert(!memcmp((void *)pool,fw,6860));
    for(u32 n=6860;n<allocated;n++)assert(!((unsigned char *)pool)[n]);
    sets++;if(scenario!=10 && !(scenario==11 && sets==2))attrs[pn-(physical>>xnu_page_shift)]=attr;
}
void zap_smc_step(u64 fnid,u64 pa,u64 token,u64 *out) {
    assert(pa==physical && sets==allocated/xnu_page_size);
    if(!calls) {
        assert(fnid==0x42000201 && !token && !protected);
        for(u32 n=0;n<sets;n++)assert(attrs[n]==6);
        assert(!memcmp((void *)pool,fw,6860));
        /* Host catches any CPU metadata access after entering PAS. */
        assert(!mprotect((void *)pool,allocated,PROT_NONE));protected=1;
    } else assert(fnid==1 && token==0x60000000ull+resumed);
    calls++;
    if(scenario==14 && resumed<2) {out[0]=1;out[1]=~0ull;out[2]=0x60000000ull+(++resumed);return;}
    if(scenario==15) {out[0]=1;out[1]=~0ull;out[2]=0x60000000ull+(++resumed);return;}
    out[0]=scenario==12?~11ull:0;out[1]=scenario==13?17:0;out[2]=0;
}
int main(int argc,char **argv) {
    assert(argc==2);FILE *file=fopen(argv[1],"rb");assert(file && fread(fw,1,sizeof(fw),file)==sizeof(fw));fclose(file);
    for(scenario=0;scenario<=15;scenario++) {
        pool=allocated=0;allocs=sets=calls=resumed=protected=0;attrs[0]=attrs[1]=2;
        xnu_page_size=(scenario==1 || scenario==11)?4096:16384;xnu_page_shift=xnu_page_size==4096?12:14;
        if(scenario==4)xnu_page_shift=12;
        verbose=scenario==0;
        int result=lmi_gpu_zap_metadata();
        assert(result==(scenario==0 || scenario==1 || scenario==14));
        if(scenario==0 || scenario==1 || scenario>=12)assert(pool && protected && calls && sets==allocated/xnu_page_size);
        else assert(!calls && !protected);
        if(scenario==14)assert(calls==3);
        if(scenario==15)assert(calls==64);
        if(protected)assert(!mprotect((void *)pool,allocated,PROT_READ|PROT_WRITE));
        free((void *)pool); /* Harness cleanup only; production exposes no free. */
    }
    puts("PASS: exact MDT, owned contiguous 4K/16K pages, Normal-NC before PAS, no post-call metadata access, retained errors and bounded A6 resumes");
}
