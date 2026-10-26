"""Exercise the real presenter body and compositor with the current pipeline."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v55-desktop-host';out.mkdir(exist_ok=True)
s=(root/'tools/lmi-display-native-v55.c').read_text()
body=s[s.index('FN void desktop_show('):s.index('FN struct lmi_display_probe *create(')]
prefix=r'''
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "lmi-display-probe.h"
#include "lmi-display-compositor.h"
#define FN static
struct native_context {struct lmi_display_probe probe;struct lmi_compositor compositor;};
static struct {unsigned done;} state;
static int consumed,poll_result,submit_result,restore_result,stopped,stop_after_compose;
static unsigned composes,polls,submits,stops,restores,replays,logs,delays;
static const char desktop_fallback[]="restored",desktop_failed[]="retained";
int lmi_compositor_frame(struct lmi_compositor *c,struct lmi_display_pipeline *p,const unsigned char *s,void **u,unsigned *i,uint64_t *t)
{(void)c;(void)p;(void)s;(void)u;composes++;*i=1;*t=9;if(stop_after_compose)stopped=1;return consumed;}
int lmi_pipeline_poll(struct lmi_display_pipeline *p,uint64_t t)
{(void)t;polls++;if(poll_result>0)p->scanning=-1;return poll_result;}
int lmi_pipeline_submit(struct lmi_display_pipeline *p,unsigned i,uint64_t ticket,uint64_t now)
{(void)p;(void)now;assert(i==1 && ticket==9);submits++;return submit_result;}
void lmi_pipeline_stop(struct lmi_display_pipeline *p){(void)p;stops++;}
int lmi_pipeline_detach_after_cpu_stop(struct lmi_display_pipeline *p){(void)p;restores++;return restore_result;}
static int stopping(void *c){(void)c;return stopped;}
static uint64_t ticks(void *c){(void)c;return 100;}
static void delay(unsigned t){assert(t==50);delays++;poll_result=1;}
static void loader_log_line(const char *line){assert(!strcmp(line,restore_result?desktop_fallback:desktop_failed));logs++;}
static void lmi_dpu_original_show(void *self,const unsigned char *s,void **u){(void)self;(void)s;(void)u;replays++;}
'''
tail=r'''
static struct native_context c;
static void reset(void){memset(&c,0,sizeof c);c.probe.pipeline.scanning=-1;state.done=2;
 consumed=poll_result=submit_result=restore_result=1;stopped=stop_after_compose=0;
 composes=polls=submits=stops=restores=replays=logs=delays=0;}
static void frame(void){desktop_show(&c,0,0,0);assert(composes==1);}
int main(void){
 reset();frame();assert(submits==1 && !polls && !restores && !replays && state.done==2);
 reset();c.probe.pipeline.scanning=0;poll_result=0;frame();assert(polls==2 && delays==1 && submits==1 && !restores);
 reset();consumed=0;frame();assert(restores==1 && stops==1 && logs==1 && replays==1 && state.done==1 && !submits);
 reset();consumed=-1;frame();assert(restores==1 && !replays && state.done==1 && !submits);
 reset();submit_result=-1;frame();assert(submits==1 && restores==1 && !replays && state.done==1);
 reset();c.probe.pipeline.scanning=0;poll_result=-1;frame();assert(!submits && restores==1 && !replays && state.done==1);
 reset();consumed=0;restore_result=0;frame();assert(restores==1 && state.done==0 && !replays && logs==1);
 reset();stop_after_compose=1;frame();assert(!polls && !submits && !restores && !replays);
 puts("PASS: real presenter normal flip, outstanding completion, fault and fallback ownership, no queue replay after consumption");
}
'''
(out/'presenter.c').write_text(prefix+body+tail)
commands=[('presenter',[out/'presenter.c']),('compositor',[root/'tools/check-lmi-display-compositor.c',root/'tools/lmi-display-compositor.c',root/'tools/lmi-display-pipeline-v51.c'])]
for name,inputs in commands:
    subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'tools'),*map(str,inputs),'-o',str(out/name)],check=True)
    p=subprocess.run([str(out/name)],capture_output=True,text=True);(out/(name+'.log')).write_text(p.stdout+p.stderr);print(p.stdout+p.stderr);p.check_returncode()
names=['lmi-display-native-v55.c','lmi-display-compositor.c','lmi-display-compositor.h','lmi-display-compositor-abi.h','lmi-display-pipeline-v51.c','lmi-display-pipeline.h','check-lmi-display-compositor.c','check-lmi-display-v55-desktop.py']
(out/'result.json').write_text(json.dumps(dict(result='PASS',asan_ubsan=True,hardware_tested=False,
    actual_presenter_body=True,compositor_with_current_pipeline=True,sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names}),indent=2)+'\n')
