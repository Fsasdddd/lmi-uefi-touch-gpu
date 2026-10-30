#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "lmi-render-wait-v75.h"
struct lmi_fast_stats *lmi_fast_state;
static struct lmi_render_stats storage;
static uint64_t now,duration;
static unsigned stopped,emitted,fail_alloc,delays,expected_interval,expected_scale;
static size_t requested;
void *IOMallocAligned(size_t n,size_t a) {assert(a==16);requested=n;return fail_alloc?0:&storage;}
void bzero(void *p,size_t n) {memset(p,0,n);}
uint64_t lmi_frame_ticks(void) {return __atomic_load_n(&now,__ATOMIC_RELAXED);}
void lmi_render_original_delay(unsigned i,unsigned s)
{assert(i==expected_interval && s==expected_scale);__atomic_fetch_add(&delays,1,__ATOMIC_RELAXED);__atomic_fetch_add(&now,duration,__ATOMIC_RELAXED);}
void lmi_timing_cleanup(void) {stopped=1;}
void lmi_frame_emit(const char *tag,const uint64_t *p,unsigned n)
{
    assert(stopped);
    if(emitted++==0)assert(!strcmp(tag,"LMI_RENDER_DELAY") && p==&storage.delay.count && n==9);
    else assert(!strcmp(tag,"LMI_RENDER_DELAY_OTHER") && p==&storage.other && n==1);
}
static void reset(void)
{memset(&storage,0,sizeof(storage));now=1000000;duration=960;expected_interval=50;expected_scale=1000;
    stopped=emitted=fail_alloc=delays=0;requested=0;lmi_fast_state=(void *)&storage;}
static void *worker(void *p)
{for(unsigned i=0;i<(uintptr_t)p;i++)lmi_render_delay(50,1000);return 0;}
int main(void)
{
    unsigned cases=0;
    reset();memset(&storage,0xa5,sizeof(storage));assert(lmi_render_allocate(sizeof(struct lmi_fast_stats),16)==&storage);
    assert(requested==sizeof(storage));for(size_t i=0;i<sizeof(storage);i++)assert(!((unsigned char *)&storage)[i]);cases++;
    reset();assert(!lmi_render_allocate(0,16) && !lmi_render_allocate(sizeof(struct lmi_fast_stats),8));cases++;
    reset();fail_alloc=1;assert(!lmi_render_allocate(sizeof(struct lmi_fast_stats),16));cases++;
    reset();storage.original.frame_ok=42;struct lmi_timing_stats prefix=storage.original;
    lmi_render_delay(50,1000);assert(delays==1 && storage.delay.count==1 && storage.delay.sum==960 && storage.delay.max==960 && storage.delay.bin[0]==1 && !storage.other);
    assert(!memcmp(&prefix,&storage.original,sizeof(prefix)));cases++;
    reset();lmi_fast_state=0;lmi_render_delay(50,1000);assert(delays==1 && !storage.delay.count);cases++;
    reset();expected_interval=200;lmi_render_delay(200,1000);assert(delays==1 && storage.other==1);cases++;
    reset();expected_scale=0;lmi_render_delay(50,0);assert(delays==1 && storage.other==1);cases++;
    const uint64_t edge[5]={19200,76800,160000,320000,640000};
    for(unsigned i=0;i<5;i++) {
        reset();duration=edge[i];lmi_render_delay(50,1000);assert(storage.delay.bin[i]==1);
        duration++;lmi_render_delay(50,1000);assert(storage.delay.bin[i+1]==1 && storage.delay.max==duration);cases++;
    }
    reset();now=UINT64_MAX-479;lmi_render_delay(50,1000);assert(storage.delay.sum==960 && storage.delay.max==960);cases++;
    reset();pthread_t t[4];for(unsigned i=0;i<4;i++)assert(!pthread_create(t+i,0,worker,(void *)1000));
    for(unsigned i=0;i<4;i++)assert(!pthread_join(t[i],0));
    assert(delays==4000 && storage.delay.count==4000 && storage.delay.sum>=4000*960 && storage.delay.max>=960);
    uint64_t sum=0;for(unsigned i=0;i<6;i++)sum+=storage.delay.bin[i];assert(sum==4000 && !storage.other);cases++;
    reset();lmi_render_cleanup();assert(stopped && emitted==2);cases++;
    reset();lmi_fast_state=0;lmi_render_cleanup();assert(stopped && !emitted);cases++;
    printf("PASS: %u scenarios, including 4 concurrent writers\n",cases);return 0;
}
