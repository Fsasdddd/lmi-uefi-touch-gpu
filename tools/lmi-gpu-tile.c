/* Explicit opt-in: one 16x16 linear BGRA clear in the existing owned scratch
 * page. Mesa24.3 A650 CCU/2D, Linuxv6.12 sequence fences; no new mappings.
 * CPU writes only guard words, never pixels or the three fresh GPU fences. */
typedef unsigned long long u64;
typedef unsigned int u32;
#define TILE __attribute__((noinline,section(".gpu_normal_diag")))
#define TD __attribute__((section(".gpu_normal_diag_data")))
extern u64 io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern int cache_sync(u64,u32,int);
extern int lmi_gpu_cp_complete(volatile u32 *,volatile u32 *,volatile u32 *,u32);
extern u32 lmi_gpu_firmware_crc(const void *,u32);
extern void log_line(const char *);
extern void log_hex(u64);
static const u32 canary TD=0x65065049;
static const char begin[] TD="LMI_GPU_TILE_BEGIN\n",packet[] TD="LMI_GPU_TILE_PACKET\n";
static const char pixels[] TD="LMI_GPU_TILE_PIXELS\n",fences[] TD="LMI_GPU_TILE_FENCES\n";
static const char verified[] TD="LMI_GPU_TILE_VERIFIED_HELD\n";
/* type4/type7 odd parity; A650 has three 64KiB CCU depth caches, so its
 * sysmem color offset is192KiB (RB_CCU_CNTL=0x18000000), not the old board's.
 * Solid R/G/B/A=33/66/cc/ff, format8888 with BGRA swap, stride64 bytes.
 * FLUSH_COLOR_TS/CACHE_FLUSH_TS write distinct words before final MEM_WRITE.
 * Bit30 must stay clear: it selects a timestamp, not the payload sequence. */
static const u32 commands[] TD={
    0x70e50001,12,0x70268000,0x408e0701,0x18000000,
    0x48840502,0,0xf000f,0x488c2c04,0x33,0x66,0xcc,0xff,
    0x408c0001,0x10f03080,0x48840001,0x10f03080,0x48acc001,0xf180,
    0x488c0101,0,0x408c1704,0x430,0x1010100,0,1,
    0x70268000,0x408e0401,0x04100000,0x702c0001,3,0x70268000,0x408e0401,0,
    0x70460004,0x1d,0x1010008,0,0x650c0101,
    0x70460004,4,0x101000c,0,0x650c0102,
    0x70268000,0x703d8003,0x1010010,0,0x650c0de3};
u32 TILE lmi_gpu_tile_canary(u32 v) {return v^*(volatile const u32 *)&canary;}
int TILE lmi_gpu_tile(u64 pool,u32 bytes,volatile u32 *g) {
    u32 fetched=lmi_gpu_tile_canary(0x1badb002);
    log_line(begin);log_hex(fetched);
    if(fetched!=0x7eabe04b || !pool || pool&4095 || bytes!=81920 || !g)return 0;
    volatile u32 *gpu=(void *)io_map(0x3d00000,0x40000),*s=(void *)io_map(0x3da0000,0x10000);
    if(!gpu || !s || rsc_read(gpu+0x806)!=19 || rsc_read(gpu+0x807)!=19 ||
       rsc_read(gpu+0x808)!=1 || !lmi_gpu_cp_complete(gpu,s,g,19))return 0;
    volatile u32 *ring=(void *)pool,*scratch=(void *)(pool+65536);
    if(!cache_sync((u64)scratch,1536,0) || scratch[0]!=0x650c0de1 || scratch[1]!=0x650c0de2)return 0;
    for(u32 n=2;n<384;n++)if(scratch[n])return 0;
    for(u32 n=19;n<68;n++)if(ring[n])return 0;
    for(u32 n=32;n<64;n++) {scratch[n]=0xa55aa55a;scratch[n+288]=0xa55aa55a;}
    if(!cache_sync((u64)scratch,1536,1))return 0;
    log_line(packet);log_hex(49);
    for(u32 n=0;n<49;n++) {ring[19+n]=commands[n];log_hex(commands[n]);}
    if(!cache_sync(pool,384,1))return 0;
    rsc_write(gpu+0x807,68);
    if(!lmi_gpu_cp_complete(gpu,s,g,68) || !cache_sync((u64)scratch,1536,0))return 0;
    log_line(fences);for(u32 n=0;n<5;n++)log_hex(scratch[n]);
    u32 bad=0;
    const u32 values[]={0x650c0de1,0x650c0de2,0x650c0101,0x650c0102,0x650c0de3};
    for(u32 n=0;n<384;n++) {
        u32 expected=n<5?values[n]:n>=64 && n<320?0xff3366cc:
            (n>=32 && n<64) || (n>=320 && n<352)?0xa55aa55a:0;
        if(scratch[n]!=expected)bad++;
    }
    log_line(pixels);log_hex(256);log_hex(bad);
    log_hex(lmi_gpu_firmware_crc((const void *)(scratch+64),1024));
    if(bad)return 0;
    log_line(verified);return 1;
}
#ifndef LMI_GPU_DESKTOP
int TILE lmi_gpu_tile_opt(u64 pool,u32 bytes,volatile u32 *g) {
    extern int boot_arg(const char *,void *,int);
    u32 opt=0;
    int good=boot_arg("lmi_gpu_tile",&opt,4) && opt==1 && lmi_gpu_tile(pool,bytes,g);
    log_line("LMI_GPU_TILE_RESULT\n");log_hex(good);return good;
}
#endif
