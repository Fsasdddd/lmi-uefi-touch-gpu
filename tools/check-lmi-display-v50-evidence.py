"""Check the production retained trace and interpret the candidate plan, host only."""
from pathlib import Path
import hashlib,json,subprocess,ctypes
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v50-evidence-host';out.mkdir(exist_ok=True)
s=(root/'tools/lmi-display-native-v50.c').read_text()
context=s[s.index('struct native_context {'):s.index('static const char display_entry')]
report=s[s.index('FN void report('):s.index('static const char desktop_enabled')]
prefix='#include <assert.h>\n#include <stdio.h>\n#include <string.h>\n#include "lmi-display-probe.h"\n#include "lmi-display-compositor.h"\n#define FN static\n'
fmt='static const char display_format[]="LMI_DPU_PROBE stage=%u ok=%u exp=%x got=%x ticks=%llu\\n";\n'
suffix=r"""
int main(void) {
 struct native_context c={0};
 for(unsigned n=0;n<13;n++)report(&c,n,1,0x100+n,0x200+n,0xffffffffffffffffull-n);
 assert(c.trace_count==13);
 c.last_key=0x6b984;c.last_value=0x3481259f;
 report(&c,12,0,0xabcdef01,0x3481259f,960000);
 c.last_key=42;c.last_value=43;report(&c,4,0,1,2,3);
 assert(c.failed_stage==12 && c.failed_key==0x6b984 && c.failed_value==0x3481259f);
 assert(strstr(c.trace[13],"stage=12 ok=0 exp=abcdef01 got=3481259f ticks=960000"));
 report(&c,112,0,5,1,0);assert(c.trace_count==16);
 char saved[16][128];memcpy(saved,c.trace,sizeof saved);
 for(unsigned n=0;n<100;n++)report(&c,n,1,0,0,0);
 assert(c.trace_count==16 && !memcmp(saved,c.trace,sizeof saved));
 for(unsigned n=0;n<16;n++)assert(strlen(c.trace[n])<127 && c.trace[n][strlen(c.trace[n])-1]=='\n');
 puts("PASS: retained trace order, first refusal, bounded capacity and complete lines");
}
"""
source=out/'trace-host.c';source.write_text(prefix+context+fmt+report+suffix)
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'tools'),str(source),'-o',str(out/'trace-check')],check=True)
x=subprocess.run([str(out/'trace-check')],capture_output=True,text=True);(out/'trace.log').write_text(x.stdout+x.stderr);x.check_returncode();print(x.stdout)
lib=out/'plan.so'
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',str(root/'tools/lmi-display-pipeline-v50.c'),'-o',str(lib)],check=True)
class Write(ctypes.Structure):_fields_=[('offset',ctypes.c_uint32),('value',ctypes.c_uint32)]
class Plan(ctypes.Structure):_fields_=[('write',Write*32),('count',ctypes.c_uint)]
f=ctypes.CDLL(str(lib)).lmi_qseed_configure_plan;f.argtypes=[ctypes.POINTER(Plan),ctypes.c_uint32,ctypes.c_uint32]
for pitch in (4544,4608):
 p=Plan();assert f(ctypes.byref(p),0x3000,pitch)==1
 registers={w.offset:w.value for w in p.write[:p.count]};assert len(registers)==p.count==25
 assert registers[0x5024]==pitch
 mode=registers[0x5a04]
 assert mode&1 and (mode>>16)&3==3 and (mode>>29)&3==1 and mode>>31==1
 assert mode&(1<<14) and mode&(1<<10) and not mode&(1<<13)
 assert [registers[0x5a20]>>(8*n)&127 for n in range(4)]==[4,2,4,2]
 for step_reg,phase_reg,src,dst,src_cell,dst_cell in [(0x5a10,0x5a90,1125,1080,25,24),(0x5a14,0x5a94,2436,2400,203,200)]:
  step,phase=registers[step_reg],registers[phase_reg]
  assert step==(src<<21)//dst and phase==(step-(1<<21))//2
  for n in range(dst):
   q=(phase+n*step)>>21
   assert q//src_cell==n//dst_cell and min(q+1,src-1)//src_cell==n//dst_cell
print('PASS: QSEED4 bitfields and bilinear spatial grid support at both pitches')
report=dict(result='PASS',asan_ubsan=True,hardware_tested=False,scaler_pixel_validated=False,
 sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in ('lmi-display-native-v50.c','lmi-display-pipeline-v50.c','check-lmi-display-v50-evidence.py')})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
