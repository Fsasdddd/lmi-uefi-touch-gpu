/* v63: batch the pages of one native newBuffer() mapping under gGPULock.
 * First page and final mapped() keep actual GPU idle/fence validation; no
 * submission, cache handoff or release may cross an uncommitted batch.
 * v58: one outstanding A650 submission. CPU encoding may overlap execution;
 * cache maintenance, mapping changes and the next submission drain it first.
 * done() samples the real device fence, never the submitted fence.
 * lmi A650 backend for the existing RedwoodGPU user client. Explicit opt-in
 * follows authenticated normal mode AND exact GPU tile pixels. Serialized,
 * bounded submissions keep failed DMA dependencies until the RAM-run reboot.
 * The old board's power/stop/recovery code is never entered by this profile. */
#include "lmi-gpu-boot-regs.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define DESK __attribute__((noinline,section(".gpu_desktop")))
#define AUX1 __attribute__((noinline,section(".gpu_batch_aux_one")))
#define AUX2 __attribute__((noinline,section(".gpu_batch_aux_two")))
#define DD __attribute__((section(".gpu_desktop_data")))
struct table_record {u64 phys;u64 *table;unsigned char changed;};
struct desktop_space {
    const char *name;u32 context,control,table_count;u64 *root;
    struct table_record tables[1024];u64 *last_entry,*last_table;u32 last_changed;
};
_Static_assert(sizeof(struct table_record)==24 && sizeof(struct desktop_space)==24632,"legacy table inventory ABI");
_Static_assert(__builtin_offsetof(struct desktop_space,root)==24 && __builtin_offsetof(struct desktop_space,tables)==32,"legacy table inventory offsets");
extern struct desktop_space desktop_space;
extern u64 desktop_slot[3],desktop_free[1024][2];
extern u32 desktop_free_count;
extern u64 g_phys_base,g_phys_size;
extern int legacy_space_map(struct desktop_space *,u64,u64,u64);
extern u64 pa_of(u64),io_map(u64,u64),absolute_time(void);
extern void *alloc_data(u64),*memset(void *,int,__SIZE_TYPE__);
extern int cache_sync(u64,u32,int),boot_arg(const char *,void *,int);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32),delay(u32,u32),log_line(const char *),log_hex(u64),desktop_service_start(void);
extern int lmi_gpu_cp_complete(volatile u32 *,volatile u32 *,volatile u32 *,u32);
extern int lmi_gpu_tile(u64,u32,volatile u32 *);
static const u32 canary DD=0x65065050;
struct desk_state {u64 pool;volatile u32 *gpu,*s,*g;u32 at,fence,done,failed,ready,mapping;u64 map_pages,map_batches;};
static struct desk_state *DESK state(void) {
    u64 p=desktop_slot[0];
    return p && desktop_slot[1]==0x4c4d494445534b31ull && desktop_slot[2]==~p?(void *)p:0;
}
u32 DESK lmi_gpu_desktop_canary(u32 v) {return v^*(volatile const u32 *)&canary;}
#ifdef LMI_GPU_POLL_HOST
extern u64 lmi_gpu_counter(void),lmi_gpu_counter_frequency(void);
#else
static u64 DESK lmi_gpu_counter(void) {
    u64 value;__asm__ volatile("isb\n\tmrs %0, cntvct_el0":"=r"(value)::"memory");return value;
}
static u64 DESK lmi_gpu_counter_frequency(void) {
    u64 value;__asm__ volatile("mrs %0, cntfrq_el0":"=r"(value));return value;
}
#endif
static int DESK quiet(struct desk_state *d) {
    /* Both callers reject failed state under the same service lock. */
    if(rsc_read(d->s+0x9058/4)!=0x400 || rsc_read(d->s+0x48/4) ||
       rsc_read(d->gpu+0x821) || rsc_read(d->gpu+0x823) ||
       rsc_read(d->g+BOOT_GMU_AHB_FENCE_STATUS/4))return -1;
    return rsc_read(d->gpu+0x806)==d->at && rsc_read(d->gpu+0x807)==d->at &&
        !(rsc_read(d->gpu+0x210)&~1u);
}
static int DESK idle(struct desk_state *d) {
    if(d->failed)return 0;
    for(u32 n=0;n<1000;n++) {
        int q=quiet(d);if(q<0)break;if(q)return 1;
        /* Short submissions must not yield the single CPU for a scheduler
         * quantum at every 100us poll. Spin only the first 2ms, with interrupts
         * enabled; long waits retain the original yielding/fault path. */
        if(n<20) {
            u64 began=lmi_gpu_counter();
            while(lmi_gpu_counter()-began<1920) {}
        } else delay(100,1000);
    }
    d->failed=1;log_line("LMI_GPU_DESKTOP_FAULT_HELD\n");
    lmi_gpu_cp_complete(d->gpu,d->s,d->g,d->at);return 0;
}
/* Called only after a real idle observation, while the service lock is held
 * (or after native SMP stop). Invalidate before reading device-owned scratch. */
static int DESK retire(struct desk_state *d) {
    volatile u32 *scratch=(void *)(d->pool+65536+64);
    if(!cache_sync((u64)scratch,64,0) || scratch[0]!=d->fence) {
        d->failed=1;return 0;
    }
    /* Fences start at one, advance by one and refuse wrap. */
    d->done=d->fence;
    return 1;
}
static int DESK drain(struct desk_state *d) {return idle(d) && retire(d);}
/* A void legacy ABI must not return to a caller that will release backing
 * after an uncertain table invalidation. The global native RAM-run timer
 * returns to the loader; until then, this thread keeps the caller's reference. */
static void DESK hold(struct desk_state *d) {
    d->failed=1;log_line("LMI_GPU_DESKTOP_RELEASE_HELD\n");
    for(;;)delay(100,1000);
}
static int DESK commit(void) {
    if(desktop_space.table_count>1024)return 0;
    for(u32 n=0;n<desktop_space.table_count;n++) {
        struct table_record *t=desktop_space.tables+n;
        if(t->changed) {if(!cache_sync((u64)t->table,4096,1))return 0;t->changed=0;}
    }
    return 1;
}
int AUX1 lmi_desktop_ready(void) {struct desk_state *d=state();return d && d->ready;}
int DESK lmi_desktop_parameter(u32 key,u64 *v) {
    if(!v)return 0;
    switch(key) {
    case 1:case 6:case 8:case 9:case 10:case 17:*v=0;break;
    case 2:*v=1152*1024;break;
    case 3:*v=0x06050002;break;
    case 4:*v=865000000;break;
    case 5:*v=absolute_time();break;
    case 7:case 19:*v=1;break;
    case 16:*v=16;break;
    case 18:*v=6;break;
    default:return 0;
    }
    return 1;
}
int DESK lmi_desktop_map(u64 address,u64 phys,int ro) {
    struct desk_state *d=state();
    if(!d || !d->ready || d->failed || (address|phys)&4095 || address<0x20000000 || address>=0x100000000ull ||
       !phys || phys>>36 || phys<g_phys_base || g_phys_size<4096 || phys-g_phys_base>g_phys_size-4096)return 0;
    /* newBuffer holds gGPULock across all map() calls and mapped(). No new
     * ring writer can appear between pages; commit checks health again. */
    if(!d->mapping) {if(!drain(d))hold(d);d->mapping=1;d->map_batches++;}
    d->map_pages++;
    return legacy_space_map(&desktop_space,address,phys,0xe40|(ro?128:0));
}
void DESK lmi_desktop_mapped(void) {
    struct desk_state *d=state();if(!d)return;
    if(!drain(d) || !commit())hold(d);
    d->mapping=0;
}
void DESK lmi_desktop_unmap(u64 address,u64 bytes) {
    struct desk_state *d=state();if(!d)return;
    if(d->mapping || !bytes || (address|bytes)&4095 || address<0x20000000 || address>=0x100000000ull ||
       bytes>0x100000000ull-address || !drain(d))hold(d);
    for(u64 n=0;n<bytes;n+=4096)if(!legacy_space_map(&desktop_space,address+n,0,0))hold(d);
    if(!commit())hold(d);
    rsc_write(d->s+0x9610/4,2);rsc_write(d->s+0x97f0/4,0);
    for(u32 n=0;n<1000;n++) {if(!(rsc_read(d->s+0x97f4/4)&1))return;delay(1,1000);}
    hold(d);
}
void DESK lmi_desktop_to_memory(void *p,u64 bytes) {
    struct desk_state *d=state();if(!d)return;
    if(d->mapping || bytes>0xffffffffu || (!p && bytes) || (u64)p+bytes<(u64)p ||
       !drain(d) || !cache_sync((u64)p,(u32)bytes,1) || !cache_sync((u64)p,(u32)bytes,0))hold(d);
}
static void AUX2 word(struct desk_state *d,u32 value) {
    ((volatile u32 *)d->pool)[d->at]=value;d->at=(d->at+1)&8191;
}
/* Fixed known type7 headers retain parity. All user command streams are IBs;
 * their addresses/sizes are checked by the existing service before this ABI. */
u32 DESK lmi_desktop_submit(const u64 *addresses,const u32 *words,u32 count) {
    struct desk_state *d=state();
    if(!d || !d->ready || d->mapping || !addresses || !words || !count || count>128 || !drain(d))return 0;
    for(u32 i=0;i<count;i++)if(addresses[i]<0x20000000 || addresses[i]>=0x100000000ull ||
        addresses[i]&3 || !words[i] || words[i]>(0x100000000ull-addresses[i])/4)return 0;
    /* drain() also checked the DMA-visible scratch against the last fence. */
    u32 fence=d->fence+1;if(!fence) {d->failed=1;return 0;}
    word(d,0x70460001);word(d,0x18);
    word(d,0x70460001);word(d,0x19);
    for(u32 i=0;i<count;i++) {word(d,0x70bf8003);word(d,(u32)addresses[i]);word(d,0);word(d,words[i]);}
    word(d,0x70268000);
    word(d,0x70460004);word(d,4);word(d,0x1010040);word(d,0);word(d,fence);
    if(!cache_sync(d->pool,32768,1)) {d->failed=1;return 0;}
    d->fence=fence;rsc_write(d->gpu+0x807,d->at);
    /* Return the queued fence. No completion is published here, even if the
     * GPU finished quickly. Existing BO/surface retention uses done(). */
    return fence;
}
int DESK lmi_desktop_done(u32 fence) {
    struct desk_state *d=state();if(!d)return 0;
    if(!fence || fence<=d->done)return 1;
    if(fence>d->fence || d->failed)return 0;
    int q=quiet(d);
    if(q<0) {d->failed=1;log_line("LMI_GPU_DESKTOP_FAULT_HELD\n");return 0;}
    return q && retire(d) && fence<=d->done;
}
u32 AUX1 lmi_desktop_last(void) {struct desk_state *d=state();return d?d->fence:0;}
void AUX2 lmi_desktop_worked(u64 *us,u32 *count,u32 by[7]) {
    /* No fabricated GPU time measurement; this backend has no timing packets. */
    *us=0;*count=0;for(u32 n=0;n<7;n++)by[n]=0;
}
void DESK lmi_desktop_report(const char *why) {
    struct desk_state *d=state();if(!d)return;
    log_line("LMI_GPU_DESKTOP_REPORT\n");log_line(why);log_line("\n");log_hex(d->fence);log_hex(d->done);log_hex(d->failed);
}
int DESK lmi_desktop_recover(void) {return 0;}
void DESK lmi_desktop_stop(void) {
    struct desk_state *d=state();if(d) {
        if(!drain(d))hold(d);
        /* Keep all parent allocations; only the verified return hook logs. */
        d->failed=1;
    }
}
/* Timer hook: preserve existing verified SMP/DPU cleanup first. No service
 * caller can still modify the ring when GPU drain begins. Never return to
 * the loader while GPU DMA completion is uncertain. */
extern void lmi_display_smp_prepare(void);
void DESK lmi_gpu_async_return(void) {
    lmi_display_smp_prepare();
    lmi_desktop_stop();
    struct desk_state *d=state();
    if(d) {log_line("LMI_GPU_MAP_BATCH\n");log_hex(d->map_batches);log_hex(d->map_pages);log_hex(d->mapping);}
    log_line("LMI_GPU_ASYNC_DRAINED\n");
}
/* Linux v6.12 a6xx_hw_init and a6xx_set_ubwc_config, A650 branch.
 * The all-ones UCHE bases disable L2 bypass; they are not DMA allocations. */
static const u32 nc[][2] DD={
    {0x8e08,0x816},{0xb604,6},{0xae02,0x26},{0xe01,0x600000},{0x534,1},
    {0xe05,0xffffffc0},{0xe06,0x1ffff},{0xe07,0xfffff000},{0xe08,0x1ffff},
    {0xe09,0xfffff000},{0xe0a,0x1ffff},{0xe18,0x804},{0xe17,4}};
int DESK lmi_gpu_desktop(u64 pool,u32 bytes,volatile u32 *g) {
    u32 fetched=lmi_gpu_desktop_canary(0x1badb002);
    log_line("LMI_GPU_DESKTOP_BEGIN\n");log_hex(fetched);
    if(fetched!=0x7eabe052 || lmi_gpu_counter_frequency()!=19200000 || !pool || pool&4095 || bytes!=81920 || !g ||
       desktop_slot[0] || desktop_slot[1] || desktop_slot[2] || desktop_free_count ||
       desktop_space.context || desktop_space.control!=256 || desktop_space.table_count || desktop_space.root ||
       desktop_space.last_entry || desktop_space.last_table || desktop_space.last_changed)return 0;
    for(u32 n=0;n<1024;n++)if(desktop_space.tables[n].phys || desktop_space.tables[n].table || desktop_space.tables[n].changed)return 0;
    volatile u32 *gpu=(void *)io_map(0x3d00000,0x40000),*s=(void *)io_map(0x3da0000,0x10000);
    if(!gpu || !s || rsc_read(gpu+0x806)!=68 || rsc_read(gpu+0x807)!=68 || rsc_read(gpu+0x808)!=1 ||
       !lmi_gpu_cp_complete(gpu,s,g,68))return 0;
    u64 root=pa_of(pool+17*4096),l2=pa_of(pool+18*4096),l3=pa_of(pool+19*4096);
    if(!root || !l2 || !l3 || (root|l2|l3)&4095 || (root|l2|l3)>>36 ||
       rsc_read(s+0x9020/4)!=(u32)root || rsc_read(s+0x9024/4)!=((root>>32)|0x20000) ||
       rsc_read(s+0x9000/4)!=0xc000e7 || rsc_read(s+0x9010/4)!=0x38071 || rsc_read(s+0x9030/4)!=0x803519)return 0;
    for(u32 n=0;n<512;n++)if(((u64 *)(pool+17*4096))[n]!=(n==0?(l2|3):0) ||
       ((u64 *)(pool+18*4096))[n]!=(n==8?(l3|3):0) ||
       ((u64 *)(pool+19*4096))[n]!=(n<17?(pa_of(pool+4096*n)|(n>=8 && n<16?0xec3:0xe43)):0))return 0;
    if(!cache_sync(pool+65536+64,64,0))return 0;
    for(u32 n=16;n<32;n++)if(((volatile u32 *)(pool+65536))[n])return 0;
    for(u32 n=68;n<72;n++)if(((volatile u32 *)pool)[n])return 0;
    struct desk_state *d=alloc_data(sizeof(*d));if(!d)return 0;
    memset(d,0,sizeof(*d));d->pool=pool;d->gpu=gpu;d->s=s;d->g=g;d->at=68;
    desktop_slot[0]=(u64)d;desktop_slot[1]=0x4c4d494445534b31ull;desktop_slot[2]=~(u64)d;
    desktop_space.context=1;desktop_space.root=(void *)(pool+17*4096);desktop_space.table_count=3;
    const u64 phys[]={root,l2,l3};
    for(u32 n=0;n<3;n++) {desktop_space.tables[n].phys=phys[n];desktop_space.tables[n].table=(void *)(pool+(17+n)*4096);}
    log_line("LMI_GPU_DESKTOP_TABLES\n");for(u32 n=0;n<3;n++)log_hex(phys[n]);
    log_line("LMI_GPU_DESKTOP_NC\n");
    for(u32 n=0;n<sizeof(nc)/sizeof(nc[0]);n++) {
        rsc_write(gpu+nc[n][0],nc[n][1]);u32 v=rsc_read(gpu+nc[n][0]);
        log_hex(((u64)(0x3d00000+4*nc[n][0])<<32)|v);if(v!=nc[n][1]) {d->failed=1;return 0;}
    }
    const u32 packet[]={0x703d8003,0x1010044,0,0x650c0de4};
    for(u32 n=0;n<4;n++)word(d,packet[n]);
    if(!cache_sync(pool,384,1)) {d->failed=1;return 0;}
    rsc_write(gpu+0x807,72);
    if(!idle(d) || !cache_sync(pool+65536+64,64,0)) {d->failed=1;return 0;}
    u32 fence=((volatile u32 *)(pool+65536))[17];
    log_line("LMI_GPU_DESKTOP_BIND_FENCE\n");log_hex(72);log_hex(fence);
    if(fence!=0x650c0de4 || ((volatile u32 *)(pool+65536))[16]) {d->failed=1;return 0;}
    desktop_free[0][0]=0x20000000;desktop_free[0][1]=0xe0000000;desktop_free_count=1;
    d->ready=1;log_line("LMI_GPU_DESKTOP_READY\n");log_hex(0x06050002);log_hex(1152*1024);log_hex(16);log_hex(1);log_hex(2);
    desktop_service_start();return 1;
}
/* Replaces the tile-only wrapper only in a compiled desktop profile. */
int DESK lmi_gpu_tile_opt(u64 pool,u32 bytes,volatile u32 *g) {
    u32 tile=0,desktop=0;
    int good=boot_arg("lmi_gpu_tile",&tile,4) && tile==1 && lmi_gpu_tile(pool,bytes,g);
    log_line("LMI_GPU_TILE_RESULT\n");log_hex(good);
    if(good) {
        good=boot_arg("lmi_gpu_desktop",&desktop,4) && desktop==1 && lmi_gpu_desktop(pool,bytes,g);
        log_line("LMI_GPU_DESKTOP_RESULT\n");log_hex(good);
    }
    return good;
}
