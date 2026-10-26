"""Run the exact observer C body with mocked hardware services, host only."""
from pathlib import Path
import hashlib,json,subprocess

root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-display-v55-startup-host';out.mkdir(exist_ok=True)
native=root/'tools/lmi-display-native-v55.c'
source=native.read_text()
body=source[source.index('LMI_PIPE_CODE void lmi_dpu_observe_show('):
    source.index('LMI_PIPE_CODE void lmi_display_smp_prepare(')]
# Only the observer under test is taken from production. Register access,
# composition and DMA are explicit mocks, so this cannot establish GPU proof.
prefix=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-display-probe.h"
#include "lmi-display-compositor.h"
#include "lmi-display-compositor-abi.h"
static volatile struct {
    struct lmi_display_probe *probe;
    unsigned stopping,restoring,attempted,done;
} state;
static volatile unsigned long display_samples;
struct native_context {struct lmi_display_probe probe;struct lmi_compositor compositor;uint64_t began;};
static struct native_context context;
static unsigned show_calls,create_calls,probe_calls,desktop_calls;
static int draw_graphics,stop_during_show,allocation_ok,probe_ok;
static const char display_map_failure[]="refusal";
static int stopping(void *p) {(void)p;return state.stopping;}
static void lmi_dpu_original_show(void *self,const unsigned char *swap,void **surfaces)
{
    (void)swap;(void)surfaces;show_calls++;
    if(draw_graphics)((unsigned char *)self)[LMI_FB_fGraphics]=1;
    if(stop_during_show)state.stopping=1;
}
static void loader_log_line(const char *s) {(void)s;}
static struct lmi_display_probe *create(void) {create_calls++;return allocation_ok?&context.probe:0;}
static int gpu_ready(void *p,void *s) {(void)p;(void)s;return 1;}
static void original_show(void *p,void *self,const unsigned char *swap,void **surfaces)
{(void)p;lmi_dpu_original_show(self,swap,surfaces);}
static uint64_t ticks(void *p) {(void)p;return 100;}
static void desktop_show(struct native_context *c,void *self,const unsigned char *swap,void **surfaces)
{(void)c;(void)self;(void)swap;(void)surfaces;desktop_calls++;}
int lmi_compositor_init(struct lmi_compositor *c,void *s,const struct lmi_compositor_services *io)
{(void)c;(void)s;(void)io;return 1;}
int lmi_display_diagnostic_run(struct lmi_display_probe *p)
{probe_calls++;p->frames=probe_ok?40:0;p->verified=probe_ok;p->restore_ok=!probe_ok;return probe_ok;}
'''
suffix=r'''
static unsigned char framebuffer[LMI_FB_CLASS_BYTES],swap[1];
static void *surfaces[4];
static void reset(void)
{
    memset((void *)&state,0,sizeof(state));memset(&context,0,sizeof(context));
    memset(framebuffer,0,sizeof(framebuffer));display_samples=0;
    show_calls=create_calls=probe_calls=desktop_calls=0;
    draw_graphics=stop_during_show=0;allocation_ok=probe_ok=1;
}
static void frame(void) {lmi_dpu_observe_show(framebuffer,swap,surfaces);}
int main(void)
{
    reset();frame();frame();
    assert(show_calls==2 && !state.attempted && !create_calls && !probe_calls);
    draw_graphics=1;frame();
    assert(show_calls==3 && create_calls==1 && probe_calls==1 && state.done==2);
    frame();assert(show_calls==3 && desktop_calls==1 && probe_calls==1);
    reset();state.stopping=1;frame();assert(!show_calls && !create_calls);
    reset();draw_graphics=1;stop_during_show=1;frame();
    assert(show_calls==1 && !create_calls && !state.attempted);
    reset();draw_graphics=1;allocation_ok=0;frame();frame();
    assert(show_calls==2 && create_calls==1 && !probe_calls && state.done==1);
    reset();draw_graphics=1;probe_ok=0;frame();frame();
    assert(show_calls==2 && probe_calls==1 && !desktop_calls && state.done==1);
    reset();framebuffer[LMI_FB_fGraphics]=1;frame();
    assert(show_calls==1 && probe_calls==1 && state.done==2);
    puts("PASS: 7 startup and queue-consumption scenarios (mocked services)");
}
'''
path=out/'startup-host.c';path.write_text(prefix+body+suffix)
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
    '-fsanitize=address,undefined','-I',str(root/'tools'),str(path),'-o',str(out/'check')],check=True)
result=subprocess.run([str(out/'check')],capture_output=True,text=True)
(out/'host.log').write_text(result.stdout+result.stderr)
result.check_returncode()
report=dict(result='PASS',scenarios=7,asan_ubsan=True,hardware_tested=False,
    exact_observer_body=True,mocked_hardware_services=True,
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (native,Path(__file__),root/'tools/lmi-display-compositor-abi.h')})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(result.stdout)
