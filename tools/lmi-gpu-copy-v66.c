/* One boot-only, mandatory probe before publishing the GPU service. Uses
 * fresh bytes of the already owned/mapped scratch page, no source surface,
 * new mapping, CP context change or desktop replacement. No CPU target writes.
 * The old backend owns every allocation through the existing RAM-run return.
 */
#include "lmi-gpu-copy-v66.h"
extern struct lmi_v66_desk *lmi_v66_state(void);
extern int lmi_v66_drain(struct lmi_v66_desk *);
extern _Noreturn void lmi_v66_hold(struct lmi_v66_desk *);
extern int cache_sync(uint64_t,uint32_t,int);
extern void rsc_write(volatile uint32_t *,uint32_t);
extern uint64_t lmi_v66_counter(void);
extern void lmi_v66_emit(const char *,const uint64_t *,unsigned);
extern void desktop_service_start(void);
/* Mesa24.3 CP_MEMCPY DWORDS/SRC_LO/SRC_HI/DST_LO/DST_HI. A non-power-of-two
 * length crosses cache lines and leaves the final dword as an overwrite guard.
 * WAIT_MEM_WRITES + idle precede a new CACHE_FLUSH_TS, then a separate
 * MEM_WRITE marker. Desktop's real TS scratch at +0x40 is never touched. */
static const uint32_t commands[]={
    0x70758005,255,0x1010800,0,0x1010c00,0,
    0x70928000,0x70268000,
    0x70460004,4,0x1010600,0,0x660c0de6,
    0x70268000,0x703d8003,0x1010604,0,0x660c0de7
};
static __attribute__((noinline)) uint32_t copied(volatile uint32_t *scratch)
{
    uint32_t bad=0;
    for(unsigned i=0;i<256;i++) {
        uint32_t expected=i<255?(i^0xa5a55a5a):0;
        bad+=scratch[512+i]!=expected;bad+=scratch[768+i]!=expected;
    }
    for(unsigned i=386;i<512;i++)bad+=scratch[i]!=0;
    return bad;
}
int lmi_gpu_copy_start(void)
{
    struct lmi_v66_desk *d=lmi_v66_state();
    if(!d || !d->ready || d->failed || d->mapping || d->at!=72 || d->fence ||
       !lmi_v66_drain(d))return 0;
    volatile uint32_t *scratch=(void *)(uintptr_t)(d->pool+65536);
    if(!cache_sync((uintptr_t)scratch,4096,0))return 0;
    for(unsigned i=384;i<1024;i++)if(scratch[i])return 0;
    for(unsigned i=0;i<255;i++)scratch[512+i]=i^0xa5a55a5a;
    if(!cache_sync((uintptr_t)(scratch+512),1024,1))return 0;
    volatile uint32_t *ring=(void *)(uintptr_t)d->pool;
    for(unsigned i=0;i<18;i++)ring[72+i]=commands[i];
    if(!cache_sync(d->pool,512,1))return 0;
    uint64_t began=lmi_v66_counter();d->at=90;rsc_write(d->gpu+0x807,90);
    if(!lmi_v66_drain(d))lmi_v66_hold(d); /* Never release an uncertain DMA dependency. */
    if(!cache_sync((uintptr_t)scratch,4096,0))return 0;
    uint64_t elapsed=lmi_v66_counter()-began,bad=copied(scratch);
    uint64_t values[]={1020,90,scratch[384],scratch[385],bad,elapsed};
    lmi_v66_emit("LMI_CP_COPY",values,6);
    if(bad || scratch[384]!=0x660c0de6 || scratch[385]!=0x660c0de7)return 0;
    desktop_service_start();return 1;
}
