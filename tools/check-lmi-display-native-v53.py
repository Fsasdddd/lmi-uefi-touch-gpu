"""Run actual v53 observer and retained report bodies with explicit mocks."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-native-v53-host';out.mkdir(exist_ok=True)
s=(root/'tools/lmi-display-native-v53.c').read_text()
body=s[s.index('LMI_PIPE_CODE void lmi_dpu_observe_show('):s.index('LMI_PIPE_CODE void lmi_display_smp_prepare(')]
prefix=r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-display-probe.h"
#include "lmi-display-compositor-abi.h"
static struct {struct lmi_display_probe *probe;unsigned stopping,restoring,attempted,done;} state;
static unsigned long display_samples;
static unsigned show_calls,create_calls,diagnostic_calls;
static int draw_graphics,stop_during_show,allocation_ok,restore_ok;
static unsigned char fb[LMI_FB_CLASS_BYTES],swap[1];static void *surfaces[4];
static struct lmi_display_probe probe;
static const char display_map_failure[]="refusal";
static int stopping(void *p){(void)p;return state.stopping;}
static void loader_log_line(const char *p){(void)p;}
static void lmi_dpu_original_show(void *self,const unsigned char *a,void **b)
{(void)a;(void)b;show_calls++;if(draw_graphics)((unsigned char *)self)[LMI_FB_fGraphics]=1;if(stop_during_show)state.stopping=1;}
static struct lmi_display_probe *create(void){create_calls++;return allocation_ok?&probe:0;}
static int lmi_display_diagnostic_run(struct lmi_display_probe *p){diagnostic_calls++;p->verified=0;p->restore_ok=restore_ok;return 0;}
"""
suffix=r"""
static void reset(void){memset(&state,0,sizeof state);memset(&probe,0,sizeof probe);memset(fb,0,sizeof fb);show_calls=create_calls=diagnostic_calls=0;draw_graphics=stop_during_show=0;allocation_ok=restore_ok=1;}
static void frame(void){lmi_dpu_observe_show(fb,swap,surfaces);}
int main(void){
 reset();frame();frame();assert(show_calls==2 && !state.attempted && !create_calls);
 draw_graphics=1;frame();assert(show_calls==3 && create_calls==1 && diagnostic_calls==1 && state.done==1 && state.probe==&probe);
 frame();assert(show_calls==4 && diagnostic_calls==1);
 reset();state.stopping=1;frame();assert(!show_calls && !create_calls);
 reset();draw_graphics=stop_during_show=1;frame();assert(show_calls==1 && !create_calls);
 reset();draw_graphics=1;allocation_ok=0;frame();frame();assert(show_calls==2 && create_calls==1 && !diagnostic_calls && state.done==1);
 reset();draw_graphics=1;restore_ok=0;frame();frame();assert(show_calls==1 && diagnostic_calls==1 && !state.done && state.probe==&probe);
 puts("PASS: v53 real observer startup, single consumption, stop and retained ownership");return 0;
}
"""
context=s[s.index('struct native_context {'):s.index('static const char display_entry')]
report=s[s.index('FN void report('):s.index('FN struct lmi_display_probe *create(')]
fmt='static const char display_format[]="LMI_DPU_PROBE stage=%u ok=%u exp=%x got=%x ticks=%llu\\n";\n'
trace_tail=r"""
int main(void){struct native_context c={0};
 for(unsigned n=0;n<318;n++)report(&c,n,1,0xffffffffu,0xffffffffu,0xffffffffffffffffull);
 c.last_key=0x6b984;c.last_value=0xff159753;report(&c,1104,0,0xabcdef01,0xff159753,960000);
 c.last_key=3;c.last_value=4;report(&c,9000,0,256,1,42);
 assert(c.trace_count==320 && c.failed_stage==1104 && c.failed_key==0x6b984 && c.failed_value==0xff159753);
 char saved[320][128];memcpy(saved,c.trace,sizeof saved);
 report(&c,9001,1,0,0,0);assert(c.trace_count==320 && !memcmp(saved,c.trace,sizeof saved));
 for(unsigned n=0;n<320;n++)assert(strlen(c.trace[n])<127 && c.trace[n][strlen(c.trace[n])-1]=='\n');
 puts("PASS: actual 320-line retained report capacity, first failure and complete publication");return 0;}
"""
for name,source in [('startup',prefix+body+suffix),('trace','#include <assert.h>\n#include <stdio.h>\n#include <string.h>\n#include "lmi-display-probe.h"\n#define FN static\n'+context+fmt+report+trace_tail)]:
 src=out/(name+'.c');src.write_text(source)
 subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'tools'),str(src),'-o',str(out/name)],check=True)
 p=subprocess.run([str(out/name)],capture_output=True,text=True);(out/(name+'.log')).write_text(p.stdout+p.stderr);print(p.stdout+p.stderr);p.check_returncode()
(out/'result.json').write_text(json.dumps(dict(result='PASS',asan_ubsan=True,actual_observer_and_report_bodies=True,hardware_tested=False,sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in ('lmi-display-native-v53.c','lmi-display-probe.h','lmi-display-dma.h','lmi-display-pipeline.h','lmi-display-compositor-abi.h','check-lmi-display-native-v53.py')}),indent=2)+'\n')
