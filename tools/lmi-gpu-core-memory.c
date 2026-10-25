/* Mode35: owned GPU-only ring/SQE/scratch and CB1 SID0/1 translation.
 * No CP/GPU/secure writes. Published or uncertain references live until reboot. */
#include "lmi-gpu-boot-regs.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define MEM __attribute__((noinline,section(".gpu_core_mem")))
#define ATTACH __attribute__((noinline,section(".gpu_core_attach")))
struct kmem_result {int status;u64 address;};
extern struct kmem_result kmem_alloc_tagged(u64,u64,u64,u32,u64,void *);
extern void kmem_free3(u64,u64,u64);
extern u64 kernel_map_value,boot_args_ptr,g_phys_base,g_phys_size,xnu_page_size;
extern u32 xnu_page_shift;
extern u64 pa_of(u64),io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern void delay(u32,u32);
extern int cache_sync(u64,u32,int);
extern void *memset(void *,int,__SIZE_TYPE__),*memcpy(void *,const void *,__SIZE_TYPE__);
extern const unsigned char *image_file(const char *,const char *,u64 *,int *);
extern u32 lmi_gpu_firmware_crc(const unsigned char *,u32);
extern void log_line(const char *);
extern void log_hex(u64);
#ifdef LMI_GPU_TILE
#define OFFSET_DATA __attribute__((section(".gpu_normal_diag_data")))
#else
#define OFFSET_DATA __attribute__((section(".gpu_core_mem_data")))
#endif
static const u32 offsets[] OFFSET_DATA={
    0x1804,0x1004,0x9010,0x9030,0x9020,0x9024,0x9028,0x902c,0x9038,0x903c,0x9000,0xc04,0x804,0x9058,0x48};
int ATTACH lmi_gpu_core_attach(volatile u32 *s,u64 root) {
    if(!s || !root || root&4095 || root>>36 || rsc_read(s+0x20/4)!=0x4c017e06 ||
       rsc_read(s+0x24/4)!=0x20000005 || rsc_read(s+0x800/4)!=0x84000005 ||
       rsc_read(s+0x9000/4)&1 || rsc_read(s+0x1004/4) || rsc_read(s+0x1804/4) ||
       rsc_read(s+0x9058/4) || rsc_read(s+0x48/4))return 0;
    for(u32 n=1;n<6;n++)if(rsc_read(s+0x800/4+n))return 0;
    u32 target[]={1,0x1f300,0x38071,0x803519,(u32)root,(u32)(root>>32)|0x20000,
        0,0,0xf404ff44,0,0xc000e7,0,0x84010000};
    target[11]=(rsc_read(s+0xc04/4)&~0x030303ffu)|0x301;
    log_line("LMI_GPU_CORE_ATTACH_BEGIN\n");
    for(u32 n=0;n<13;n++) {
        if(n==10) {
            rsc_write(s+0x9610/4,2);rsc_write(s+0x97f0/4,0);
            u32 ready=0;
            for(u32 k=0;k<1000;k++) {if(!(rsc_read(s+0x97f4/4)&1)) {ready=1;break;}delay(1,1000);}
            if(!ready)return 0;
        }
        rsc_write(s+offsets[n]/4,target[n]);
        if(rsc_read(s+offsets[n]/4)!=target[n])return 0;
    }
    log_line("LMI_GPU_CORE_ATTACH_ACTUAL\n");
    for(u32 n=0;n<15;n++)log_hex(((u64)(0x3da0000+offsets[n])<<32)|rsc_read(s+offsets[n]/4));
    for(u32 n=0;n<13;n++)if(rsc_read(s+offsets[n]/4)!=target[n])return 0;
    if(rsc_read(s+0x9058/4)!=0x400 || rsc_read(s+0x48/4) || rsc_read(s+0x800/4)!=0x84000005)return 0;
    for(u32 n=2;n<6;n++)if(rsc_read(s+0x800/4+n))return 0;
    log_line("LMI_GPU_CORE_ATTACHED_HELD\n");return 1;
}
int MEM lmi_gpu_core_memory(volatile u32 *g) {
    u64 size=0;int disk=-1;const unsigned char *fw=image_file("fw","a650_sqe.fw",&size,&disk);
    if(!g || rsc_read(g+BOOT_GMU_SPTPRAC_PWR_CLK_STATUS/4)&0xc0 || !fw || size!=31632 ||
       lmi_gpu_firmware_crc(fw,31632)!=0x1f3285db || !kernel_map_value || !boot_args_ptr ||
       !((xnu_page_size==4096 && xnu_page_shift==12) || (xnu_page_size==16384 && xnu_page_shift==14)))return 0;
    const u64 *boot=(const u64 *)boot_args_ptr;u64 base=boot[2],span=boot[3];
    if(base<0x100000000ull || span!=0x180000000ull || base+span<base || g_phys_base!=base ||
       g_phys_size<4096 || g_phys_size>span)return 0;
    u64 bytes=(20*4096+xnu_page_size-1)&~(xnu_page_size-1);
    struct kmem_result a=kmem_alloc_tagged(kernel_map_value,bytes,0,0,3,0);
    if(a.status || !a.address)return 0;
    u64 pool=a.address,pas[20];int good=0;
    if(pool&(xnu_page_size-1))goto done;
    memset((void *)pool,0,bytes);
    for(u32 n=0;n<20;n++) {
        u64 va=pool+4096*n,pa=pa_of(va);
        if(!pa || pa&4095 || pa>>36 || pa<base || pa-base>g_phys_size-4096 ||
           pa_of(va+4095)!=pa+4095)goto done;
        for(u32 k=0;k<n;k++)if(pa==pas[k])goto done;
        pas[n]=pa;
    }
    memcpy((void *)(pool+8*4096),fw+4,31628);
    u64 *l1=(void *)(pool+17*4096),*l2=(void *)(pool+18*4096),*l3=(void *)(pool+19*4096);
    l1[0]=pas[18]|3;l2[8]=pas[19]|3;
    for(u32 n=0;n<17;n++)l3[n]=pas[n]|(n>=8 && n<16?0xec3:0xe43);
    /* Full table/sparse-gap checks plus SQE content and zero tail check. */
    for(u32 n=0;n<512;n++)if(l1[n]!=(n==0?(pas[18]|3):0) || l2[n]!=(n==8?(pas[19]|3):0) ||
        l3[n]!=(n<17?(pas[n]|(n>=8 && n<16?0xec3:0xe43)):0))goto done;
    for(u32 n=0;n<8*4096;n++)if(((const unsigned char *)(pool+8*4096))[n]!=(n<31628?fw[n+4]:0))goto done;
    if(!cache_sync(pool,(u32)bytes,1))goto done;
    log_line("LMI_GPU_CORE_MEMORY\n");log_hex(base);log_hex(span);log_hex(xnu_page_size);log_hex(bytes);
    for(u32 n=0;n<20;n++)log_hex(pas[n]);
    log_line("LMI_GPU_CORE_LAYOUT\n");log_hex(0x1000000);log_hex(0x1008000);log_hex(0x1010000);
    log_hex(lmi_gpu_firmware_crc((void *)(pool+8*4096),31628));
    log_line("LMI_GPU_CORE_SOFTWARE_TABLES_OK\n");
    /* Once the context transaction starts, conservatively retain all pages
     * even if a write or sync fails; never release an uncertain DMA target. */
    good=lmi_gpu_core_attach((void *)io_map(0x3da0000,0x10000),pas[17]);
    log_line("LMI_GPU_CORE_MEMORY_RETAINED\n");
#ifdef LMI_GPU_CORE_ACCESS
    if(good) {
        extern int lmi_gpu_core_access(volatile u32 *);
        good=lmi_gpu_core_access(g);
        log_line("LMI_GPU_CORE_ACCESS_RESULT\n");log_hex(good);
    }
#endif
#ifdef LMI_GPU_CP
    if(good) {
        extern int lmi_gpu_cp(u64,u32,volatile u32 *);
        good=lmi_gpu_cp(pool,(u32)bytes,g);
        log_line("LMI_GPU_CP_RESULT\n");log_hex(good);
    }
#endif
#ifdef LMI_GPU_SCM_QUERY
    if(good) {
        extern int lmi_gpu_scm_available(void);
        good=lmi_gpu_scm_available();
        log_line("LMI_GPU_SCM_RESULT\n");log_hex(good);
    }
#endif
#ifdef LMI_GPU_ZAP_METADATA
    if(good) {
        extern int lmi_gpu_zap_metadata(void);
        good=lmi_gpu_zap_metadata();
        log_line("LMI_GPU_ZAP_METADATA_RESULT\n");log_hex(good);
    }
#endif
#ifdef LMI_GPU_ZAP_LOAD
    if(good) {
        extern int lmi_gpu_zap_load(void);
        good=lmi_gpu_zap_load();
        log_line("LMI_GPU_ZAP_LOAD_RESULT\n");log_hex(good);
    }
#endif
#ifdef LMI_GPU_UNSECURE
    if(good) {
        extern int lmi_gpu_unsecure(u64,u32,volatile u32 *);
        good=lmi_gpu_unsecure(pool,(u32)bytes,g);
        log_line("LMI_GPU_NORMAL_RESULT\n");log_hex(good);
    }
#endif
#ifdef LMI_GPU_TILE
    if(good) {
        extern int lmi_gpu_tile_opt(u64,u32,volatile u32 *);
        good=lmi_gpu_tile_opt(pool,(u32)bytes,g);
    }
#endif
    return good;
done:
    kmem_free3(kernel_map_value,pool,bytes);return 0;
}
