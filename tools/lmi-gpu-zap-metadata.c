/* GPU13 PAS_INIT_IMAGE only. Pin the phone's original signed MDT.
 * A separate owned, contiguous allocation becomes Normal-NC through XNU's
 * managed-page API (all aliases/TLB/cache handled there), never an NC alias
 * over a live WB mapping. Retain allocation/attributes on every outcome.
 * No MEM_SETUP, AUTH_RESET, SHUTDOWN, MMIO or security register write. */
typedef unsigned long long u64;
typedef unsigned int u32;
#define ZAP __attribute__((noinline,section(".gpu_zap")))
static const char retained[] __attribute__((section(".gpu_extra")))="LMI_GPU_ZAP_METADATA_RETAINED\n";
struct kmem_result {int status;u64 address;};
extern struct kmem_result kmem_alloc_tagged(u64,u64,u64,u32,u64,void *);
extern u64 kernel_map_value,g_phys_base,g_phys_size,xnu_page_size;
extern u32 xnu_page_shift;
extern u64 pa_of(u64);
extern u32 pmap_cache_attributes(u32);
extern void pmap_set_cache_attributes(u32,u32);
extern void *memcpy(void *,const void *,u64);
extern void *memset(void *,int,u64);
extern const unsigned char *image_file(const char *,const char *,u64 *,int *);
extern u32 lmi_gpu_firmware_crc(const unsigned char *,u32);
extern void log_line(const char *);
extern void log_hex(u64);
#ifdef LMI_GPU_ZAP_HOST
extern void zap_smc_step(u64,u64,u64,u64 *);
#else
static void ZAP zap_smc_step(u64 fnid,u64 physical,u64 session,u64 *out) {
    register u64 x0 __asm__("x0")=fnid,x1 __asm__("x1")=0x82,x2 __asm__("x2")=13;
    register u64 x3 __asm__("x3")=physical,x4 __asm__("x4")=0,x5 __asm__("x5")=0;
    register u64 x6 __asm__("x6")=session,x7 __asm__("x7")=0;
    __asm__ volatile("smc #0":"+r"(x0),"+r"(x1),"+r"(x2),"+r"(x3),"+r"(x4),"+r"(x5),"+r"(x6),"+r"(x7)
        ::"x8","x9","x10","x11","x12","x13","x14","x15","x16","x17","memory");
    out[0]=x0;out[1]=x1;out[2]=x6;
}
#endif
int ZAP lmi_gpu_zap_metadata(void) {
    u64 size=0;int disk=-1;
    const unsigned char *fw=image_file("fw","a650_zap.mdt",&size,&disk);
    if(!fw || size!=6860 || lmi_gpu_firmware_crc(fw,6860)!=0x2361d154 ||
       !kernel_map_value || g_phys_base<0x100000000ull || g_phys_size<16384 ||
       g_phys_size>0x180000000ull || !((xnu_page_size==4096 && xnu_page_shift==12) ||
       (xnu_page_size==16384 && xnu_page_shift==14)))return 0;
    u64 bytes=(6860+xnu_page_size-1)&~(xnu_page_size-1);
    struct kmem_result a=kmem_alloc_tagged(kernel_map_value,bytes,0,0,3,0);
    if(a.status || !a.address)return 0;
    u64 pool=a.address,physical=pa_of(pool);
    if(pool&(xnu_page_size-1) || !physical || physical&(xnu_page_size-1) || physical>>36 ||
       physical<g_phys_base || physical-g_phys_base>g_phys_size-bytes)return 0;
    for(u32 at=0;at<bytes;at+=4096)
        if(pa_of(pool+at)!=physical+at || pa_of(pool+at+4095)!=physical+at+4095)return 0;
    for(u32 at=0;at<bytes;at+=xnu_page_size)
        if(pmap_cache_attributes((u32)((physical+at)>>xnu_page_shift))!=2)return 0;
    memset((void *)pool,0,bytes);memcpy((void *)pool,fw,6860);
    if(lmi_gpu_firmware_crc((void *)pool,6860)!=0x2361d154)return 0;
    log_line("LMI_GPU_ZAP_METADATA_CLAIM\n");log_hex(pool);log_hex(physical);log_hex(bytes);log_hex(xnu_page_size);
    for(u32 at=0;at<bytes;at+=xnu_page_size) {
        u32 pn=(u32)((physical+at)>>xnu_page_shift);
        pmap_set_cache_attributes(pn,6); /* VM_WIMG_WCOMB = Normal-NC, not Device on DRAM. */
        if(pmap_cache_attributes(pn)!=6)return 0;
    }
    log_line("LMI_GPU_ZAP_METADATA_NC\n");log_hex(0x2361d154);log_hex(6);
    u64 out[3]={1,0,0};u32 n;
    for(n=0;n<64;n++) {
        zap_smc_step(n?1:0x42000201,physical,out[2],out);
        if(out[0]!=1)break;
    }
    /* No metadata access after handing its physical address to PAS. */
    log_line("LMI_GPU_ZAP_METADATA_REPLY\n");log_hex(out[0]);log_hex(out[1]);log_hex(n==64?64:n+1);
    log_line(retained);
    return !out[0] && !out[1];
}
