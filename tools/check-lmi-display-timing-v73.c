#include "lmi-display-timing-v73.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct lmi_fast_stats *lmi_fast_state;
static uint64_t clock_now,frame_ticks,source_ticks,copy_ticks,submit_ticks;
static int frame_result,submit_result,source_result,with_source,create_state;
static unsigned frame_calls,submit_calls,source_calls,alloc_calls,emit_calls,stop_calls;
static int fail_alloc,stopped;
static void *allocation;
static struct lmi_compositor compositor;
static struct lmi_display_pipeline pipeline,other_pipeline;
static unsigned char swap[8];static void *surfaces[4];
static unsigned index;static uint64_t ticket;
static uint64_t expected_now,expected_timeout;
static void *expected_surface;
uint64_t lmi_frame_ticks(void) {return clock_now;}
void *IOMallocAligned(size_t n,size_t a)
{
    alloc_calls++;assert(a==16 && n==sizeof(struct lmi_timing_stats));
    if(fail_alloc)return 0;
    assert(!allocation);allocation=aligned_alloc(a,(n+a-1)&~(a-1));
    assert(allocation);memset(allocation,0xa5,n);return allocation;
}
void bzero(void *p,size_t n) {memset(p,0,n);}
_Bool lmi_timing_original_source(void *p,uint64_t timeout)
{source_calls++;assert(p==expected_surface && timeout==expected_timeout);clock_now+=source_ticks;return source_result;}
int lmi_gpu_frame_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,
    const unsigned char *v,void **s,unsigned *i,uint64_t *t)
{
    frame_calls++;assert(c==&compositor && p==&pipeline && v==swap && s==surfaces);
    if(create_state) {assert(!lmi_fast_state);lmi_fast_state=lmi_timing_allocate(sizeof(struct lmi_fast_stats),16);}
    if(with_source) {assert(lmi_timing_source(expected_surface,expected_timeout)==source_result);}
    if(lmi_fast_state)((struct lmi_timing_stats *)lmi_fast_state)->original.copy_ticks+=copy_ticks;
    clock_now+=frame_ticks;
    if(i)*i=index;if(t)*t=ticket;
    return frame_result;
}
int lmi_timing_original_submit(struct lmi_display_pipeline *p,unsigned i,uint64_t t,uint64_t now)
{
    submit_calls++;assert((p==&pipeline || p==&other_pipeline) && i==index && t==ticket && now==expected_now);
    clock_now+=submit_ticks;return submit_result;
}
void lmi_gpu_frame_cleanup(void) {stop_calls++;stopped=1;}
void lmi_frame_emit(const char *tag,const uint64_t *values,unsigned n)
{
    const char *tags[]={"LMI_TIME_FRAME","LMI_TIME_GAP","LMI_TIME_SOURCE","LMI_TIME_COPY",
        "LMI_TIME_DPU_WAIT","LMI_TIME_SUBMIT","LMI_TIME_TOTAL","LMI_TIME_CADENCE","LMI_TIME_COUNTS"};
    assert(stopped && stop_calls==1 && emit_calls<9 && !strcmp(tag,tags[emit_calls]));
    assert(n==(emit_calls==8?6:9));
    /* Upper bound for the unchanged native 256-byte fixed-ABI formatter. */
    assert(strlen(tag)+n*21+2<=256 && values);emit_calls++;
}
static struct lmi_timing_stats *stats(void) {return (void *)lmi_fast_state;}
static void reset(int state)
{
    free(allocation);allocation=0;lmi_fast_state=0;
    clock_now=1000000;frame_ticks=38000;source_ticks=12000;copy_ticks=18000;submit_ticks=2222;
    frame_result=submit_result=source_result=1;with_source=1;create_state=0;
    frame_calls=submit_calls=source_calls=alloc_calls=emit_calls=stop_calls=0;
    fail_alloc=stopped=0;index=1;ticket=23;expected_now=1234567;
    expected_surface=&surfaces[0];expected_timeout=500;
    if(state)lmi_fast_state=lmi_timing_allocate(sizeof(struct lmi_fast_stats),16);
}
static int frame(void)
{unsigned i=0;uint64_t t=0;int r=lmi_timing_frame(&compositor,&pipeline,swap,surfaces,&i,&t);assert(i==index && t==ticket);return r;}
static int submit(struct lmi_display_pipeline *p)
{return lmi_timing_submit(p,index,ticket,expected_now);}
static void metric(enum lmi_timing_kind k,uint64_t count,uint64_t sum,uint64_t max)
{const struct lmi_timing_metric *m=stats()->metric+k;assert(m->count==count && m->sum==sum && m->max==max);
 uint64_t n=0;for(unsigned i=0;i<6;i++)n+=m->bin[i];assert(n==count);}
int main(void)
{
    reset(0);assert(!lmi_timing_allocate(279,16) && !lmi_timing_allocate(280,8) && !alloc_calls);
    lmi_fast_state=lmi_timing_allocate(280,16);assert(alloc_calls==1);
    for(unsigned n=0;n<sizeof(struct lmi_timing_stats);n++)assert(!((unsigned char *)stats())[n]);
    reset(0);fail_alloc=1;assert(!lmi_timing_allocate(280,16) && alloc_calls==1);
    reset(0);assert(frame()==1 && frame_calls==1 && source_calls==1);assert(submit(&pipeline)==1 && submit_calls==1);
    lmi_timing_cleanup();assert(stop_calls==1 && !emit_calls);
    reset(1);assert(frame()==1);metric(LMI_TIME_FRAME,1,50000,50000);metric(LMI_TIME_SOURCE,1,12000,12000);
    metric(LMI_TIME_COPY,1,18000,18000);clock_now+=77777;assert(submit(&pipeline)==1);
    metric(LMI_TIME_DPU_WAIT,1,77777,77777);metric(LMI_TIME_SUBMIT,1,2222,2222);
    metric(LMI_TIME_TOTAL,1,129999,129999);assert(stats()->matched==1 && stats()->submit_ok==1 && !stats()->armed);
    clock_now+=11111;assert(frame()==1);clock_now+=3333;assert(submit(&pipeline)==1);
    metric(LMI_TIME_GAP,1,11111,11111);metric(LMI_TIME_CADENCE,1,66666,66666);
    assert(frame_calls==2 && source_calls==2 && submit_calls==2 && !emit_calls);
    reset(1);frame_result=-1;assert(frame()==-1 && !stats()->armed && stats()->frame_other==1);
    submit_result=-1;assert(submit(&pipeline)==-1 && stats()->submit_other==1 && stats()->unmatched==1);
    metric(LMI_TIME_DPU_WAIT,0,0,0);
    reset(1);assert(frame()==1);assert(submit(&other_pipeline)==1 && stats()->unmatched==1 && !stats()->matched);
    reset(1);assert(frame()==1);ticket++;assert(submit(&pipeline)==1 && stats()->unmatched==1);
    reset(1);index=2;assert(frame()==1 && !stats()->armed && stats()->frame_other==1);
    reset(1);ticket=0;assert(frame()==1 && !stats()->armed);
    reset(1);assert(frame()==1);lmi_timing_cleanup();assert(stopped && emit_calls==9 && stop_calls==1);
    /* Boundaries are independently enumerated; zero duration is a real sample. */
    reset(1);with_source=0;copy_ticks=0;frame_result=0;
    const uint64_t duration[]={0,19200,19201,76800,76801,160000,160001,320000,320001,640000,640001};
    const uint64_t bins[]={2,2,2,2,2,1};uint64_t sum=0;
    for(unsigned i=0;i<sizeof(duration)/sizeof(*duration);i++) {frame_ticks=duration[i];sum+=duration[i];assert(!frame());}
    metric(LMI_TIME_FRAME,11,sum,640001);
    for(unsigned i=0;i<6;i++)assert(stats()->metric[LMI_TIME_FRAME].bin[i]==bins[i]);
    reset(0);create_state=1;assert(frame()==1 && stats()->armed);metric(LMI_TIME_FRAME,1,50000,50000);
    metric(LMI_TIME_COPY,1,18000,18000);
    reset(1);expected_timeout=0x10000001234ull;source_result=0;
    assert(!lmi_timing_source(expected_surface,expected_timeout));metric(LMI_TIME_SOURCE,1,12000,12000);
    reset(1);copy_ticks=0;unsigned char prefix[sizeof(struct lmi_gpu_frame_stats)];
    memcpy(prefix,stats(),sizeof(prefix));assert(frame()==1 && submit(&pipeline)==1);
    assert(!memcmp(prefix,stats(),sizeof(prefix)));lmi_timing_cleanup();assert(emit_calls==9);
    reset(1);assert(lmi_timing_frame(&compositor,&pipeline,swap,surfaces,0,0)==1 && !stats()->armed);
    free(allocation);allocation=0;lmi_fast_state=0;
    puts("PASS: 16 timing scenarios, unchanged calls/arguments/results and GPU prefix");return 0;
}
