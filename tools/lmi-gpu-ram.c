/* lmi GMU stage7: owned wired RAM and software tables only. No MMIO. */
typedef unsigned int u32;
typedef unsigned long long u64;
#ifdef LMI_GPU_GMU_BOOT
#include "lmi-gpu-runtime.h"
#endif
#ifdef LMI_GPU_RAM_HFI
enum {PAYLOAD_PAGES=42,TOTAL_PAGES=47,SEGMENTS=5};
extern int lmi_hfi_prepare(void *,u32,u32);
#else
enum {PAYLOAD_PAGES=37,TOTAL_PAGES=42,SEGMENTS=4};
#endif
struct kmem_result {int status;u64 address;};
extern struct kmem_result kmem_alloc_tagged(u64,u64,u64,u32,u64,void *);
extern void kmem_free3(u64,u64,u64);
extern u64 pa_of(u64);
extern void clean_cache(u64,u32,int);
extern u64 kernel_map_value,boot_args_ptr,g_phys_base,g_phys_size,xnu_page_size;
extern u32 xnu_page_shift;
extern const unsigned char *image_file(const char *,const char *,u64 *,int *);
extern void *memset(void *,int,u64);
extern void *memcpy(void *,const void *,u64);
extern void log_line(const char *);
extern void log_hex(u64);
#ifdef LMI_GPU_GMU_ROUTE
/* Keep every validation; compact the old per-field diagnostic text. */
#define field(label,value) ((void)(value))
#else
static void field(const char *s,u64 v) {log_line(s);log_hex(v);}
#endif
#ifdef LMI_GPU_GMU_ROUTE
#define RAM_HELPER __attribute__((noinline,section(".gpu_helpers")))
#ifdef LMI_GPU_GMU_BOOT
#define RAM_CONST __attribute__((section(".gpu_boot_data")))
#define RAM_BOOT_CONST RAM_CONST
#else
#define RAM_CONST __attribute__((section(".gpu_extra")))
#define RAM_BOOT_CONST
#endif
#else
#define RAM_HELPER
#define RAM_CONST
#define RAM_BOOT_CONST
#endif
u32 RAM_HELPER lmi_gpu_firmware_crc(const unsigned char *p,u32 size) {
    u32 c=~0u;
    for(u32 n=0;n<size;n++) {
        c^=p[n];
        for(int b=0;b<8;b++)c=(c>>1)^((0u-(c&1))&0xedb88320u);
    }
    return ~c;
}
static int ram_refused(const char *label,u32 reason) {
#ifdef LMI_GPU_GMU_ROUTE
    (void)label;log_line("LMI_GPU_RAM_REFUSED\n");log_hex(reason);
#else
    (void)reason;log_line(label);
#endif
    return 2;
}
static int in_window(u64 pa,u64 base,u64 size) {
    return size>=4096 && pa>=base && pa-base<=size-4096;
}
static u64 RAM_HELPER walk(u64 address,u64 **tables,const u64 *pas) {
    const u64 mask=0x0000fffffffff000ULL;
    if(address>>36)return 0;
    u64 *table=tables[0];
    for(int level=0;level<3;level++) {
        unsigned shift=30-level*9;
        u64 entry=table[(address>>shift)&511];
        if(!entry)return 0;
        if((entry&~mask)!=(level==2?0xe03:3))return ~0ULL;
        if(level==2)return (entry&mask)|(address&4095);
        int found=-1;
        for(int k=0;k<5;k++)if(pas[k]==(entry&mask))found=k;
        if(found<0)return ~0ULL;
        table=tables[found];
    }
    return ~0ULL;
}
/* Consumer returns positive only after all hardware references are restored.
 * 2 means safely detached but incomplete; zero/negative retains backing. */
typedef int (*lmi_ram_consumer)(u64 root,void *context);
int lmi_gpu_ram_consume(lmi_ram_consumer consumer,void *context) {
    static const struct segment {u32 address,size,file_offset,payload;} segments[] RAM_BOOT_CONST={
        {0x4000,0x8000,14812,21968}, {0x144000,0x13000,0,0},
        {0x157000,0x9000,36796,920}, {0x60000000,0x1000,0,0}
#ifdef LMI_GPU_RAM_HFI
        ,{0x60001000,0x5000,0,0}
#endif
    };
    static const u32 unmapped[] RAM_CONST={0,0x3000,0xc000,0x143000,0x160000,
#ifdef LMI_GPU_RAM_HFI
        0x60006000,
#else
        0x60001000,
#endif
        0x10004000};
    u64 fw_size=0;int disk=-1;
    const unsigned char *fw=image_file("fw","a650_gmu.bin",&fw_size,&disk);
    if(!fw || fw_size!=41548 || lmi_gpu_firmware_crc(fw,41548)!=0x5c66275c) {
        return ram_refused("LMI_GPU_RAM_FIRMWARE_REFUSED\n",1);
    }
    if(!boot_args_ptr || !kernel_map_value ||
       !((xnu_page_size==4096 && xnu_page_shift==12) ||
         (xnu_page_size==16384 && xnu_page_shift==14))) {
        return ram_refused("LMI_GPU_RAM_ABI_REFUSED\n",2);
    }
    const u64 *boot=(const u64 *)boot_args_ptr;
    u64 claim_base=boot[2],claim_size=boot[3];
    if(claim_base<0x100000000ULL || claim_size!=0x180000000ULL ||
       claim_base+claim_size<claim_base || g_phys_base!=claim_base ||
       !g_phys_size || g_phys_size>claim_size) {
        return ram_refused("LMI_GPU_RAM_WINDOW_REFUSED\n",3);
    }
    log_line("LMI_GPU_RAM_BEGIN\n");
    field("LMI_GPU_RAM_CLAIM_BASE\n",claim_base);
    field("LMI_GPU_RAM_CLAIM_SIZE\n",claim_size);
    field("LMI_GPU_RAM_XNU_PAGE\n",xnu_page_size);
    u64 bytes=(TOTAL_PAGES*4096+xnu_page_size-1)&~(xnu_page_size-1),pool=0;
    /* The exported three-argument shim derives a tag from return addresses.
     * Injected code has no registered VM tag: use explicit IOKIT tag3. The
     * pinned internal ABI returns status/address in x0/x1, guard in x4. */
    struct kmem_result allocation=kmem_alloc_tagged(kernel_map_value,bytes,0,0,3,0);
    pool=allocation.address;
    if(allocation.status!=0) {
        return ram_refused("LMI_GPU_RAM_ALLOC_FAILED\n",4);
    }
    if(!pool)return ram_refused("LMI_GPU_RAM_ALLOC_ABI_FAILED\n",5);
    u32 failed=1,retain=0;u64 pas[TOTAL_PAGES];u64 *tables[5];
    if(!pool || (pool&(xnu_page_size-1)))goto done;
    memset((void *)pool,0,bytes);
    for(int n=0;n<TOTAL_PAGES;n++) {
        u64 va=pool+(u64)n*4096,pa=pa_of(va);
        if(!pa || (pa&4095) || (pa>>36) ||
           !in_window(pa,claim_base,claim_size) ||
           !in_window(pa,g_phys_base,g_phys_size) || pa_of(va+4095)!=pa+4095)goto done;
        for(int k=0;k<n;k++)if(pas[k]==pa)goto done;
        pas[n]=pa;
    }
    for(int n=0;n<TOTAL_PAGES;n++) {
        field("LMI_GPU_RAM_PAGE_INDEX\n",n);
        field("LMI_GPU_RAM_PAGE_PA\n",pas[n]);
    }
    for(int k=0;k<5;k++)tables[k]=(u64 *)(pool+(PAYLOAD_PAGES+k)*4096);
    tables[0][0]=pas[PAYLOAD_PAGES+1]|3;tables[0][1]=pas[PAYLOAD_PAGES+2]|3;
    tables[1][0]=pas[PAYLOAD_PAGES+3]|3;tables[2][256]=pas[PAYLOAD_PAGES+4]|3;
    u32 slot=0;
    for(int s=0;s<SEGMENTS;s++) {
        const struct segment *v=&segments[s];
        if(v->payload)memcpy((void *)(pool+(u64)slot*4096),fw+v->file_offset,v->payload);
        for(u32 j=0;j<v->size/4096;j++,slot++) {
            u32 address=v->address+j*4096;
            tables[s>=3?4:3][(address>>12)&511]=pas[slot]|0xe03;
        }
    }
    if(slot!=PAYLOAD_PAGES)goto done;
#ifdef LMI_GPU_RAM_HFI
    if(!lmi_hfi_prepare((void *)(pool+37*4096),20480,0x60001000))goto done;
    field("LMI_GPU_RAM_HFI_ADDRESS\n",0x60001000);
    field("LMI_GPU_RAM_HFI_BYTES\n",20480);
#endif
#ifdef LMI_GPU_RAM_HFI
    log_line("LMI_GPU_RAM_HFI_RING_OFFSET\n");log_hex(256);
#endif
    clean_cache(pool,(u32)bytes,0);
    __asm__ volatile("dsb sy":::"memory");
#ifdef LMI_GPU_GMU_ROUTE
    log_line("LMI_GPU_RAM_SEGMENTS\n");
#endif
    slot=0;
    for(int s=0;s<SEGMENTS;s++) {
        const struct segment *v=&segments[s];
        const unsigned char *memory=(const unsigned char *)(pool+(u64)slot*4096);
        for(u32 j=0;j<v->size;j++) {
            unsigned char expected=j<v->payload?fw[v->file_offset+j]:0;
#ifdef LMI_GPU_RAM_HFI
            if(s==4 && j<216) {
                u32 word=j/4,value=0;
                if(word<6) {const u32 h[]={0,54,6,12,4,4};value=h[word];}
                else {
                    u32 queue=(word-6)/12,member=(word-6)%12;
                    if(member==0)value=queue<3;
                    if(member==1)value=0x60001000+256+queue*4096;
                    if(member==2)value=queue|((queue==2?40:queue==3?20:10)<<8);
                    if(member==3)value=1024;
                }
                expected=(unsigned char)(value>>(8*(j&3)));
            }
#endif
            if(memory[j]!=expected)goto done;
        }
        field("LMI_GPU_RAM_SEGMENT_ADDRESS\n",v->address);
        field("LMI_GPU_RAM_SEGMENT_CRC\n",lmi_gpu_firmware_crc(memory,v->size));
#ifdef LMI_GPU_GMU_ROUTE
        log_hex(((u64)v->address<<32)|lmi_gpu_firmware_crc(memory,v->size));
#endif
        for(u32 j=0;j<v->size/4096;j++,slot++) {
            u64 address=v->address+j*4096;
            if(walk(address,tables,pas+PAYLOAD_PAGES)!=pas[slot] ||
               walk(address+17,tables,pas+PAYLOAD_PAGES)!=pas[slot]+17 ||
               walk(address+2048,tables,pas+PAYLOAD_PAGES)!=pas[slot]+2048 ||
               walk(address+4095,tables,pas+PAYLOAD_PAGES)!=pas[slot]+4095)goto done;
        }
    }
    for(u32 n=0;n<sizeof(unmapped)/sizeof(unmapped[0]);n++)
        if(walk(unmapped[n],tables,pas+PAYLOAD_PAGES)!=0)goto done;
    u32 table_entries=0,leaves=0;
    for(int k=0;k<5;k++)for(int n=0;n<512;n++)if(tables[k][n]) {
        if(k<3)table_entries++;else leaves++;
    }
    if(table_entries!=4 || leaves!=PAYLOAD_PAGES)goto done;
    field("LMI_GPU_RAM_WIRED_BYTES\n",bytes);
    field("LMI_GPU_RAM_PAYLOAD_PAGES\n",leaves);
    field("LMI_GPU_RAM_TABLE_PAGES\n",5);
    field("LMI_GPU_RAM_ROOT_PA\n",pas[PAYLOAD_PAGES]);
    log_line("LMI_GPU_RAM_SOFTWARE_WALK_OK\n");
#ifdef LMI_GPU_GMU_ROUTE
    log_line("LMI_GPU_RAM_LIVE_MAP\n");
    log_hex(claim_base);log_hex(claim_size);log_hex(xnu_page_size);log_hex(bytes);
    log_hex(pas[PAYLOAD_PAGES]);
    for(u32 n=0;n<TOTAL_PAGES;n++)log_hex(pas[n]);
#endif
    if(consumer) {
#ifdef LMI_GPU_GMU_BOOT
        struct lmi_gpu_live_backing live={context,pool,(u32)bytes};
        int status=consumer(pas[PAYLOAD_PAGES],&live);
        if(status==3) {retain=2;failed=0;goto done;}
#else
        int status=consumer(pas[PAYLOAD_PAGES],context);
#endif
        if(status<=0) {retain=1;goto done;}
        if(status!=1)goto done;
    }
    failed=0;
done:
    if(retain) {
#ifdef LMI_GPU_GMU_BOOT
        static const char active[] RAM_CONST="LMI_GPU_RAM_ACTIVE_RETAINED\n";
        log_line(retain==2?active:"LMI_GPU_RAM_RETAINED\n");
#else
        log_line("LMI_GPU_RAM_RETAINED\n");
#endif
    }
    else {
        kmem_free3(kernel_map_value,pool,bytes);
        log_line("LMI_GPU_RAM_CLEANUP_DONE\n");
    }
    field("LMI_GPU_RAM_FAILED\n",failed);
    log_line("LMI_GPU_RAM_END\n");
#ifdef LMI_GPU_GMU_ROUTE
    log_line("LMI_GPU_RAM_CONSUMER_RESULT\n");log_hex(retain==2?3:retain?0:failed?2:1);
#endif
    return retain==2?3:retain?0:failed?2:1;
}
void lmi_gpu_ram_use(lmi_ram_consumer consumer,void *context) {(void)lmi_gpu_ram_consume(consumer,context);}
void lmi_gpu_ram_plan(void) {lmi_gpu_ram_use(0,0);}
