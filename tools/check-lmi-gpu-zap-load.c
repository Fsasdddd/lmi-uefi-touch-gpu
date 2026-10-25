#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#define LMI_GPU_ZAP_LOAD_HOST
#define memcpy payload_copy
#define memset payload_zero
#include "lmi-gpu-zap-load.c"
#undef memcpy
#undef memset
static unsigned char fw[1676];
static u64 pool,raw_pool,physical=0x124000000ull;
static u32 scenario,allocs,sets,attrs[256],calls,mem_ready,auth_calls,protected,resumed,verbose;
u64 g_phys_base=0x100000000ull,g_phys_size=0x180000000ull,xnu_page_size;
u32 xnu_page_shift;
void log_line(const char *p) {if(verbose)fputs(p,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
const unsigned char *image_file(const char *dir,const char *name,u64 *size,int *disk) {
    assert(!strcmp(dir,"fw") && !strcmp(name,"a650_zap.b02"));*size=scenario==2?1677:1676;*disk=1;return fw;
}
u32 lmi_gpu_firmware_crc(const unsigned char *p,u32 n) {
    assert(n==1676 && !protected);
    if(p==fw)return scenario==1?0:0x5384b346;
    assert((u64)p==pool && mem_ready && !auth_calls);
    return scenario==11 || memcmp(p,fw,n)?0:0x5384b346;
}
void *alloc_contiguous(u64 bytes,u64 alignment,u64 *pa) {
    assert(bytes==0x100000 && alignment==bytes && !pa && !pool);allocs++;
    if(scenario==4)return 0;
    raw_pool=(u64)aligned_alloc(bytes,2*bytes);assert(raw_pool);
    pool=raw_pool+(scenario==17?16384:scenario==18?1:scenario==19?4096:0);
    memset((void *)pool,0xa5,bytes);return (void *)pool;
}
u64 pa_of(u64 va) {
    assert(pool && va>=pool && va<pool+0x100000 && !sets && !calls);u64 at=va-pool;
    if(scenario==5)return physical+4096+at;
    if(scenario==6 && at>=4096)return physical+at+4096;
    if(scenario==7 && at==4095)return physical+at+1;
    return physical+at;
}
u32 pmap_cache_attributes(u32 pn) {
    assert(!calls && pn>=(physical>>xnu_page_shift) && pn<(physical>>xnu_page_shift)+0x100000/xnu_page_size);
    return scenario==8?7:attrs[pn-(physical>>xnu_page_shift)];
}
void pmap_set_cache_attributes(u32 pn,u32 attr) {
    assert(!calls && attr==6 && pn==(physical>>xnu_page_shift)+sets);
    sets++;if(scenario!=9)attrs[pn-(physical>>xnu_page_shift)]=attr;
}
void *payload_zero(void *p,int c,u64 n) {assert((u64)p==pool && !c && n==0x100000 && mem_ready && !protected && !auth_calls);return memset(p,c,n);}
void *payload_copy(void *d,const void *p,u64 n) {
    assert((u64)d==pool && p==fw && n==1676 && mem_ready && !protected && !auth_calls);
    memcpy(d,p,n);if(scenario==12)((unsigned char *)d)[1676]=1;return d;
}
void zap_load_step(u64 function,u64 info,u64 pa,u64 span,u64 token,u64 *out) {
    u32 command=mem_ready?5:2;calls++;
    assert(sets==0x100000/xnu_page_size && info==(command==2?3:1));
    for(u32 n=0;n<sets;n++)assert(attrs[n]==6);
    assert(pa==(command==2?physical:0) && span==(command==2?0x1000:0));
    assert(function==(resumed?1:0x42000200u|command));
    assert(token==(resumed?0x60000000ull+resumed:0));
    if(command==5 && !auth_calls) {
        assert(!protected && !memcmp((void *)pool,fw,1676));
        for(u32 n=1676;n<0x100000;n++)assert(!((unsigned char *)pool)[n]);
    }
    if(command==5)auth_calls++;
    if(!protected) {assert(!mprotect((void *)pool,0x100000,PROT_NONE));protected=1;}
    if(scenario==15 || (scenario==14 && resumed<2)) {out[0]=1;out[1]=~0ull;out[2]=0x60000000ull+(++resumed);return;}
    out[0]=scenario==16?~11ull:0;
    out[1]=(scenario==10 && command==2) || (scenario==13 && command==5)?17:0;out[2]=0;
    if(!out[0] && !out[1] && command==2) {assert(!mprotect((void *)pool,0x100000,PROT_READ|PROT_WRITE));protected=0;mem_ready=1;}
    resumed=0;
}
int main(int argc,char **argv) {
    assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f && fread(fw,1,sizeof(fw),f)==sizeof(fw));fclose(f);
    assert(lmi_gpu_zap_code_canary(0x1badb002)==0x7eabe047);
    for(scenario=0;scenario<=19;scenario++) {
        pool=raw_pool=0;allocs=sets=calls=mem_ready=auth_calls=protected=resumed=0;
        xnu_page_size=scenario==3 || scenario==19?4096:16384;xnu_page_shift=xnu_page_size==4096?12:14;
        for(u32 n=0;n<256;n++)attrs[n]=2;
        verbose=scenario==0;
        int ok=lmi_gpu_zap_load();assert(ok==(scenario==0 || scenario==3 || scenario==14 || scenario==17 || scenario==19));
        if(ok)assert(mem_ready && auth_calls && protected);
        if(scenario==1 || scenario==2 || scenario==4 || (scenario>=5 && scenario<=9))assert(!calls);
        if(scenario==10)assert(!mem_ready && !auth_calls && protected);
        if(scenario==11 || scenario==12)assert(mem_ready && !auth_calls && !protected);
        if(scenario==13)assert(mem_ready && auth_calls==1 && protected);
        if(scenario==14)assert(calls==6 && auth_calls==3);
        if(scenario==15)assert(calls==64 && !mem_ready && !auth_calls && protected);
        if(scenario==18)assert(!sets && !calls);
        if(protected)assert(!mprotect((void *)pool,0x100000,PROT_READ|PROT_WRITE));
        free((void *)raw_pool); /* Harness cleanup; production deliberately has no free. */
    }
    puts("PASS: exact original b02, owned 1MB PA alignment/contiguity with page-aligned VA, NC before MEM_SETUP, publish only after approval, AUTH ordering/A6, protected post-call access and held failures");
}
