#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-resources.c"
#include "lmi-gpu-table-plan.c"
static unsigned char db[0x20000],original[0x20000];
static unsigned char fuses[0x3000];
static void put16(unsigned n,unsigned v) {db[n]=v;db[n+1]=v>>8;}
static void put32(unsigned n,unsigned v) {put16(n,v);put16(n+2,v>>16);}
static void seed(void) {
    memset(db,0,sizeof(db));put32(0,1);put32(4,0x0c0330db);
    put16(8,3);put16(10,0);put16(12,72);put16(14,3);
    const char *ids[]={"gfx.lvl","cx.lvl","mx.lvl"};
    unsigned levels[]={0,16,48,64,128,144,192,224,256,320,384};
    for(unsigned n=0;n<3;n++) {
        unsigned at=144+n*24;memcpy(db+at,ids[n],strlen(ids[n]));
        put32(at+16,0x30000+16*n);put16(at+20,32);put16(at+22,32*n);
        for(unsigned k=0;k<11;k++)put16(216+32*n+2*k,levels[k]);
    }
    put16(24,5);put16(26,168);put16(28,264);put16(30,4);
    const char *bus[]={"SH0","MC0","ACV","CN0"};
    for(unsigned n=0;n<4;n++) {unsigned at=312+24*n;memcpy(db+at,bus[n],3);put32(at+16,0x50000+4*n);}
    memcpy(original,db,sizeof(db));
}
u64 io_map_memory(u64 pa,u64 bytes) {assert(pa==0x80860000 && bytes==sizeof(db));return (u64)db;}
u64 io_map(u64 pa,u64 bytes) {assert(pa==0x784000 && bytes==sizeof(fuses));return (u64)fuses;}
void log_line(const char *s) {fputs(s,stdout);}
void log_hex(u64 v) {printf("%016llx\n",v);}
int main(void) {
    struct lmi_gpu_perf_table t,sentinel;seed();assert(lmi_gpu_prepare_perf(db,sizeof(db),&t));
    unsigned indices[]={0,3,4,5,6,7,8,9},levels[]={0,64,128,144,192,224,256,320};
    assert(t.gx_count==8 && t.cx_count==2 && !t.hdr);
    for(unsigned n=0;n<8;n++)assert(t.gx[n][0]==((levels[n]<<16)|(indices[n]<<8)|indices[n]) && t.gx[n][1]==0xffffffff);
    assert(t.cx[0][0]==0 && t.cx[1][0]==0x300202 && t.cx[1][1]==200000);
    for(unsigned n=8;n<16;n++)for(unsigned k=0;k<3;k++)assert(!t.gx[n][k]);
    assert(!memcmp(db,original,sizeof(db)) && lmi_gpu_table_plan());
    fuses[0x19b]=32;assert(!lmi_gpu_table_plan());fuses[0x19b]=0;
    assert(lmi_gpu_bcm_address(db,sizeof(db),"SH0\0\0\0\0")==0x50000);
    seed();put32(328,0x40000);assert(!lmi_gpu_bcm_address(db,sizeof(db),"SH0\0\0\0\0"));
    seed();memcpy(db+336,db+312,24);assert(!lmi_gpu_bcm_address(db,sizeof(db),"SH0\0\0\0\0"));
    memset(&sentinel,0xa5,sizeof(sentinel));
    for(unsigned n=0;n<4;n++) {
        seed();t=sentinel;
        if(n==0)db[144]^=1;
        if(n==1)put16(216+9*2,0),put16(216+10*2,0);
        if(n==2)put32(160,0x30010);
        if(n==3)put16(216+4*2,63);
        assert(!lmi_gpu_prepare_perf(db,sizeof(db),&t) && !memcmp(&t,&sentinel,sizeof(t)));
    }
    seed();/* Vendor allows MX clamping to its top selector. */
    for(unsigned n=5;n<11;n++)put16(216+64+2*n,0);
    assert(lmi_gpu_prepare_perf(db,sizeof(db),&t) && (t.gx[7][0]&0xff00)==0x400);
    puts("PASS: source-defined performance ABI, OPPs, ARC dependencies, bounds, atomic refusal and read-only DB");
}
