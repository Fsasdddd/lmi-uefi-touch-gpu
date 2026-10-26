/* Real diagnostic state machine with adverse mock MMIO, no pixel proof. */
#define main historical_protocol_checks
#include "check-lmi-display-dma-v54.c"
#undef main
extern int lmi_display_diagnostic_run(struct lmi_display_probe *);
extern int lmi_display_diagnostic_pattern(struct lmi_display_probe *,unsigned,int,unsigned);
struct row {unsigned stage;int ok;uint32_t expected,actual;uint64_t ticks;};
static struct row rows[576];static unsigned row_count,stall_after;
static void record(void *context,unsigned stage,int ok,uint32_t expected,uint32_t actual,uint64_t elapsed)
{
 assert(row_count<576);rows[row_count++]=(struct row){stage,ok,expected,actual,elapsed};
 probe_report(context,stage,ok,expected,actual,elapsed);
 if(stage==stall_after)((struct fake *)context)->stall=1;
}
static struct fake *setup_diagnostic(void)
{
 struct fake *f=setup_probe();struct lmi_display_probe *p=(struct lmi_display_probe *)f->d;
 p->report=record;row_count=stall_after=0;memset(rows,0,sizeof rows);return f;
}
static void patterns(struct lmi_display_probe *p)
{
 for(unsigned seed=0;seed<10;seed++)for(unsigned scaled=0;scaled<2;scaled++) {
  assert(lmi_display_diagnostic_pattern(p,0,(int)scaled,seed));
  struct lmi_frame_buffer *b=p->dma.buffer;unsigned w=scaled?1125:1080,h=scaled?2436:2400;
  for(unsigned y=0;y<h;y++)for(unsigned x=0;x<b->pitch/4;x++) {
   uint32_t v=*(uint32_t *)(b->pixels+(uintptr_t)y*b->pitch+4*x);
   if(x>=w) {assert(v==0xff00ff00u);continue;}
   unsigned kind=seed>>1,grid=0;
   if(kind==1 || kind==3)grid+=x/(scaled?25:24);
   if(kind==2 || kind==3)grid+=y/(scaled?203:200);
   assert(v==(kind==4?((seed&1)?0xffffffffu:0xff000000u):(((grid+(seed&1))&1)?0xffd03070u:0xff20c0a0u)));
  }
  for(uint64_t off=(uint64_t)h*b->pitch;off<b->bytes;off+=4)assert(*(uint32_t *)(b->pixels+off)==0xff00ff00u);
 }
 assert(!lmi_display_diagnostic_pattern(p,2,0,0));
 assert(!lmi_display_diagnostic_pattern(p,0,0,10));
}
int main(void)
{
 for(unsigned mismatch=0;mismatch<2;mismatch++) {
  struct fake *f=setup_diagnostic();struct lmi_display_probe *p=(struct lmi_display_probe *)f->d;
  p->keep_active=1;f->scaled_bad=mismatch;
  assert(!lmi_display_diagnostic_run(p) && !p->verified && !p->keep_active && p->restore_ok);
  assert(p->pipeline.submitted==480 && p->pipeline.completed==480 && row_count==524);
  assert(rows[522].stage==90 && rows[522].ok && rows[522].expected==480 && rows[522].actual==480);
  assert(rows[522].ticks==(mismatch?0u:0xffffffffffull));
  for(unsigned variant=0;variant<8;variant++)for(unsigned kind=0;kind<5;kind++) {
   unsigned at=2+13*(variant*5+kind),base=1000+100*variant+20*kind;
   for(unsigned n=0;n<12;n++) {
    assert(rows[at+n].stage==base+n);
    assert(rows[at+n].ok==(n<8 || !mismatch));
   }
   assert(rows[at+12].stage==base+12 && rows[at+12].ok==!mismatch);
  }
  restored(f);patterns(p);destroy(f);
 }
 const unsigned stops[]={1,2,1000,1003,1004,1007,1008,1011,1012,1792,90};
 for(unsigned n=0;n<sizeof stops/sizeof *stops;n++) {
  struct fake *f=setup_diagnostic();struct lmi_display_probe *p=(struct lmi_display_probe *)f->d;
  f->stop_stage=stops[n];assert(!lmi_display_diagnostic_run(p));
  assert(f->probe_stopping && !p->verified && !p->restore_ok);
  unsigned before=f->starts;f->restore_mode=1;assert(lmi_dma_restore(f->d));
  assert(!p->verified && f->starts>=before);restored(f);destroy(f);
 }
 struct fake *f=setup_diagnostic();struct lmi_display_probe *p=(struct lmi_display_probe *)f->d;
 stall_after=1007;assert(!lmi_display_diagnostic_run(p));
 assert(!p->verified && !p->restore_ok && f->d->pending && f->d->mapped);
 assert(!lmi_dma_restore(f->d));f->stall=0;assert(lmi_dma_restore(f->d));restored(f);destroy(f);
 f=setup_diagnostic();p=(struct lmi_display_probe *)f->d;f->drop_scaler_enable=1;
 assert(!lmi_display_diagnostic_run(p) && !p->verified && p->restore_ok);
 assert(p->pipeline.submitted==4 && p->pipeline.completed==4);restored(f);destroy(f);
 puts("PASS: batched diagnostic protocol, 480-frame traversal, mismatches stay diagnostic, fault/stop recovery and poison bounds");
 return 0;
}
