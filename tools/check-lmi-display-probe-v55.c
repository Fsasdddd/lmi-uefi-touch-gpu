/* Strict experimental eligibility, with explicit non-pixel hardware mocks. */
#define main historical_protocol_checks
#include "check-lmi-display-dma-v55.c"
#undef main
extern int lmi_display_diagnostic_run(struct lmi_display_probe *);
static unsigned recorded,stall_after;
static void record(void *ctx,unsigned stage,int ok,uint32_t expected,uint32_t actual,uint64_t ticks)
{
    recorded++;assert(recorded<=64);probe_report(ctx,stage,ok,expected,actual,ticks);
    if(stage==stall_after)((struct fake *)ctx)->stall=1;
}
static struct fake *setup_experiment(void)
{
    struct fake *f=setup_probe();struct lmi_display_probe *p=(struct lmi_display_probe *)f->d;
    f->normalized_signature=1;p->keep_active=1;p->report=record;recorded=stall_after=0;return f;
}
int main(void)
{
    struct fake *f=setup_experiment();struct lmi_display_probe *p=(struct lmi_display_probe *)f->d;
    assert(lmi_display_diagnostic_run(p)==1 && p->verified && p->keep_active && !p->restore_ok);
    assert(p->frames==40 && p->pipeline.submitted==40 && p->pipeline.completed==40 && recorded==49);
    assert(*reg(f,0,0x5a20)==0x03050305u && *reg(f,0,0x5a04)==0x20036401u);
    lmi_pipeline_stop(&p->pipeline);assert(lmi_pipeline_detach_after_cpu_stop(&p->pipeline));restored(f);destroy(f);
    for(unsigned failure=0;failure<4;failure++) {
        f=setup_experiment();p=(struct lmi_display_probe *)f->d;
        if(failure==0)f->scaled_bad=1;
        if(failure==1)f->normalized_signature=2;
        if(failure==2)f->normalized_signature=0;
        if(failure==3)f->drop_scaler_enable=1;
        assert(!lmi_display_diagnostic_run(p) && !p->verified && p->restore_ok);
        assert(p->pipeline.submitted<=5 && p->pipeline.submitted==p->pipeline.completed);
        restored(f);destroy(f);
    }
    const unsigned stops[]={1,2,1000,1003,1004,1007,1008,1048,90,91};
    for(unsigned n=0;n<sizeof stops/sizeof *stops;n++) {
        f=setup_experiment();p=(struct lmi_display_probe *)f->d;f->stop_stage=stops[n];
        assert(!lmi_display_diagnostic_run(p) && !p->verified && f->probe_stopping);
        f->restore_mode=1;assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    }
    f=setup_experiment();p=(struct lmi_display_probe *)f->d;stall_after=1003;
    assert(!lmi_display_diagnostic_run(p) && !p->verified && !p->restore_ok && f->d->pending && f->d->mapped);
    assert(!lmi_dma_restore(f->d));f->stall=0;assert(lmi_dma_restore(f->d));restored(f);destroy(f);
    f=setup_experiment();p=(struct lmi_display_probe *)f->d;p->keep_active=0;
    assert(!lmi_display_diagnostic_run(p) && !p->verified && p->restore_ok && p->frames==40);
    restored(f);destroy(f);
    puts("PASS: 40-frame strict normalized experiment; pinned endpoints, first CRC refusal, stop, pending hold and compositor refusal");
}
