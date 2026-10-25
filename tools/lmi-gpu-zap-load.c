/* Continue successful GPU13 INIT_IMAGE with the original relocatable b02.
 * Only owned contiguous memory, PAS_MEM_SETUP and PAS_AUTH_AND_RESET.
 * No shutdown/error-as-loaded fallback or security-register writes.
 * Caller keeps every allocation, mapping and parent until bounded reboot. */
typedef unsigned long long u64;
typedef unsigned int u32;
#define LOAD __attribute__((noinline,section(".gpu_zap_load")))
static const char authenticated[] __attribute__((section(".gpu_extra")))="LMI_GPU_ZAP_AUTHENTICATED_HELD\n";
extern void *alloc_contiguous(u64,u64,u64 *);
extern u64 pa_of(u64);
extern u64 g_phys_base,g_phys_size,xnu_page_size;
extern u32 xnu_page_shift;
extern u32 pmap_cache_attributes(u32);
extern void pmap_set_cache_attributes(u32,u32);
extern void *memcpy(void *,const void *,u64);
extern void *memset(void *,int,u64);
extern const unsigned char *image_file(const char *,const char *,u64 *,int *);
extern u32 lmi_gpu_firmware_crc(const unsigned char *,u32);
extern void log_line(const char *);
extern void log_hex(u64);
static const u32 canary __attribute__((section(".gpu_zap_load_data")))=0x65065045;
u32 LOAD lmi_gpu_zap_code_canary(u32 input) {return input^*(volatile const u32 *)&canary;}
#ifdef LMI_GPU_ZAP_LOAD_HOST
extern void zap_load_step(u64,u64,u64,u64,u64,u64 *);
#else
static void LOAD zap_load_step(u64 function,u64 info,u64 physical,u64 span,u64 session,u64 *out) {
    register u64 x0 __asm__("x0")=function,x1 __asm__("x1")=info,x2 __asm__("x2")=13;
    register u64 x3 __asm__("x3")=physical,x4 __asm__("x4")=span,x5 __asm__("x5")=0;
    register u64 x6 __asm__("x6")=session,x7 __asm__("x7")=0;
    __asm__ volatile("dsb sy\n\tsmc #0":"+r"(x0),"+r"(x1),"+r"(x2),"+r"(x3),"+r"(x4),"+r"(x5),"+r"(x6),"+r"(x7)
        ::"x8","x9","x10","x11","x12","x13","x14","x15","x16","x17","memory");
    out[0]=x0;out[1]=x1;out[2]=x6;
}
#endif
static int LOAD pas(u32 command,u64 physical,u64 span) {
    u64 out[3]={1,0,0};u32 n;
    for(n=0;n<64;n++) {
        zap_load_step(n?1:(0x42000200u|command),command==2?3:1,physical,span,out[2],out);
        if(out[0]!=1)break;
    }
    log_line("LMI_GPU_ZAP_LOAD_SMC\n");log_hex(command);log_hex(out[0]);log_hex(out[1]);log_hex(n==64?64:n+1);
    return !out[0] && !out[1];
}
int LOAD lmi_gpu_zap_load(void) {
    u32 fetched=lmi_gpu_zap_code_canary(0x1badb002);
    log_line("LMI_GPU_ZAP_CODE_CANARY\n");log_hex(fetched);
    if(fetched!=0x7eabe047)return 0;
    u64 size=0;int disk=-1;
    const unsigned char *fw=image_file("fw","a650_zap.b02",&size,&disk);
    if(!fw || size!=1676 || lmi_gpu_firmware_crc(fw,1676)!=0x5384b346 ||
       g_phys_base<0x100000000ull || g_phys_size<0x100000 || g_phys_size>0x180000000ull ||
       !((xnu_page_size==4096 && xnu_page_shift==12) || (xnu_page_size==16384 && xnu_page_shift==14)))return 0;
    u64 pool=(u64)alloc_contiguous(0x100000,0x100000,0);
    /* Record the allocator's raw return before enforcing alignment/window.
     * Successful PAS replies still require every guard below to pass. */
    log_line("LMI_GPU_ZAP_PAYLOAD_CLAIM\n");log_hex(pool);
    /* kmem's pointer-range VA allocator does not consume the alignment mask.
     * PAS receives the PA, which must still meet the full 1MB restriction.
     * CPU accesses and cache-attribute updates need only an XNU-page VA. */
    if(!pool || pool&(xnu_page_size-1))return 0;
    u64 physical=pa_of(pool);
    log_hex(physical);log_hex(0x100000);log_hex(xnu_page_size);
    if(!physical || physical&0xfffff || physical>>36 || physical<g_phys_base ||
       physical-g_phys_base>g_phys_size-0x100000)return 0;
    for(u32 at=0;at<0x100000;at+=4096)
        if(pa_of(pool+at)!=physical+at || pa_of(pool+at+4095)!=physical+at+4095)return 0;
    for(u32 at=0;at<0x100000;at+=xnu_page_size)
        if(pmap_cache_attributes((u32)((physical+at)>>xnu_page_shift))!=2)return 0;
    for(u32 at=0;at<0x100000;at+=xnu_page_size) {
        u32 pn=(u32)((physical+at)>>xnu_page_shift);
        pmap_set_cache_attributes(pn,6);
        if(pmap_cache_attributes(pn)!=6)return 0;
    }
    if(!pas(2,physical,0x1000))return 0; /* Signed ELF min5000..rounded max6000. */
    memset((void *)pool,0,0x100000);memcpy((void *)pool,fw,1676);
    u32 crc=lmi_gpu_firmware_crc((void *)pool,1676);
    log_line("LMI_GPU_ZAP_PAYLOAD_CRC\n");log_hex(crc);
    if(crc!=0x5384b346)return 0;
    for(u32 n=1676;n<0x100000;n++)if(((volatile const unsigned char *)pool)[n])return 0;
    if(!pas(5,0,0))return 0;
    log_line(authenticated);return 1;
}
