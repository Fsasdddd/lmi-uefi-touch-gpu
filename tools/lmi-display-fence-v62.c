#include "lmi-display-fast-v62.h"
#include "lmi-display-fence-abi-v62.h"
extern void *IOMallocAligned(size_t,size_t);
extern void bzero(void *,size_t);
extern void IOLockLock(void *),IOLockUnlock(void *),IOLockWakeup(void *,void *,int);
extern int IOLockSleepDeadline(void *,void *,uint64_t,int);
extern uint64_t mach_absolute_time(void);
extern void clock_interval_to_deadline(uint32_t,uint32_t,uint64_t *);
extern void lmi_fence_original_show(void *,const unsigned char *,void **);
extern void lmi_fence_original_clear(void);
extern uint32_t lmi_fence_original_method(void *,uint32_t,void *,void *,void *,void *);
extern uint32_t lmi_fence_original_close(void *);
extern void loader_log_line(const char *);
extern void IOSleep(unsigned);
static uintptr_t pointer(const void *p,unsigned at)
{return *(const uintptr_t *)((const unsigned char *)p+at);}
static uint32_t word(const void *p,unsigned at)
{return *(const uint32_t *)((const unsigned char *)p+at);}
/* Called only with the framebuffer queue lock held. No other caller creates
 * fast statistics: the real presenter enters this wrapper before composition. */
static struct lmi_swap_fence *journal(void *owner)
{
    struct lmi_fast_stats *s=__atomic_load_n(&lmi_fast_state,__ATOMIC_ACQUIRE);
    if(!s) {
        s=IOMallocAligned(sizeof(*s),16);
        if(!s)return 0;
        bzero(s,sizeof(*s));s->fence.owner=owner;
        __atomic_store_n(&lmi_fast_state,s,__ATOMIC_RELEASE);
    }
    return s->fence.owner==owner?&s->fence:0;
}
static void *queue_lock(void *owner)
{return (void *)pointer(owner,LMI_FB_fSwapLock);}
static void wake(struct lmi_swap_fence *f)
{
    f->generation++;f->wakes++;
    IOLockWakeup(queue_lock(f->owner),&f->generation,0);
}
static void hold(void)
{
    loader_log_line("LMI_SWAP_FENCE_HELD\n");
    for(;;)IOSleep(1000); /* Native global stop/return retains uncertain state. */
}
void lmi_fence_show(void *owner,const unsigned char *swap,void **surfaces)
{
    void *lock=queue_lock(owner);IOLockLock(lock);
    struct lmi_swap_fence *f=journal(owner);
    if(!f || f->reading) {
        if(f)f->held++;
        IOLockUnlock(lock);hold();return;
    }
    f->reading=1;f->id=word(swap,0x50);f->began++;
    IOLockUnlock(lock);
    /* The queue still contains this swap until native show dequeues it.
     * Reading is published first, so SwapWait cannot observe a retirement gap. */
    lmi_fence_original_show(owner,swap,surfaces);
}
void lmi_fence_finish(void *owner)
{
    /* The native presenter has dropped all source holds before this call.
     * Keep retirement pending through its original kept-memory cleanup too. */
    lmi_fence_original_clear();
    void *lock=queue_lock(owner);IOLockLock(lock);
    struct lmi_swap_fence *f=journal(owner);
    if(!f || !f->reading) {
        if(f)f->held++;
        IOLockUnlock(lock);hold();return;
    }
    f->reading=0;f->retired++;wake(f);IOLockUnlock(lock);
}
static __attribute__((noinline)) int pending(struct lmi_swap_fence *f,uint32_t id,uint32_t mode)
{
    void *owner=f->owner;
    uint32_t first=word(owner,LMI_FB_fSwapFirst),count=word(owner,LMI_FB_fSwapsWaiting);
    if(first>=2 || count>2)return -1;
    if(f->reading && (mode==2 || f->id==id))return 1;
    for(unsigned n=0;n<count;n++)
        if(mode==2 || word(owner,LMI_FB_fSwap+((first+n)&1)*0x46c+0x50)==id)return 1;
    return 0;
}
static int closed(void *client)
{
    /* Native clientClose writes fClosed under this lock. No client lock is
     * held across sleeping on the framebuffer queue lock. */
    void *lock=(void *)pointer(client,LMI_UC_fLock);if(!lock)return 1;
    IOLockLock(lock);int value=((const unsigned char *)client)[LMI_UC_fClosed];IOLockUnlock(lock);
    return value!=0;
}
static uint32_t wait_swap(void *client,void *args)
{
    if(!args || word(args,LMI_ARG_scalarInputCount)<3 || !pointer(args,LMI_ARG_scalarInput))return LMI_kIOReturnBadArgument;
    const uint64_t *in=(const void *)pointer(args,LMI_ARG_scalarInput);
    uint32_t id=(uint32_t)in[0],flags=(uint32_t)in[1],ms=(uint32_t)in[2],mode=flags&0x7fffffffu;
    if(in[1]>0xffffffffu || in[2]>0xffffffffu || mode>4)return LMI_kIOReturnBadArgument;
    void *owner=(void *)pointer(client,LMI_UC_fOwner);if(!owner)return LMI_kIOReturnNotOpen;
    void *lock=queue_lock(owner);if(!lock)return LMI_kIOReturnNotOpen;
    uint64_t deadline;clock_interval_to_deadline(ms?ms:700,1000000,&deadline);
    IOLockLock(lock);struct lmi_swap_fence *f=journal(owner);
    uint32_t result=LMI_kIOReturnNoMemory;
    if(f) {
        f->waits++;
        for(;;) {
            if(closed(client)) {result=LMI_kIOReturnNotOpen;f->closed++;break;}
            if(mode==3) {result=LMI_kIOReturnSuccess;break;}
            if(mode==4) {result=LMI_kIOReturnBadArgument;f->bad++;break;}
            int busy=pending(f,id,mode);
            if(busy<0) {result=LMI_kIOReturnBusy;f->held++;break;}
            if(!busy) {result=LMI_kIOReturnSuccess;break;}
            if(flags&0x80000000u) {result=LMI_kIOReturnBusy;f->busy++;break;}
            if(mach_absolute_time()>=deadline) {result=LMI_kIOReturnTimeout;f->timeouts++;break;}
            f->sleeps++;
            int waited=IOLockSleepDeadline(lock,&f->generation,deadline,LMI_THREAD_ABORTSAFE);
            if(waited==LMI_THREAD_INTERRUPTED) {result=LMI_kIOReturnAborted;break;}
            /* Recheck completion/close before the original deadline, including
             * simultaneous timeout and spurious wakes. Never extend it. */
        }
    }
    IOLockUnlock(lock);return result;
}
uint32_t lmi_fence_method(void *client,uint32_t selector,void *args,void *dispatch,void *target,void *reference)
{
    if(selector==6)return wait_swap(client,args);
    return lmi_fence_original_method(client,selector,args,dispatch,target,reference);
}
uint32_t lmi_fence_close(void *client)
{
    /* Publish close and wake before native terminate(). Nothing here may
     * dereference the client or its provider after original_close returns.
     * Never nest client->queue locks: wait_swap takes queue->client. */
    void *owner=(void *)pointer(client,LMI_UC_fOwner);
    void *client_lock=(void *)pointer(client,LMI_UC_fLock);
    if(client_lock) {
        IOLockLock(client_lock);
        ((unsigned char *)client)[LMI_UC_fClosed]=1;
        IOLockUnlock(client_lock);
    }
    if(owner) {
        void *lock=queue_lock(owner);
        if(lock) {
            IOLockLock(lock);struct lmi_swap_fence *f=journal(owner);
            if(f)wake(f);
            IOLockUnlock(lock);
        }
    }
    return lmi_fence_original_close(client);
}
