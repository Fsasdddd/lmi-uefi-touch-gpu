#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-core-memory.c"
static unsigned char firmware[31632];
static u32 g[0xc000],s[0x4000],scenario,allocs,frees,cleaned,writes,synced,verbose,ticks;
static u64 boot[4]={0,0,0x100000000ull,0x180000000ull},pool,allocation_bytes;
u64 kernel_map_value=0xf00,boot_args_ptr=(u64)boot,g_phys_base=0x100000000ull,g_phys_size=0x180000000ull,xnu_page_size;
u32 xnu_page_shift;
void log_line(const char *p) {if(verbose)fputs(p,stdout);}
void log_hex(u64 v) {if(verbose)printf("%016llx\n",v);}
u32 lmi_gpu_firmware_crc(const unsigned char *p,u32 size) {
    u32 c=~0u;for(u32 n=0;n<size;n++) {c^=p[n];for(int b=0;b<8;b++)c=c>>1^((0u-(c&1))&0xedb88320u);}return ~c;
}
const unsigned char *image_file(const char *d,const char *n,u64 *z,int *disk) {assert(!strcmp(d,"fw") && !strcmp(n,"a650_sqe.fw"));*z=scenario==2?12:31632;*disk=1;return scenario==1?0:firmware;}
struct kmem_result kmem_alloc_tagged(u64 map,u64 bytes,u64 mask,u32 flags,u64 tag,void *callback) {
    assert(map==kernel_map_value && bytes==81920 && !mask && !flags && tag==3 && !callback && !pool);allocs++;
    if(scenario==3)return (struct kmem_result){1,0};
    pool=(u64)aligned_alloc(xnu_page_size,bytes);assert(pool);allocation_bytes=bytes;return (struct kmem_result){0,pool};
}
void kmem_free3(u64 map,u64 p,u64 bytes) {assert(map==kernel_map_value && p==pool && bytes==allocation_bytes && !writes);free((void *)pool);pool=0;frees++;}
static u64 physical(u32 n) {return g_phys_base+0x200000+((n*7)%20)*0x3000;}
u64 pa_of(u64 va) {
    assert(va>=pool && va<pool+allocation_bytes);u32 page=(u32)(va-pool)/4096,off=(u32)(va-pool)&4095;
    if(scenario==4 && page==3)return off;
    if(scenario==5 && page==3)return physical(2)+off;
    if(scenario==6 && page==3)return g_phys_base+g_phys_size+off;
    if(scenario==7 && page==3 && off)return physical(page)+off-1;
    return physical(page)+off;
}
int cache_sync(u64 p,u32 bytes,int publish) {
    assert(p==pool && bytes==81920 && publish && !writes);cleaned++;
    const u64 *a=(void *)(pool+17*4096),*b=(void *)(pool+18*4096),*c=(void *)(pool+19*4096);
    assert(a[0]==(physical(18)|3) && b[8]==(physical(19)|3));
    for(u32 n=0;n<512;n++) {assert(c[n]==(n<17?(physical(n)|(n>=8 && n<16?0xec3:0xe43)):0));if(n)assert(!a[n]);if(n!=8)assert(!b[n]);}
    assert(!memcmp((void *)(pool+8*4096),firmware+4,31628));
    for(u32 n=0;n<8*4096;n++)assert(!((unsigned char *)pool)[n]);
    for(u32 n=16*4096;n<17*4096;n++)assert(!((unsigned char *)pool)[n]);
    return scenario!=8;
}
u64 io_map(u64 address,u64 bytes) {assert(address==0x3da0000 && bytes==sizeof(s));return (u64)s;}
u32 rsc_read(volatile u32 *p) {if(p>=g && p<g+0xc000)return *p;assert(p>=s && p<s+0x4000);if(p==s+0x97f4/4)return scenario==10?1:0;return *p;}
void rsc_write(volatile u32 *p,u32 v) {
    assert(p>=s && p<s+0x4000 && cleaned==1 && !frees && pool);
    u32 off=(u32)(p-s)*4;assert(off!=0x800 && off!=0xc00 && off<0x9800);
    if(writes<10) {assert(off==offsets[writes] && !(s[0x9000/4]&1) && !s[0x804/4]);}
    else if(!synced) {assert((off==0x9610 && v==2) || (off==0x97f0 && !v));if(off==0x97f0)synced=1;}
    else {assert(off==offsets[writes-2]);if(off==0x804)assert(v==0x84010000 && s[0x9000/4]==0xc000e7 && (s[0xc04/4]&0x030303ff)==0x301);}
    writes++;
    if(scenario>=20 && writes==scenario-19)return;
    *p=v;if(off==0x9000 && v&1)s[0x9058/4]=0x400;
    if(scenario==11 && off==0x804)s[0x9058/4]|=2;
}
void delay(u32 count,u32 unit) {assert(count==1 && unit==1000 && ++ticks<=1000);}
static void seed(void) {
    if(pool) {free((void *)pool);pool=0;}memset(g,0,sizeof(g));memset(s,0,sizeof(s));allocs=frees=cleaned=writes=synced=ticks=scenario=0;
    s[0x20/4]=0x4c017e06;s[0x24/4]=0x20000005;s[0x800/4]=0x84000005;s[0xc04/4]=0x19363bff;s[0x9000/4]=0x12a36116;
}
int main(int argc,char **argv) {
    assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f && fread(firmware,1,sizeof(firmware),f)==sizeof(firmware));fclose(f);
    for(xnu_page_size=4096;xnu_page_size<=16384;xnu_page_size*=4) {
        xnu_page_shift=xnu_page_size==4096?12:14;
        seed();verbose=xnu_page_size==16384;assert(lmi_gpu_core_memory(g));verbose=0;assert(allocs==1 && !frees && writes==15 && synced && pool);
        for(u32 n=1;n<=11;n++) {seed();scenario=n;if(n==9)s[0x9000/4]|=1;assert(!lmi_gpu_core_memory(g));if(n>=9)assert(pool && !frees);else if(n>=4)assert(frees==1 && !pool);}
        for(u32 n=20;n<=34;n++) {seed();scenario=n;/* Zero writes can be ignored without a mismatch. */int ok=lmi_gpu_core_memory(g);if(ok)assert(n==26 || n==27 || n==29 || n==30 || n==31);assert(!frees && pool);}
        seed();g[BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4]=0xc0;assert(!lmi_gpu_core_memory(g) && !allocs);
        seed();s[0x808/4]=0x80000002;assert(!lmi_gpu_core_memory(g) && !writes && pool);
        seed();s[0x1804/4]=1;assert(!lmi_gpu_core_memory(g) && !writes && pool);
    }
    seed();puts("PASS: noncontiguous owned GPU backing, RO SQE + user RW ring/scratch tables, CB1-only writes, ASID2 sync, SID0/1 publication last, failures retain DMA memory");
}
