/* First source-defined A650 HFI command: FW_VER, no GX/CP/rail requests.
 * Caller holds the live mode28 allocation and every parent until reboot.
 * Only firmware writes the response ring; exact echo/result/version required.
 * 1=verified bidirectional DMA,0=retain everything, regardless of failure. */
#include "lmi-gpu-boot-regs.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define IO_CODE __attribute__((noinline,section(".gpu_boot")))
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern void delay(u32,u32);
extern void log_line(const char *);
extern void log_hex(u64);
#ifndef LMI_GPU_HFI_IO_HOST
int IO_CODE cache_sync(u64 address,u32 bytes,int publish) {
    u64 ctr;
    __asm__ volatile("mrs %0, ctr_el0":"=r"(ctr));
    u32 line=4u<<((ctr>>16)&15);
    if(line!=64 && line!=128)return 0;
    __asm__ volatile("dsb sy":::"memory");
    for(u64 at=address&~((u64)line-1);at<address+bytes;at+=line) {
        if(publish)__asm__ volatile("dc cvac, %0"::"r"(at):"memory");
        else __asm__ volatile("dc ivac, %0"::"r"(at):"memory");
    }
    __asm__ volatile("dsb sy":::"memory");
    return 1;
}
#else
extern int cache_sync(u64,u32,int);
#endif
int IO_CODE lmi_gpu_hfi_version(u64 pool,u32 bytes,volatile u32 *g) {
    if(!pool || pool&4095 || bytes<47*4096 || bytes>47*4096+16383 ||
       rsc_read(g+0x14000/4) || (rsc_read(g+0x14070/4)&0x1ff)!=0x100 ||
       rsc_read(g+0x14600/4)!=1 || rsc_read(g+0x14604/4)!=0x20000001 ||
       rsc_read(g+0xafe0/4)!=0x20010008 || rsc_read(g+0xaff0/4)!=0x20000001)return 0;
    u64 address=pool+37*4096;
    volatile u32 *h=(volatile u32 *)address;
    /* RAM preparation already cleaned the allocation to PoC before boot.
     * One command only: firmware cannot advance CMD/MSG indices before its
     * publication. Both indices share a line, so publish that line LAST and
     * never clean it again until CMD consumed + entire MSG published. After
     * that ACK, no second producer can change CMD/MSG during our rd update.
     * CMD starts at byte256, outside every firmware-written queue header.
     * DBG indices reside beyond byte128 and are never cleaned by this code. */
    if(!cache_sync(address,216,0))return 0;
    if(h[0] || h[1]!=54 || h[2]!=6 || h[3]!=12 || h[4]!=4 || h[5]!=4 ||
       h[6]!=1 || h[7]!=0x60001100 || h[8]!=0xa00 || h[9]!=1024 ||
       h[18]!=1 || h[19]!=0x60002100 || h[20]!=0xa01 || h[21]!=1024 ||
       h[16] || h[17] || h[28] || h[29] || rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4))return 0;
    log_line("LMI_GPU_HFI_IO_REQUEST\n");
    const u32 request[]={0x00100201,0x20000000,0xfafafafa,0xfafafafa};
    for(u32 n=0;n<4;n++) {h[64+n]=request[n];log_hex(request[n]);}
    if(!cache_sync(address+256,16,1))return 0;
    h[17]=4;if(!cache_sync(address+64,4,1))return 0;
    rsc_write(g+BOOT_GMU_HOST2GMU_INTR_SET/4,1);
    u32 irq=0,ready=0;
    for(u32 n=0;n<1000;n++) {
        irq=rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4);
        if(!cache_sync(address,128,0))return 0;
        if(irq&~1u || h[16]>4 || h[17]!=4 || h[28] || h[29]>4)break;
        if(h[16]==4 && h[29]==4 && irq==1) {ready=1;break;}
        delay(100,1000);
    }
    if(!cache_sync(address+4352,16,0))return 0;
    log_line("LMI_GPU_HFI_IO_REPLY\n");
    log_hex(h[16]);log_hex(h[17]);log_hex(h[28]);log_hex(h[29]);log_hex(irq);
    u32 reply[4];
    for(u32 n=0;n<4;n++) {reply[n]=h[1088+n];log_hex(reply[n]);}
    if(!ready || irq!=1 || h[16]!=4 || h[17]!=4 || h[28] || h[29]!=4 ||
       (reply[0]&0xfff00)!=0x10400 || reply[1]!=request[0] || reply[2] || reply[3]!=0x20010008)return 0;
    h[28]=4;if(!cache_sync(address+112,4,1))return 0;
    rsc_write(g+BOOT_GMU_GMU2HOST_INTR_CLR/4,1);
    if(rsc_read(g+BOOT_GMU_GMU2HOST_INTR_INFO/4))return 0;
    log_line("LMI_GPU_HFI_IO_ACK_VERIFIED\n");
    return 1;
}
