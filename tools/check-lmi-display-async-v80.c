#define _DEFAULT_SOURCE
#include "lmi-display-async-v80.h"
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

struct lock {pthread_mutex_t m;pthread_cond_t cv;};
struct source {unsigned ready;uint32_t pixels[64];};
struct env {
    struct lmi_async_native_context *native;
    pthread_t worker;
    void (*entry)(void *,int);void *arg;
    _Atomic unsigned gate,grants,automatic,bad;
    unsigned lock_fail,thread_fail,clean_fail,partial;
    unsigned created,ref_drop,old_show,cleanup,restored,starts,busy,first,value,checks,emitted;
    uint32_t expected[1024];
    uint64_t emitted_values[10];
};
static struct env *g;
struct lmi_fast_stats *lmi_fast_state;
volatile struct lmi_async_native_state lmi_async_native_state;
static struct lmi_async_context *ctx(void) {return &((struct lmi_async_stats *)lmi_fast_state)->async;}
void *IOMallocAligned(size_t bytes,size_t alignment)
{void *p=0;assert(!posix_memalign(&p,alignment,bytes));memset(p,0xa5,bytes);return p;}
void bzero(void *p,size_t bytes) {memset(p,0,bytes);}
void *IOLockAlloc(void)
{
    if(g->lock_fail)return 0;
    struct lock *p=calloc(1,sizeof(*p));assert(p);
    pthread_mutexattr_t attr;assert(!pthread_mutexattr_init(&attr));
    assert(!pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_ERRORCHECK));
    assert(!pthread_mutex_init(&p->m,&attr));assert(!pthread_mutexattr_destroy(&attr));
    assert(!pthread_cond_init(&p->cv,0));return p;
}
void IOLockLock(void *p) {assert(!pthread_mutex_lock(&((struct lock *)p)->m));}
void IOLockUnlock(void *p) {assert(!pthread_mutex_unlock(&((struct lock *)p)->m));}
void IOLockWakeup(void *p,void *event,int one)
{assert(event==ctx());assert(!one);assert(!pthread_cond_broadcast(&((struct lock *)p)->cv));}
int IOLockSleep(void *p,void *event,int mode)
{assert(event==ctx() && mode==1);assert(!pthread_cond_wait(&((struct lock *)p)->cv,&((struct lock *)p)->m));return 0;}
void delay(unsigned us) {assert(us==50);usleep(us);}
void IOSleep(unsigned ms) {assert(ms==1000);pthread_exit((void *)1);}
static void *start_worker(void *unused)
{
    (void)unused;
    while(!atomic_load(&g->gate))usleep(50);
    g->entry(g->arg,0);assert(0);return 0;
}
int kernel_thread_start(void (*entry)(void *,int),void *arg,void **thread)
{
    if(g->thread_fail)return 5;
    g->entry=entry;g->arg=arg;g->created=1;
    assert(!pthread_create(&g->worker,0,start_worker,0));*thread=&g->worker;return 0;
}
void thread_deallocate(void *thread) {assert(thread==&g->worker);g->ref_drop++;}
uint64_t lmi_frame_ticks(void)
{struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return (uint64_t)t.tv_sec*19200000+(uint64_t)t.tv_nsec*192/10000;}
void lmi_async_original_show(void *owner,const unsigned char *swap,void **surfaces)
{assert(owner && swap && surfaces);g->old_show++;}
static int validate(void *o,const struct lmi_frame_buffer b[2]) {assert(o==g);return b[0].pixels!=b[1].pixels;}
static int clean(void *o,const struct lmi_frame_buffer *b)
{
    assert(o==g);
    const uint32_t *p=(const void *)b->pixels;
    assert(g->starts<1024);
    for(unsigned n=0;n<64;n++)assert(p[n]==g->expected[g->starts]);
    return !g->clean_fail;
}
static int kickoff(void *o,const struct lmi_frame_buffer *b,uint32_t *first)
{
    assert(o==g && !g->busy);g->busy=1;g->value=b->iova;
    *first=g->first;g->starts++;return 1;
}
static int sample(void *o,struct lmi_display_completion *c)
{
    assert(o==g && g->busy);g->checks++;
    unsigned done=atomic_load(&g->automatic) || g->starts<=atomic_load(&g->grants);
    c->source=g->value;c->frame=g->first;c->line=0;c->status=0;
    if(done) {
        c->frame=g->first+1;c->line=4;c->status=1;
        switch(atomic_load(&g->bad)) {
        case 1:c->source^=4096;break;
        case 2:c->frame++;break;
        case 3:c->line=3;break;
        case 4:c->status=0;break;
        }
        if(c->source==g->value && c->frame-g->first==1 && c->line==4 && c->status==1) {
            g->busy=0;g->first++;
        }
    }
    return 1;
}
static int restore(void *o)
{assert(o==g && g->cleanup==1);g->busy=0;g->restored++;return 1;}
int lmi_gpu_frame_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *swap,void **surfaces,unsigned *index,uint64_t *ticket)
{
    assert(c==&g->native->compositor && p==&g->native->probe.pipeline && swap && surfaces);
    struct source *src=surfaces[0];assert(src && src->ready);
    int n=lmi_pipeline_acquire(p,ticket);assert(n>=0 && n<2);
    *index=(unsigned)n;
    memcpy((void *)p->buffer[n].pixels,src->pixels,sizeof(src->pixels));
    if(g->partial)return -1;
    assert(lmi_pipeline_complete_frame(p,(unsigned)n,*ticket));c->frames++;return 1;
}
int lmi_timing_original_submit(struct lmi_display_pipeline *p,unsigned n,uint64_t ticket,uint64_t now)
{return lmi_pipeline_submit(p,n,ticket,now);}
_Bool lmi_timing_original_source(void *p,uint64_t ms) {(void)p;(void)ms;return 1;}
void lmi_gpu_frame_cleanup(void) {assert(0);}
void lmi_frame_emit(const char *tag,const uint64_t *values,unsigned n)
{
    assert(!strcmp(tag,"LMI_DPU_ASYNC") && n==10 && g->cleanup==1 && g->restored==1);
    memcpy(g->emitted_values,values,10*sizeof(*values));g->emitted++;
}
void lmi_async_original_cleanup(void)
{
    __atomic_store_n(&lmi_async_native_state.stopping,1,__ATOMIC_RELEASE);
    struct lmi_async_context *c=ctx();
    if(c->lock) {IOLockLock(c->lock);IOLockWakeup(c->lock,c,0);IOLockUnlock(c->lock);}
    atomic_store(&g->gate,1);
    if(g->created)assert(!pthread_join(g->worker,0));
    g->cleanup=1;
    lmi_pipeline_stop(&g->native->probe.pipeline);
    assert(lmi_pipeline_detach_after_cpu_stop(&g->native->probe.pipeline));
}
static void setup(void)
{
    g=calloc(1,sizeof(*g));assert(g);
    g->native=calloc(1,sizeof(*g->native));assert(g->native);
    memset((void *)&lmi_async_native_state,0,sizeof(lmi_async_native_state));
    lmi_async_native_state.probe=&g->native->probe;lmi_async_native_state.done=2;
    lmi_fast_state=lmi_async_allocate(sizeof(*lmi_fast_state),16);assert(lmi_fast_state);
    struct lmi_frame_buffer b[2];
    for(unsigned n=0;n<2;n++)b[n]=(struct lmi_frame_buffer){(uintptr_t)IOMallocAligned(4096,4096),4096,0x20000+n*0x10000,64,4,4};
    const struct lmi_display_ops ops={validate,clean,kickoff,sample,restore};
    assert(lmi_pipeline_init(&g->native->probe.pipeline,b,&ops,g,4,1,19200000*5ull));
    for(unsigned n=0;n<1024;n++)g->expected[n]=n+1;
    atomic_store(&g->gate,1);
}
static struct source *source(unsigned value)
{struct source *s=calloc(1,sizeof(*s));assert(s);s->ready=1;for(unsigned n=0;n<64;n++)s->pixels[n]=value;return s;}
static void drop_source(void *opaque)
{struct source *s=opaque;memset(s,0xcc,sizeof(*s));free(s);}
static void show(unsigned value)
{
    struct source *s=source(value);void *surfaces[4]={s};unsigned char swap[1]={0};
    pthread_cleanup_push(drop_source,s);
    lmi_async_show(g,swap,surfaces);
    pthread_cleanup_pop(1); /* worker must never read a retired source */
}
static void wait_count(unsigned which,uint64_t count)
{
    uint64_t began=lmi_frame_ticks();
    for(;;) {
        struct lmi_async_context *c=ctx();IOLockLock(c->lock);
        uint64_t value=which==0?c->submitted:which==1?c->completed:which==2?c->failed:c->enqueued;
        IOLockUnlock(c->lock);
        if(value>=count)return;
        assert(lmi_frame_ticks()-began<19200000*3ull);usleep(100);
    }
}
static void finish(void)
{
    lmi_async_cleanup();assert(g->emitted==1 && g->restored==1);
    if(g->created)assert(g->ref_drop==1);
    struct lock *lock=ctx()->lock;
    if(lock) {assert(!pthread_mutex_destroy(&lock->m));assert(!pthread_cond_destroy(&lock->cv));free(lock);}
    for(unsigned n=0;n<2;n++)free((void *)g->native->probe.pipeline.buffer[n].pixels);
    free(lmi_fast_state);lmi_fast_state=0;free(g->native);free(g);g=0;
}
struct job {unsigned value;_Atomic unsigned returned;};
static void *show_job(void *opaque) {struct job *j=opaque;show(j->value);atomic_store(&j->returned,1);return 0;}

int main(void)
{
    unsigned cases=0;
    setup();atomic_store(&g->gate,0);show(1);
    assert(ctx()->enqueued==1 && ctx()->submitted==0); /* no worker schedule needed to retire source */
    atomic_store(&g->gate,1);wait_count(0,1);show(2);
    assert(ctx()->enqueued==2); /* previous scan unfinished; current source already destroyed */
    struct job j={3,0};pthread_t third;assert(!pthread_create(&third,0,show_job,&j));
    usleep(10000);assert(!atomic_load(&j.returned)); /* neither target is free */
    atomic_store(&g->grants,1);assert(!pthread_join(third,0));assert(atomic_load(&j.returned));
    atomic_store(&g->grants,3);wait_count(1,3); /* idle final frame flushes without another show */
    assert(ctx()->enqueued==ctx()->submitted && ctx()->completed==3 && !ctx()->failed);
    finish();cases++;

    setup();atomic_store(&g->automatic,1);
    for(unsigned n=1;n<=512;n++)show(n);
    wait_count(1,512);assert(ctx()->enqueued==512 && ctx()->submitted==512 && !ctx()->failed);
    assert(((struct lmi_async_stats *)lmi_fast_state)->prior.matched==512);
    finish();cases++;

    for(unsigned bad=1;bad<=4;bad++) {
        setup();atomic_store(&g->bad,bad);show(1);wait_count(0,1);atomic_store(&g->grants,1);
        if(bad<=2) {wait_count(2,1);assert(g->native->probe.pipeline.failed);}
        else {
            usleep(10000);IOLockLock(ctx()->lock);assert(!ctx()->completed && g->busy);IOLockUnlock(ctx()->lock);
            atomic_store(&g->bad,0);wait_count(1,1);
        }
        finish();cases++;
    }
    setup();g->clean_fail=1;show(1);wait_count(2,1);assert(!g->starts && g->native->probe.pipeline.failed);
    finish();cases++;

    for(unsigned kind=0;kind<2;kind++) {
        setup();g->lock_fail=kind==0;g->thread_fail=kind==1;show(1);
        assert(g->old_show==1 && !ctx()->started && !g->starts);
        finish();cases++;
    }
    setup();g->partial=1;struct job partial={1,0};pthread_t failure;
    assert(!pthread_create(&failure,0,show_job,&partial));assert(!pthread_join(failure,0));
    assert(!atomic_load(&partial.returned) && ctx()->failed && !ctx()->enqueued && !g->starts);
    finish();cases++;

    setup();show(1);wait_count(0,1); /* stop during scan, only post-join restore detaches */
    finish();cases++;
    setup();atomic_store(&g->gate,0);show(1); /* stop with a ready unpublished frame */
    finish();cases++;
    printf("PASS: %u asynchronous integration scenarios; 512-frame stream; real pipeline/timing code\n",cases);
    return 0;
}
