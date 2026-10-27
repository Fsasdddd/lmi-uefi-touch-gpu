#define _POSIX_C_SOURCE 200809L
#include "lmi-display-fast-v62.h"
#include "lmi-display-fence-abi-v62.h"
#include <assert.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

struct lmi_fast_stats *lmi_fast_state;
struct lock { pthread_mutex_t mutex; pthread_cond_t condition,progress; };
struct fixture {
    _Alignas(16) unsigned char owner[3136],client[480],args[96],swap[0x46c];
    struct lock queue,client_lock;
    uint64_t input[3],now,deadlines[16];
    unsigned sleeps,wakes,shows,clears,allocs,fail_alloc,closed,stage;
    unsigned unknown_calls,unknown_selector;
    void *unknown[5];
    void (*sleep_action)(struct fixture *);
    void (*show_action)(struct fixture *);
    void (*clear_action)(struct fixture *);
    int interrupted,threaded,destructive_close;
};
static struct fixture *active;
static jmp_buf held;
static unsigned held_logs;
static void set32(void *p,unsigned at,uint32_t n) {memcpy((char *)p+at,&n,4);}
static void setptr(void *p,unsigned at,void *v) {memcpy((char *)p+at,&v,sizeof(v));}
void *IOMallocAligned(size_t n,size_t align)
{
    assert(active);active->allocs++;
    if(active->fail_alloc)return NULL;
    void *p=NULL;assert(!posix_memalign(&p,align,n));return p;
}
void bzero(void *p,size_t n) {memset(p,0,n);}
void IOLockLock(void *p) {assert(!pthread_mutex_lock(&((struct lock *)p)->mutex));}
void IOLockUnlock(void *p) {assert(!pthread_mutex_unlock(&((struct lock *)p)->mutex));}
void IOLockWakeup(void *p,void *event,int one)
{
    assert(event && !one);active->wakes++;
    assert(!pthread_cond_broadcast(&((struct lock *)p)->condition));
}
uint64_t mach_absolute_time(void) {return active->now;}
void clock_interval_to_deadline(uint32_t n,uint32_t scale,uint64_t *out)
{assert(scale==1000000);*out=active->now+(uint64_t)n*scale;}
int IOLockSleepDeadline(void *p,void *event,uint64_t deadline,int mode)
{
    struct fixture *f=active;assert(event && mode==LMI_THREAD_ABORTSAFE);
    assert(f->sleeps<16);f->deadlines[f->sleeps++]=deadline;
    if(f->threaded) {
        assert(!pthread_cond_broadcast(&((struct lock *)p)->progress));
        assert(!pthread_cond_wait(&((struct lock *)p)->condition,&((struct lock *)p)->mutex));
    } else {
        IOLockUnlock(p);
        if(f->sleep_action)f->sleep_action(f);else f->now=deadline;
        IOLockLock(p);
    }
    return f->interrupted?LMI_THREAD_INTERRUPTED:(f->now>=deadline?LMI_THREAD_TIMED_OUT:0);
}
void loader_log_line(const char *s) {assert(!strcmp(s,"LMI_SWAP_FENCE_HELD\n"));held_logs++;}
void IOSleep(unsigned n) {assert(n==1000);longjmp(held,1);}
static void queue(struct fixture *f,uint32_t first,uint32_t count,uint32_t a,uint32_t b)
{
    IOLockLock(&f->queue);
    set32(f->owner,LMI_FB_fSwapFirst,first);set32(f->owner,LMI_FB_fSwapsWaiting,count);
    set32(f->owner,LMI_FB_fSwap+0x50,a);set32(f->owner,LMI_FB_fSwap+0x46c+0x50,b);
    IOLockUnlock(&f->queue);
}
static uint32_t waitfor(struct fixture *f,uint32_t id,uint64_t flags,uint64_t timeout)
{
    f->input[0]=id;f->input[1]=flags;f->input[2]=timeout;
    return lmi_fence_method(f->client,6,f->args,0,0,0);
}
void lmi_fence_original_show(void *owner,const unsigned char *swap,void **surfaces)
{
    struct fixture *f=active;assert(owner==f->owner && swap==f->swap && surfaces==NULL);
    assert(lmi_fast_state && lmi_fast_state->fence.reading);
    f->shows++;
    if(f->show_action)f->show_action(f);
    queue(f,1,0,0,0); /* Native dequeue; the source remains in use. */
}
void lmi_fence_original_clear(void)
{
    struct fixture *f=active;assert(f->stage==4);f->clears++;
    if(f->clear_action)f->clear_action(f);
}
uint32_t lmi_fence_original_method(void *client,uint32_t selector,void *args,void *dispatch,void *target,void *reference)
{
    struct fixture *f=active;f->unknown_calls++;f->unknown_selector=selector;
    f->unknown[0]=client;f->unknown[1]=args;f->unknown[2]=dispatch;f->unknown[3]=target;f->unknown[4]=reference;
    return 0x12345678;
}
uint32_t lmi_fence_original_close(void *client)
{
    struct fixture *f=active;assert(client==f->client && f->client[LMI_UC_fClosed]);
    assert(f->wakes);f->closed++;
    /* Simulate terminate invalidating every client field before it returns. */
    if(f->destructive_close)memset(client,0xa5,sizeof(f->client));return 0x87654321;
}
static void init(struct fixture *f)
{
    memset(f,0,sizeof(*f));active=f;held_logs=0;
    pthread_mutexattr_t attr;assert(!pthread_mutexattr_init(&attr));
    assert(!pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_ERRORCHECK));
    assert(!pthread_mutex_init(&f->queue.mutex,&attr));assert(!pthread_cond_init(&f->queue.condition,0));
    assert(!pthread_cond_init(&f->queue.progress,0));
    assert(!pthread_mutex_init(&f->client_lock.mutex,&attr));assert(!pthread_cond_init(&f->client_lock.condition,0));
    assert(!pthread_cond_init(&f->client_lock.progress,0));
    assert(!pthread_mutexattr_destroy(&attr));
    setptr(f->owner,LMI_FB_fSwapLock,&f->queue);
    setptr(f->client,LMI_UC_fOwner,f->owner);setptr(f->client,LMI_UC_fLock,&f->client_lock);
    setptr(f->args,LMI_ARG_scalarInput,f->input);set32(f->args,LMI_ARG_scalarInputCount,3);
    set32(f->swap,0x50,42);f->now=100;
}
static void destroy(struct fixture *f)
{
    assert(!pthread_mutex_destroy(&f->queue.mutex));assert(!pthread_cond_destroy(&f->queue.condition));
    assert(!pthread_cond_destroy(&f->queue.progress));
    assert(!pthread_mutex_destroy(&f->client_lock.mutex));assert(!pthread_cond_destroy(&f->client_lock.condition));
    assert(!pthread_cond_destroy(&f->client_lock.progress));
    free(lmi_fast_state);lmi_fast_state=NULL;active=NULL;
}
static void poll_reading(struct fixture *f)
{
    assert(waitfor(f,42,0x80000000u,5)==LMI_kIOReturnBusy);
    assert(waitfor(f,42,0x80000001u,5)==LMI_kIOReturnBusy);
    assert(waitfor(f,99,0x80000000u,5)==LMI_kIOReturnSuccess);
}
static void retire(struct fixture *f) {f->stage=4;lmi_fence_finish(f->owner);}
static void advance(struct fixture *f) {f->now+=2000000;}
static void complete_at_deadline(struct fixture *f) {f->now=f->deadlines[f->sleeps-1];retire(f);}
static void close_at_deadline(struct fixture *f) {f->now=f->deadlines[f->sleeps-1];assert(lmi_fence_close(f->client)==0x87654321);}
/* Unlike the destruction probe, a live IOKit externalMethod retains its client.
 * Keep its storage valid while exercising the real pthread close/wake order. */
static void mark_closed_live(struct fixture *f)
{
    IOLockLock(&f->client_lock);f->client[LMI_UC_fClosed]=1;IOLockUnlock(&f->client_lock);
    IOLockLock(&f->queue);IOLockWakeup(&f->queue,&lmi_fast_state->fence.generation,0);IOLockUnlock(&f->queue);
}
struct waiter {struct fixture *f;uint32_t result;};
static void *wait_thread(void *p)
{
    struct waiter *w=p;unsigned char args[96]={0};uint64_t in[]={42,0,5000};
    setptr(args,LMI_ARG_scalarInput,in);set32(args,LMI_ARG_scalarInputCount,3);
    w->result=lmi_fence_method(w->f->client,6,args,0,0,0);return NULL;
}
static void wait_until_sleepers(struct fixture *f,unsigned n)
{
    struct timespec timeout;assert(!clock_gettime(CLOCK_REALTIME,&timeout));timeout.tv_sec+=3;
    IOLockLock(&f->queue);
    while(f->sleeps<n)assert(!pthread_cond_timedwait(&f->queue.progress,&f->queue.mutex,&timeout));
    IOLockUnlock(&f->queue);
}
int main(void)
{
    static struct fixture f;unsigned cases=0;
    /* The native queue protects the swap before show; reading protects it
     * through dequeue, four source drops, and original kept cleanup. */
    init(&f);queue(&f,0,1,42,0);poll_reading(&f);
    f.show_action=poll_reading;lmi_fence_show(f.owner,f.swap,NULL);poll_reading(&f);
    assert(lmi_fast_state->fence.began==1 && !lmi_fast_state->fence.retired);
    f.stage=4;f.clear_action=poll_reading;lmi_fence_finish(f.owner);
    assert(f.clears==1 && lmi_fast_state->fence.retired==1 && !lmi_fast_state->fence.reading);
    assert(waitfor(&f,42,0,1)==LMI_kIOReturnSuccess);assert(f.allocs==1);destroy(&f);cases++;
    for(unsigned mode=0;mode<3;mode++) {
        init(&f);queue(&f,1,2,0,UINT32_MAX);
        assert(waitfor(&f,UINT32_MAX,0x80000000u|mode,5)==LMI_kIOReturnBusy);
        if(mode!=2)assert(waitfor(&f,123,0x80000000u|mode,5)==LMI_kIOReturnSuccess);
        assert(waitfor(&f,0,0x80000000u|mode,5)==LMI_kIOReturnBusy);
        queue(&f,0,0,0,0);assert(waitfor(&f,0,mode,5)==LMI_kIOReturnSuccess);destroy(&f);cases++;
    }
    for(unsigned id=0;id<2;id++) {
        init(&f);set32(f.swap,0x50,id?UINT32_MAX:0);queue(&f,0,1,id?UINT32_MAX:0,0);
        lmi_fence_show(f.owner,f.swap,NULL);
        assert(waitfor(&f,id?UINT32_MAX:0,0x80000000u,5)==LMI_kIOReturnBusy);
        assert(waitfor(&f,id?0:UINT32_MAX,0x80000000u,5)==LMI_kIOReturnSuccess);
        retire(&f);destroy(&f);cases++;
    }
    init(&f);queue(&f,0,1,42,0);f.sleep_action=advance;
    assert(waitfor(&f,42,0,5)==LMI_kIOReturnTimeout && f.sleeps==3);
    assert(f.deadlines[0]==5000100 && f.deadlines[1]==f.deadlines[0] && f.deadlines[2]==f.deadlines[0]);destroy(&f);cases++;
    init(&f);queue(&f,0,1,42,0);assert(waitfor(&f,42,0,0)==LMI_kIOReturnTimeout);
    assert(f.deadlines[0]==700000100);destroy(&f);cases++;
    init(&f);queue(&f,0,1,42,0);lmi_fence_show(f.owner,f.swap,NULL);f.sleep_action=complete_at_deadline;
    assert(waitfor(&f,42,0,5)==LMI_kIOReturnSuccess && !lmi_fast_state->fence.timeouts);destroy(&f);cases++;
    /* Model close independently of invalidation: sleeping methods have their
     * own client reference. The next test probes no post-terminate accesses. */
    init(&f);queue(&f,0,1,42,0);f.sleep_action=close_at_deadline;
    assert(waitfor(&f,42,0,5)==LMI_kIOReturnNotOpen && !lmi_fast_state->fence.timeouts);destroy(&f);cases++;
    init(&f);f.destructive_close=1;assert(lmi_fence_close(f.client)==0x87654321 && f.closed==1 && f.client[0]==0xa5);destroy(&f);cases++;
    init(&f);queue(&f,0,1,42,0);f.interrupted=1;
    assert(waitfor(&f,42,0,5)==LMI_kIOReturnAborted);destroy(&f);cases++;
    init(&f);queue(&f,0,1,42,0);
    assert(waitfor(&f,42,3,5)==LMI_kIOReturnSuccess);
    assert(waitfor(&f,42,4,5)==LMI_kIOReturnBadArgument);
    assert(waitfor(&f,42,5,5)==LMI_kIOReturnBadArgument);
    assert(waitfor(&f,42,1ull<<32,5)==LMI_kIOReturnBadArgument);
    assert(waitfor(&f,42,0,1ull<<32)==LMI_kIOReturnBadArgument);destroy(&f);cases++;
    for(unsigned n=0;n<4;n++) {
        init(&f);
        if(n==0)set32(f.args,LMI_ARG_scalarInputCount,2);
        if(n==1)setptr(f.args,LMI_ARG_scalarInput,NULL);
        if(n==2)setptr(f.client,LMI_UC_fOwner,NULL);
        if(n==3)setptr(f.owner,LMI_FB_fSwapLock,NULL);
        assert(waitfor(&f,42,0,5)==(n<2?LMI_kIOReturnBadArgument:LMI_kIOReturnNotOpen));destroy(&f);cases++;
    }
    init(&f);assert(lmi_fence_method(f.client,6,NULL,0,0,0)==LMI_kIOReturnBadArgument);destroy(&f);cases++;
    init(&f);f.fail_alloc=1;assert(waitfor(&f,42,0,5)==LMI_kIOReturnNoMemory);destroy(&f);cases++;
    for(unsigned n=0;n<2;n++) {
        init(&f);queue(&f,n?0:2,n?3:0,42,0);
        assert(waitfor(&f,42,0,5)==LMI_kIOReturnBusy && lmi_fast_state->fence.held==1);destroy(&f);cases++;
    }
    init(&f);assert(lmi_fence_method(f.client,17,f.args,(void *)1,(void *)2,(void *)3)==0x12345678);
    assert(f.unknown_calls==1 && f.unknown_selector==17 && f.unknown[0]==f.client && f.unknown[1]==f.args &&
        f.unknown[2]==(void *)1 && f.unknown[3]==(void *)2 && f.unknown[4]==(void *)3);destroy(&f);cases++;
    for(unsigned close=0;close<2;close++) {
        init(&f);queue(&f,0,1,42,0);lmi_fence_show(f.owner,f.swap,NULL);f.threaded=1;
        pthread_t threads[4];struct waiter ws[4];
        for(unsigned n=0;n<4;n++) {ws[n]=(struct waiter){&f,0xffffffff};assert(!pthread_create(&threads[n],0,wait_thread,&ws[n]));}
        wait_until_sleepers(&f,4);
        if(close)mark_closed_live(&f);else retire(&f);
        for(unsigned n=0;n<4;n++) {assert(!pthread_join(threads[n],0));assert(ws[n].result==(close?LMI_kIOReturnNotOpen:LMI_kIOReturnSuccess));}
        assert(lmi_fast_state->fence.waits==4);destroy(&f);cases++;
    }
    init(&f);queue(&f,0,1,42,0);lmi_fence_show(f.owner,f.swap,NULL);
    if(!setjmp(held)) {lmi_fence_show(f.owner,f.swap,NULL);assert(0);}
    assert(held_logs==1 && f.shows==1 && lmi_fast_state->fence.held==1 && lmi_fast_state->fence.reading);destroy(&f);cases++;
    init(&f);f.stage=4;
    if(!setjmp(held)) {lmi_fence_finish(f.owner);assert(0);}
    assert(held_logs==1 && f.clears==1 && lmi_fast_state->fence.held==1);destroy(&f);cases++;
    printf("PASS: %u producer retirement integration cases (including real pthread waiters)\n",cases);
    return 0;
}
