"""Exercise the actual bus-scope caller with simulated MMIO, ASan/UBSan.
Only the AArch64 barrier is replaced by a host compiler barrier. Request
implementation has its own tests; here we test bus ownership and retention.
"""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
s=(root/'tools/lmi-gpu-probe.c').read_text()
def function(start, end):
    return s[s.index(start):s.index(end,s.index(start))]
code=function('static int rpmh_probe(void)', '\n#endif\nstatic int smmu_readonly')+'\n'+function('static int smmu_readonly(u32 mode)', '\n#if !defined(LMI_GPU_CONTEXT_PROBE)')
code=code.replace('__asm__ volatile("dsb sy":::"memory");','__asm__ volatile("":::"memory");')
prefix=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef unsigned int u32;
typedef unsigned long long u64;
#define LMI_GPU_RPMH_BUS_PROBE
#define REFUSED(label,reason) log_line(label)
static u32 gcc[0x80000/4], request_result, requests, maps, missing, halted;
static u64 io_map(u64 pa,u64 bytes) {
    if(pa==0x100000) {assert(bytes==sizeof(gcc));return missing?0:(u64)gcc;}
    if(pa==0x3de0000) {assert(bytes==0x10000);return 0x1234;}
    assert(pa==0x3da0000 && bytes==0x10000);maps++;return 0;
}
static int clock_on(u32 v) {return !(v&(1u<<31)) || (v&0xf0000000u)==0x20000000u;}
static u32 smmu_rd32(volatile u32 *p) {return *p;}
static void cb0_format_probe(volatile u32 *p) {(void)p;assert(0);}
static void log_line(const char *s) {(void)s;}
static void field(const char *s,u64 v) {(void)s;(void)v;}
static void delay(u32 a,u32 b) {
    (void)a;assert(b==1000);
    if(!(gcc[0x71018/4]&1))gcc[0x71018/4]|=1u<<31;
    if(!halted && (gcc[0x71018/4]&1))gcc[0x71018/4]&=~(1u<<31);
}
int lmi_gpu_arc_min_votes(volatile u32 *r) {
    assert((u64)r==0x1234);
    assert((gcc[0x7100c/4]&1) && (gcc[0x71018/4]&1));
    assert(clock_on(gcc[0x7100c/4]) && clock_on(gcc[0x71018/4]));
    requests++;return request_result;
}
'''
suffix=r'''
static void seed(void) {
    memset(gcc,0,sizeof(gcc));gcc[0x7100c/4]=0x20000000;
    gcc[0x71018/4]=0x80000000;
    requests=maps=missing=halted=0;request_result=1;
}
int main(void) {
    seed();assert(smmu_readonly(19)==0 && requests==1 && maps==1);
    assert(gcc[0x7100c/4]==0x20000000 && gcc[0x71018/4]==0x80000000);
    seed();request_result=4;assert(smmu_readonly(19)==2 && requests==1 && maps==0);
    assert(gcc[0x7100c/4]==0x20000001 && gcc[0x71018/4]==1);
    seed();request_result=0;assert(smmu_readonly(19)==0 && requests==1);
    assert(!(gcc[0x7100c/4]&1) && !(gcc[0x71018/4]&1));
    seed();gcc[0x7100c/4]|=1;gcc[0x71018/4]=1;
    assert(smmu_readonly(19)==0 && gcc[0x7100c/4]==0x20000001 && gcc[0x71018/4]==1);
    seed();halted=1;assert(smmu_readonly(19)==0 && !requests && !maps);
    seed();missing=1;assert(smmu_readonly(19)==0 && !requests && !maps);
    puts("PASS: bus clocks precede requests; pending retains both; completed/refused restore only owned votes; unavailable bus refuses");
}
'''
out=root/'out/lmi-gpu-bus-host';out.mkdir(exist_ok=True)
(out/'check.c').write_text(prefix+code+suffix)
subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'check.c'),'-o',str(out/'check')],check=True)
subprocess.run([str(out/'check')],check=True)
# The same bus scope protects mode22 initialization/restore failures.
init_prefix=prefix.replace('#define LMI_GPU_RPMH_BUS_PROBE','#define LMI_GPU_RSC_INIT')
init_prefix+=r'''
int lmi_gpu_rsc_init(void) {
    assert((gcc[0x7100c/4]&1) && (gcc[0x71018/4]&1));
    assert(clock_on(gcc[0x7100c/4]) && clock_on(gcc[0x71018/4]));
    requests++;return request_result;
}
'''
for mode in (22,23,24,25,26,27):
    init_suffix=suffix.replace('smmu_readonly(19)',f'smmu_readonly({mode})').replace('request_result=4','request_result=2')
    if mode==27:init_suffix=init_suffix.replace('maps==1','maps==0')
    defines='\n#define LMI_GPU_RSC_PDC_VOTE\n#define LMI_GPU_RPMH_BUS_PROBE\n' if mode>=25 else ''
    if mode==27:defines+='\n#define LMI_GPU_GMU_ROUTE\n'
    (out/'check-init.c').write_text(init_prefix+defines+code+init_suffix)
    subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'check-init.c'),'-o',str(out/'check-init')],check=True)
    subprocess.run([str(out/'check-init')],check=True)
