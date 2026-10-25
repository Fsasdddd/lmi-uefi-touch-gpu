#include <assert.h>
#include <stdio.h>
#define LMI_GPU_SCM_HOST
#include "lmi-gpu-scm.c"
static u32 scenario,calls,query_count,resumed,verbose;
void log_line(const char *s) {if(verbose)fputs(s,stdout);}
void log_hex(u64 n) {if(verbose)printf("%016llx\n",n);}
void scm_step(u64 function,u64 query,u64 session,u64 *out) {
    const u32 expected[]={0x42000601,0x02000201,0x02000202,0x02000205,0x02000206};
    assert(query_count<5 && query==expected[query_count]);calls++;
    if(function==1) {assert(session==0x60000000ull+resumed && resumed);}
    else {assert(function==(query_count?0x42000601:0xc2000601) && !session && !resumed);}
    if(scenario==1 || (scenario==2 && resumed<2)) {
        out[0]=1;out[1]=~0ull;out[2]=0x60000000ull+(++resumed);return;
    }
    out[0]=scenario==3?~11ull:0;
    out[1]=scenario==query_count+10?0:1;
    out[2]=0;query_count++;resumed=0;
}
static void seed(u32 n) {scenario=n;calls=query_count=resumed=0;}
int main(void) {
    seed(0);verbose=1;assert(lmi_gpu_scm_available() && calls==5 && query_count==5);verbose=0;
    seed(1);assert(!lmi_gpu_scm_available() && calls==64 && !query_count);
    seed(2);assert(lmi_gpu_scm_available() && calls==15 && query_count==5);
    seed(3);assert(!lmi_gpu_scm_available() && calls==1);
    for(u32 i=0;i<5;i++) {seed(10+i);assert(!lmi_gpu_scm_available() && calls==i+1 && query_count==i+1);}
    puts("PASS: only convention/PIL availability queries, exact replies, A6 resume state and bounded interrupted/error/unavailable handling");
}
