"""Bound census reads to the pinned DT blocks; host checks do not prove live DPU behavior."""
from pathlib import Path
import hashlib,json,re,subprocess

r=Path(__file__).resolve().parents[1]
source=r/'tools/lmi-display-census.c'
body=source.read_text()
out=r/'out/lmi-display-census-host'
out.mkdir(exist_ok=True)
dts=(r/'device-info/live.dts').read_text().split('qcom,mdss_mdp@ae00000 {',1)[1].split('qcom,sde-sspp-src-size',1)[0]
def dt(name):
    raw=bytes.fromhex(re.search(re.escape(name)+r' = \[([^]]+)\]',dts)[1])
    return [int.from_bytes(raw[n:n+4],'big') for n in range(0,len(raw),4)]
blocks={}
for name,prop in [('ctl','ctl'),('sspp','sspp'),('intf','intf'),('pp','pp')]:
    blocks[name]=[int(v,0) for v in re.search(r'\b'+name+r'\[\]=\{([^}]+)',body)[1].split(',')]
    assert blocks[name]==dt('qcom,sde-'+prop+'-off')
assert dt('reg')[:2]==[0xae00000,0x84208]
# Independent vendor register allowlist; no status-clear or trigger addresses.
registers={'ctl':[0,0x14,0x18,0x1c,0x64,0xf4],
           'sspp':[0,8,0xc,0x10,0x14,0x24,0x30,0x38],
           'intf':[0,4,0xac,0xb0,0x26c,0x280,0x284,0x288,0x28c,0x294,0x298,0x2ac,0x2b0,0x2b4],
           'pp':[0,4,8,0xc,0x14,0x28,0x2c,0x30]}
allowed=sorted({base+offset for name,bases in blocks.items() for base in bases for offset in registers[name]})
assert all(x%4==0 and 0<=x<=0x84208-4 for x in allowed)
production=body.split('#ifndef LMI_DISPLAY_CENSUS_HOST',1)[1].split('#endif',1)[0]
assert production.count('*(volatile const uint32_t *)')==1
assert not re.search(r'\*\([^;]+\)\s*=',production)
prefix=r'''
#include <assert.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#define LMI_DISPLAY_CENSUS_HOST 1
static unsigned reads,pauses,ticks,lines; static uint64_t now;
static const uint32_t allowed[]={ALLOWED};
static uint32_t lmi_display_read(uint32_t offset) {
    int found=0; for(unsigned i=0;i<sizeof(allowed)/sizeof(*allowed);i++) found|=allowed[i]==offset;
    assert(found); reads++; return offset^(uint32_t)now;
}
static uint64_t lmi_display_tick(void) {ticks++; return now;}
static void lmi_display_pause(void) {pauses++; now+=19200;}
static void lmi_display_emit(const char *fmt,...) {
    assert(strstr(fmt,"LMI_DPU_")==fmt); lines++;
}
'''.replace('ALLOWED',','.join(hex(v) for v in allowed))
suffix=r'''
int main(void) {
    lmi_display_census("refused",0); assert(!reads&&!pauses&&!ticks&&!lines);
    for(unsigned pass=1;pass<=2;pass++) {
        lmi_display_census(pass==1?"before":"after",1);
        assert(reads==pass*540 && pauses==pass*23 && ticks==pass*24);
        assert(lines==pass*542);
    }
    puts("PASS: fixed reads, denied gate, two bounded snapshots"); return 0;
}
'''
(out/'check.c').write_text(prefix+body+suffix)
subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(out/'check.c'),'-o',str(out/'check')],check=True)
run=subprocess.run([str(out/'check')],text=True,capture_output=True,check=True)
(out/'host.log').write_text(run.stdout+run.stderr)
report=dict(result='PASS',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),dts_sha256=hashlib.sha256((r/'device-info/live.dts').read_bytes()).hexdigest(),allowed_offsets=[hex(x) for x in allowed],reads_per_snapshot=540,samples=24,pause_us=1000,register_writes=0,scope='Host logic and fixed address scope only; active controller selection and refresh timing require device evidence.')
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(run.stdout,end='')
