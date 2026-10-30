#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "lmi-display-wait-v74.h"
struct lmi_fast_stats *lmi_fast_state;
static struct lmi_wait_stats storage;
static uint64_t now=1000000,step=96,sleep_ticks=192000;
static unsigned delays,last_us,stopped,emitted,fail_alloc;
static size_t requested,alignment;
void *IOMallocAligned(size_t bytes,size_t align)
{requested=bytes;alignment=align;return fail_alloc?NULL:&storage;}
void bzero(void *p,size_t bytes) {memset(p,0,bytes);}
uint64_t lmi_frame_ticks(void) {uint64_t value=now;now+=step;return value;}
void lmi_wait_original_delay(unsigned us)
{delays++;last_us=us;now+=sleep_ticks;}
void lmi_timing_cleanup(void) {stopped=1;}
void lmi_frame_emit(const char *tag,const uint64_t *p,unsigned n)
{assert(stopped && !strcmp(tag,"LMI_DPU_SHORT_WAIT") && p==&storage.calls && n==7);emitted++;}
static void reset(void)
{
    memset(&storage,0,sizeof(storage));now=1000000;step=96;sleep_ticks=192000;
    delays=stopped=emitted=last_us=fail_alloc=0;lmi_fast_state=(void *)&storage;
    storage.original.owner=(void *)0x1000;storage.original.armed=1;storage.original.ended=now;
}
int main(void)
{
    unsigned cases=0;
    reset();memset(&storage,0xa5,sizeof(storage));
    assert(lmi_wait_allocate(sizeof(struct lmi_fast_stats),16)==&storage);
    assert(requested==sizeof(storage) && alignment==16);
    for(size_t i=0;i<sizeof(storage);i++)assert(!((unsigned char *)&storage)[i]);cases++;
    reset();assert(!lmi_wait_allocate(sizeof(struct lmi_fast_stats)-1,16));
    assert(!lmi_wait_allocate(sizeof(struct lmi_fast_stats),8));cases++;
    reset();fail_alloc=1;assert(!lmi_wait_allocate(sizeof(struct lmi_fast_stats),16));cases++;
    reset();struct lmi_timing_stats prefix=storage.original;lmi_wait_delay(50);
    assert(storage.calls==1 && storage.spun==1 && !storage.yielded && !delays && storage.spin_ticks>=960);
    assert(!memcmp(&prefix,&storage.original,sizeof(prefix)));cases++;
    reset();storage.original.ended=now-(LMI_WAIT_BUDGET_TICKS-LMI_WAIT_STEP_TICKS);
    lmi_wait_delay(50);assert(storage.spun==1 && !delays);cases++;
    reset();storage.original.ended=now-(LMI_WAIT_BUDGET_TICKS-LMI_WAIT_STEP_TICKS+1);
    lmi_wait_delay(50);assert(!storage.spun && storage.yielded==1 && delays==1 && last_us==50);
    assert(storage.yield_ticks==sleep_ticks+step && storage.yield_max==storage.yield_ticks && !storage.other);cases++;
    reset();storage.original.ended=now+1;lmi_wait_delay(50);assert(delays==1 && !storage.spun);cases++;
    reset();storage.original.armed=0;lmi_wait_delay(50);assert(delays==1 && storage.other==1);cases++;
    reset();storage.original.owner=NULL;lmi_wait_delay(50);assert(delays==1 && storage.other==1);cases++;
    reset();lmi_wait_delay(0);lmi_wait_delay(1234);assert(delays==2 && last_us==1234 && storage.other==2);cases++;
    reset();lmi_fast_state=NULL;lmi_wait_delay(50);assert(delays==1 && !storage.calls);cases++;
    reset();for(unsigned i=0;i<200;i++)lmi_wait_delay(50);
    assert(storage.spun>100 && storage.spun<170 && storage.yielded>0 && storage.calls==200);
    assert(storage.calls==storage.spun+storage.yielded && delays==storage.yielded);cases++;
    reset();step=300000;lmi_wait_delay(50);assert(storage.spun==1 && !delays);
    lmi_wait_delay(50);assert(storage.yielded==1 && delays==1);cases++;
    reset();storage.original.ended=UINT64_MAX-959;now=0;lmi_wait_delay(50);
    assert(storage.spun==1 && !delays);cases++;
    reset();lmi_wait_cleanup();assert(stopped && emitted==1);cases++;
    reset();lmi_fast_state=NULL;lmi_wait_cleanup();assert(stopped && !emitted);cases++;
    printf("PASS: %u scenarios\n",cases);return 0;
}
