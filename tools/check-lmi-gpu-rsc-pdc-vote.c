/* Exercise both real transactions together, including an MX or CX timeout.
 * This host simulation proves ordering/retention, never physical completion. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define LMI_GPU_RSC_INIT_HOST
#define LMI_GPU_RSC_SEQUENCE
#define LMI_GPU_PDC_ENABLE
#define LMI_GPU_RSC_PDC_VOTE
#include "lmi-gpu-rsc-init.c"
#define LMI_GPU_RPMH_HOST
#define LMI_GPU_RSCC_SDE_PROBE
#define LMI_GPU_RPMH_INTERFACE_PROBE
#define LMI_GPU_RPMH_ARC_SLOT_PROBE
#include "lmi-gpu-rpmh.c"
static u32 r[0x4000],g[0xc000],p[0x4000],triggers,timeout_at,program_fault,restore_fault;
u64 io_map(u64 address,u64 bytes) {
    if(address==0x3de0000) {assert(bytes==sizeof(r));return (u64)r;}
    if(address==0x3d6a000) {assert(bytes==sizeof(g));return (u64)g;}
    assert(address==0xb290000 && bytes==sizeof(p));return (u64)p;
}
void log_line(const char *s) {(void)s;}
void log_hex(u64 value) {(void)value;}
void delay(u32 amount,u32 unit) {assert(amount<=100 && unit==1000);}
u32 rsc_read(volatile u32 *word) {return *word;}
void rsc_write(volatile u32 *word,u32 value) {
    int allowed=word==r+0x10/4 || word==p+0x4520/4 || word==p+0x4500/4;
    for(u32 n=0;n<5;n++)allowed|=word==r+(0x600+4*n)/4;
    assert(allowed);
    if(program_fault && word==r+0x600/4 && value)return;
    if(restore_fault && word==p+0x4500/4 && value==0x100)return;
    *word=value;
}
u32 vote_read(volatile u32 *word) {return *word;}
void vote_write(volatile u32 *word,u32 value) {
    if(word==g+0x143a0/4) {assert(value==0 || value==0xf11);*word=value;return;}
    if(word==r+0x10/4) {assert(value==0x1000000);*word=value;return;}
    if(word==r+0xd08/4) {assert(value==2);r[0xd04/4]&=~2u;return;}
    u32 off=(u32)(word-r)*4;
    assert(off==0xd00 || off==0xfb0 || off==0xfb4 || off==0xfbc ||
           off==0xfd0 || off==0xfd4 || off==0xfd8);
    *word=value;
    if(off!=0xfb4 || value!=0x1010000)return;
    assert(++triggers<=2 && p[0x4500/4]==0x80000001 && g[0x14000/4]==1);
    assert(r[0x34/4]==0x82204514 && r[0x48/4]==0);
    assert(r[0xfd4/4]==(triggers==1?0x30010:0x30000) && r[0xfd8/4]==2);
    for(u32 n=0;n<5;n++)assert(r[(0x600+4*n)/4]==requested[12+n]);
    if(triggers==timeout_at) {r[0xfb8/4]=0;r[0xfdc/4]=0x101;return;}
    r[0xd04/4]|=2;r[0xfdc/4]=0x10100;
}
int lmi_gpu_arc_min_votes(volatile u32 *rscc) {
    struct lmi_arc_resource cx={.address=0x30000,.count=9,.min_svs_index=2,.levels={0,16,64,128,192,256,320,384,416}};
    struct lmi_arc_resource mx={.address=0x30010,.count=9,.min_svs_index=2,.levels={0,16,128,192,224,256,320,384,416}};
    return lmi_gpu_rscc_min_votes(rscc,&cx,&mx);
}
static void seed(void) {
    memset(r,0,sizeof(r));memset(g,0,sizeof(g));memset(p,0,sizeof(p));
    r[3]=0x4000000a;g[0x14000/4]=1;
    for(u32 n=0;n<10;n++)r[(0xd18+n*0x2a0)/4]=1;
    for(u32 n=0;n<19;n++)(n<17?r:p)[offsets[n]/4]=expected[n];
    triggers=timeout_at=program_fault=restore_fault=0;
}
int main(void) {
    seed();assert(lmi_gpu_rsc_init()==1 && triggers==2);
    for(u32 n=0;n<19;n++)assert((n<17?r:p)[offsets[n]/4]==expected[n]);
    assert(!g[0x143a0/4] && !r[0xfb4/4] && !r[0xfbc/4] && !r[0xfb0/4]);
    for(u32 n=1;n<=2;n++) {
        seed();timeout_at=n;assert(lmi_gpu_rsc_init()==2 && triggers==n);
        assert(r[0x600/4]==0xeaaae5a0 && r[0x10/4]==0x1000000 && p[0x4500/4]==0x80000001);
        assert(g[0x143a0/4]==0xf11 && r[0xfb4/4]==0x1010000);
    }
    seed();program_fault=1;assert(lmi_gpu_rsc_init()==0 && !triggers && !r[0x10/4]);
    seed();restore_fault=1;assert(lmi_gpu_rsc_init()==2 && triggers==2 && p[0x4500/4]==0x80000001);
    seed();r[0x34/4]^=1;assert(lmi_gpu_rsc_init()==0 && !triggers);
    puts("PASS: real RSC/PDC and RPMh transactions preserve initialization through both requests; MX/CX timeouts retain every dependency");
}
