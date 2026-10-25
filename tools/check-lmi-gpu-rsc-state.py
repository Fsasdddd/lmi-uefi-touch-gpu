"""Run actual census functions under ASan/UBSan; forbid writes and extra reads."""
from pathlib import Path
import runpy
import subprocess

root=Path(__file__).resolve().parents[1]
decoder=runpy.run_path(str(root/'tools/verify-lmi-gpu-rsc-state.py'))
source=(root/'tools/lmi-gpu-probe.c').read_text()
code=source[source.index('static int rsc_state_bank('):source.index('\n#endif\nstatic int gmu_readonly')]
prefix=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned int u32;
typedef unsigned long long u64;
static u32 cc[0x9000/4],gm[0x30000/4],rs[0x10000/4],pd[0x10000/4],qp[0x1000/4];
static const u32 bases[]={0x3d90000,0x3d6a000,0x3de0000,0xb290000,0xc300000};
static const u32 sizes[]={sizeof(cc),sizeof(gm),sizeof(rs),sizeof(pd),sizeof(qp)};
static u32 *const regions[]={cc,gm,rs,pd,qp};
static unsigned maps,reads,fail,ok,refused,map_failed,verbose;
static unsigned char snapshot[sizeof(cc)+sizeof(gm)+sizeof(rs)+sizeof(pd)+sizeof(qp)];
static u64 io_map(u64 base,u64 size) {
    unsigned bank=maps++;assert(bank<5 && base==bases[bank] && size==sizes[bank]);
    return fail==bank+1?0:(u64)regions[bank];
}
static u32 smmu_rd32(volatile u32 *p) {
    unsigned found=0;
    for(unsigned i=0;i<5;i++)if((uintptr_t)p>=(uintptr_t)regions[i] &&
       (uintptr_t)p<(uintptr_t)regions[i]+sizes[i])found=1;
    assert(found);reads++;return *p;
}
static void field(const char *s,u64 v) {if(verbose)printf("%s%016llx\n",s,v);}
static void log_line(const char *s) {
    if(!strcmp(s,"LMI_GPU_RSC_STATE_OK\n"))ok++;
    if(!strcmp(s,"LMI_GPU_RSC_STATE_RESET_REFUSED\n"))refused++;
    if(!strcmp(s,"LMI_GPU_RSC_STATE_MAP_FAILED\n"))map_failed++;
    if(verbose)fputs(s,stdout);
}
static void seed(void) {
    unsigned at=0;
    for(unsigned i=0;i<5;i++) {
        for(unsigned n=0;n<sizes[i]/4;n++)regions[i][n]=bases[i]+4*n;
    }
    gm[0x14000/4]=1;gm[0x14070/4]=0;rs[3]=0x4000000a;
    for(unsigned i=0;i<5;i++) {memcpy(snapshot+at,regions[i],sizes[i]);at+=sizes[i];}
    maps=reads=ok=refused=map_failed=0;
}
static void unchanged(void) {
    unsigned at=0;
    for(unsigned i=0;i<5;i++){assert(!memcmp(snapshot+at,regions[i],sizes[i]));at+=sizes[i];}
}
'''
suffix=r'''
int main(void) {
    seed();verbose=1;rsc_state(gm);verbose=0;
    assert(maps==5 && reads==58 && ok==1 && !refused && !map_failed);unchanged();
    for(fail=1;fail<=5;fail++) {
        seed();rsc_state(gm);assert(maps==fail && !ok && map_failed==1 && !refused);unchanged();
    }
    fail=0;seed();gm[0x14000/4]=0;rsc_state(gm);
    assert(!maps && reads==1 && refused==1 && !ok);
    seed();gm[0x14070/4]=1;rsc_state(gm);
    assert(!maps && reads==2 && refused==1 && !ok);
    fputs("PASS: read-only bounded census, reset gates and map-failure exits\n",stderr);
}
'''
out=root/'out/lmi-gpu-rsc-state-host';out.mkdir(exist_ok=True)
(out/'check.c').write_text(prefix+code+suffix)
subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',
                str(out/'check.c'),'-o',str(out/'check')],check=True)
log=subprocess.check_output([str(out/'check')],text=True)
result=decoder['verify'](log)
assert len(result['registers'])==56 and not result['rsc_sequence_matches_vendor']
assert not result['qmp']['valid_magic_version']
for broken in [log.replace('LMI_GPU_RSC_STATE_OK\n',''),
               log.replace('0000000003d91000','0000000003d91004',1),
               log.replace('0000000003d91000','ffffffffffffffff',2),
               log.replace('LMI_GPU_RSC_STATE_BEGIN\n','LMI_GPU_RSC_STATE_RESET_REFUSED\n'),
               log.replace('LMI_GPU_RSC_STATE_BANK\n','',1)]:
    try:decoder['verify'](broken)
    except AssertionError:pass
    else:raise AssertionError('Corrupt census accepted')
(out/'host-census.log').write_text(log)
print('PASS: decoder rejects incomplete, reordered, wide and refused evidence')
