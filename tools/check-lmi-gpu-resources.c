#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-resources.c"
static unsigned char db[0x20000],original[0x20000];
static char output[8192];
static void put16(unsigned n,unsigned v) {db[n]=v;db[n+1]=v>>8;}
static void put32(unsigned n,unsigned v) {put16(n,v);put16(n+2,v>>16);}
static void seed(void) {
    memset(db,0,sizeof(db));put32(0,1);put32(4,0x0c0330db);
    put16(8,3);put16(10,0);put16(12,48);put16(14,2);
    memcpy(db+144,"cx.lvl",6);put32(160,0x30000);put16(164,32);
    memcpy(db+168,"mx.lvl",6);put32(184,0x30004);put16(188,32);put16(190,32);
    unsigned levels[]={0,16,48,64,128,256,384};
    for(int i=0;i<7;i++) {put16(192+2*i,levels[i]);put16(224+2*i,levels[i]);}
    memcpy(original,db,sizeof(db));output[0]=0;
}
arc_u64 io_map_memory(arc_u64 pa,arc_u64 bytes) {assert(pa==0x80860000 && bytes==sizeof(db));return (arc_u64)db;}
void log_line(const char *s) {assert(strlen(output)+strlen(s)<sizeof(output));strcat(output,s);}
void log_hex(arc_u64 v) {char s[32];snprintf(s,sizeof(s),"%016llx\n",v);log_line(s);}
int main(void) {
    struct lmi_arc_resource r,sentinel;
    seed();assert(lmi_gpu_arc_parse(db,sizeof(db),"cx.lvl\0",&r));
    assert(r.address==0x30000 && r.count==7 && r.min_svs_index==2 && r.levels[2]==48);
    assert(lmi_gpu_arc_inventory() && strstr(output,"LMI_GPU_ARC_INVENTORY_OK\n"));
    assert(!memcmp(db,original,sizeof(db)));
    memset(&sentinel,0xa5,sizeof(sentinel));
    for(int n=0;n<16;n++) {
        seed();r=sentinel;
        if(n==0)db[4]^=1;
        if(n==1)put16(14,513);
        if(n==2)put16(164,33);
        if(n==3)put16(164,3);
        if(n==4)put16(164,0);
        if(n==5)put32(160,0);
        if(n==6)put32(160,0x40000);
        if(n==7)put32(160,0x30001);
        if(n==8)put16(192,1);
        if(n==9)put16(196,16);
        if(n==10)put16(196,0);
        if(n==11)memcpy(db+168,"cx.lvl",6);
        if(n==12)memcpy(db+144,"missing",7);
        if(n==13)put16(12,0xfff0),put16(166,0xfff0);
        if(n==14)put16(164,2);
        if(n==15)put16(14,0);
        assert(!lmi_gpu_arc_parse(db,sizeof(db),"cx.lvl\0",&r));
        assert(!memcmp(&r,&sentinel,sizeof(r)));
    }
    seed();
    for(unsigned len=0;len<224;len++)assert(!lmi_gpu_arc_parse(db,len,"mx.lvl\0",&r));
    assert(!lmi_gpu_arc_parse(NULL,sizeof(db),"cx.lvl\0",&r));
    assert(!lmi_gpu_arc_parse(db,sizeof(db),NULL,&r));
    assert(!lmi_gpu_arc_parse(db,sizeof(db),"cx.lvl\0",NULL));
    unsigned random=0x754837;
    for(unsigned n=0;n<4096;n++) {
        seed();random=random*1664525+1013904223;
        unsigned offset=random%256;db[offset]^=(unsigned char)(random>>24);
        (void)lmi_gpu_arc_parse(db,random%513,"cx.lvl\0",&r);
    }
    puts("PASS: actual read-only ARC parser/inventory, selectors, malformed AUX and bound checks; no RPMh writes");
}
