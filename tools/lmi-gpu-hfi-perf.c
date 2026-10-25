/* Source-defined second HFI transaction, PERF_TBL only. No CORE_FW_START/GX.
 * Requires the successful one-shot FW_VER and validated mode30 plan.
 * 1=exact ACK,0=retain all DMA and parents until bounded reset. */
#include "lmi-gpu-boot-regs.h"
#include "lmi-gpu-table-plan.h"
#include "lmi-gpu-hfi-transfer.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define PERF __attribute__((noinline,section(".gpu_hfi_perf")))
extern int cache_sync(u64,u32,int);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern u64 io_map_memory(u64,u64);
extern void delay(u32,u32);
extern void log_line(const char *);
extern void log_hex(u64);
int PERF lmi_gpu_hfi_exchange(u64 pool,u32 bytes,volatile u32 *g,const u32 *words,u32 count,u32 cmd,u32 msg,const struct lmi_hfi_trace *trace) {
    if(!pool || pool&4095 || bytes<47*4096 || bytes>47*4096+16383 || !words || !trace ||
       !count || count>160 || count!=((words[0]>>8)&255) || cmd&3 || msg&3 ||
       cmd>1024-((count+3)&~3u) || msg>1020)return 0;
    u32 end=cmd+((count+3)&~3u),next=msg+4;
    u64 address=pool+37*4096;volatile u32 *h=(void *)address;
    if(!cache_sync(address,128,0) || h[16]!=cmd || h[17]!=cmd || h[28]!=msg || h[29]!=msg ||
       rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4))return 0;
    log_line(trace->request);
    for(u32 n=0;n<count;n++) {h[64+cmd+n]=words[n];log_hex(words[n]);}
    for(u32 n=cmd+count;n<end;n++)h[64+n]=0xfafafafa;
    if(!cache_sync(address+256+4*cmd,4*(end-cmd),1))return 0;
    h[17]=end;if(!cache_sync(address+64,4,1))return 0;
    rsc_write(g+BOOT_GMU_HOST2GMU_INTR_SET/4,1);
    u32 irq=0,ready=0;
    for(u32 n=0;n<1000;n++) {
        irq=rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4);
        if(!cache_sync(address,128,0))return 0;
        if(irq&~1u || h[16]>end || h[17]!=end || h[28]!=msg || h[29]>next)break;
        if(h[16]==end && h[29]==next && irq==1) {ready=1;break;}
        delay(100,1000);
    }
    if(!cache_sync(address+4352+4*msg,16,0))return 0;
    log_line(trace->reply);
    log_hex(h[16]);log_hex(h[17]);log_hex(h[28]);log_hex(h[29]);log_hex(irq);
    u32 reply[3];for(u32 n=0;n<3;n++) {reply[n]=h[1088+msg+n];log_hex(reply[n]);}
    if(!ready || irq!=1 || h[16]!=end || h[17]!=end || h[28]!=msg || h[29]!=next ||
       (reply[0]&0xfff00)!=0x10300 || reply[1]!=words[0] || reply[2])return 0;
    h[28]=next;if(!cache_sync(address+112,4,1))return 0;
    rsc_write(g+BOOT_GMU_GMU2HOST_INTR_CLR/4,1);
    if(rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4))return 0;
    log_line(trace->verified);return 1;
}
int PERF lmi_gpu_hfi_perf(u64 pool,u32 bytes,volatile u32 *g) {
    struct lmi_gpu_perf_table table;
    if(!lmi_gpu_prepare_perf((void *)io_map_memory(0x80860000,0x20000),0x20000,&table))return 0;
    table.hdr=0x00203b04;
    const struct lmi_hfi_trace trace={"LMI_GPU_HFI_PERF_REQUEST\n","LMI_GPU_HFI_PERF_REPLY\n","LMI_GPU_HFI_PERF_ACK_VERIFIED\n"};
    return lmi_gpu_hfi_exchange(pool,bytes,g,(const u32 *)&table,59,4,4,&trace);
}
