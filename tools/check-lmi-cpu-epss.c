#include "lmi-cpu-epss.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct model {
    struct lmi_epss_state state;
    uint32_t table[3][40],request[3],original[3];
    unsigned op,fail,failed,writes,barriers,last_barrier,after_write,write_on_failure;
    unsigned restore_failure,corrupt_read;
};
static uint32_t row(uint32_t freq,uint32_t count)
{assert(freq%19200==0 && freq/19200<256);return (1u<<30)|(count<<16)|freq/19200;}
static int fault(struct model *m) {return ++m->op==m->fail?(m->failed=1):0;}
static unsigned index(uintptr_t base)
{assert(base>=0x10000 && base<0x13000 && (base&0xfff)==0);return (base-0x10000)/0x1000;}
static uintptr_t map(void *ctx,uint32_t phys,uint32_t bytes)
{
    struct model *m=ctx;assert(bytes==4096 && phys>=LMI_EPSS_BASE && phys<LMI_EPSS_BASE+3*4096 && (phys&4095)==0);
    if(fault(m))return 0;
    return 0x10000+(phys-LMI_EPSS_BASE);
}
static int read32(void *ctx,uintptr_t base,uint32_t offset,uint32_t *value)
{
    struct model *m=ctx;unsigned i=index(base);
    assert(offset==LMI_EPSS_PERF || (offset>=LMI_EPSS_LUT && offset<LMI_EPSS_LUT+40*4 && !(offset&3)));
    if(fault(m))return 0;
    if(offset==LMI_EPSS_PERF) {
        if(m->after_write) {assert(m->barriers>m->after_write);m->after_write=0;}
        *value=m->request[i];
        if(m->corrupt_read && m->state.dirty && m->request[i]!=m->original[i]) {*value^=1;m->corrupt_read=0;}
    } else *value=m->table[i][(offset-LMI_EPSS_LUT)/4];
    return 1;
}
static int write32(void *ctx,uintptr_t base,uint32_t offset,uint32_t value)
{
    struct model *m=ctx;unsigned i=index(base);assert(offset==LMI_EPSS_PERF);
    assert(m->state.prepared && (m->state.dirty&(1u<<i)));
    assert(m->barriers && m->barriers>m->last_barrier);m->last_barrier=m->barriers;
    int fail=fault(m);m->writes++;m->after_write=m->barriers;
    if(m->restore_failure && value==m->original[i])return 0;
    if(!fail || m->write_on_failure)m->request[i]=value;
    return !fail;
}
static void barrier(void *ctx) {((struct model *)ctx)->barriers++;}
static void init(struct model *m)
{
    memset(m,0,sizeof(*m));
    uint32_t top[]={1804800,2419200,2841600};
    for(unsigned i=0;i<3;i++) {
        m->table[i][0]=4u<<16; /* source0 ignores low multiplier bits */
        m->table[i][1]=row(960000,4);
        m->table[i][2]=row(top[i],4);
        /* Above cap plus a single-core boost tail must never be chosen. */
        m->table[i][3]=row(top[i]+19200,4);
        m->table[i][4]=m->table[i][5]=row(top[i]+38400,1);
        m->original[i]=m->request[i]=0;
    }
}
static struct lmi_epss_io io(struct model *m)
{return (struct lmi_epss_io){m,map,read32,write32,barrier};}
static void restored(struct model *m)
{assert(m->state.dirty==0);for(unsigned i=0;i<3;i++)assert(m->request[i]==m->original[i]);}
static void normal(struct model *m)
{
    struct lmi_epss_io ops=io(m);assert(lmi_epss_prepare(&m->state,&ops));
    assert(lmi_epss_apply(&m->state));assert(m->state.changed==7 && m->state.dirty==7);
    for(unsigned i=0;i<3;i++)assert(m->request[i]==2 && m->state.domain[i].target==2);
    assert(lmi_epss_restore(&m->state));restored(m);
}
int main(void)
{
    struct model m;init(&m);normal(&m);unsigned operations=m.op,scenarios=1;
    /* Source0, same-frequency/different-core-count continuation, boost tail. */
    init(&m);struct lmi_epss_domain d={0};
    d.lut[0]=4u<<16|255u;d.lut[1]=row(960000,3);d.lut[2]=row(960000,4);
    d.lut[3]=row(1516800,4);d.lut[4]=d.lut[5]=row(1804800,1);
    assert(lmi_epss_select(&d,4,1804800) && d.rows==5 && d.target==3);scenarios++;
    /* Equal adjacent frequency/core counts ends even if later bytes look valid. */
    d=(struct lmi_epss_domain){0};d.lut[0]=row(960000,4);d.lut[1]=d.lut[0];d.lut[2]=row(1804800,4);
    assert(lmi_epss_select(&d,4,1804800) && d.rows==1 && d.target==0);scenarios++;
    /* Full table without terminator, no compatible row, zero multiplier. */
    d=(struct lmi_epss_domain){0};for(unsigned i=0;i<40;i++)d.lut[i]=row((i+1)*19200,4);
    assert(!lmi_epss_select(&d,4,1804800));scenarios++;
    d=(struct lmi_epss_domain){0};d.lut[0]=d.lut[1]=row(960000,3);
    assert(!lmi_epss_select(&d,4,1804800));scenarios++;
    d=(struct lmi_epss_domain){0};d.lut[0]=d.lut[1]=(1u<<30)|(4u<<16);
    assert(!lmi_epss_select(&d,4,1804800));scenarios++;
    /* Terminator at final row; unsorted valid frequencies select max by Hz. */
    d=(struct lmi_epss_domain){0};for(unsigned i=0;i<39;i++)d.lut[i]=row((40-i)*19200,4);
    d.lut[39]=d.lut[38];assert(lmi_epss_select(&d,4,1804800) && d.rows==39 && d.target==0);scenarios++;
    init(&m);d=(struct lmi_epss_domain){0};memcpy(d.lut,m.table[0],sizeof(d.lut));
    d.original=40;assert(!lmi_epss_select(&d,4,1804800));d.original=3;
    assert(!lmi_epss_select(&d,4,1804800));scenarios++;
    assert(!lmi_epss_select(0,4,1804800) && !lmi_epss_select(&d,0,1804800) && !lmi_epss_select(&d,8,1804800) && !lmi_epss_select(&d,4,0));scenarios++;
    assert(!lmi_epss_prepare(0,0) && !lmi_epss_apply(0) && !lmi_epss_restore(0));scenarios++;
    init(&m);struct lmi_epss_io ops=io(&m);ops.read=0;assert(!lmi_epss_prepare(&m.state,&ops));assert(!m.op && !m.writes);scenarios++;
    /* Idempotent restore, single-use apply, no write when already requested. */
    init(&m);for(unsigned i=0;i<3;i++)m.request[i]=m.original[i]=2;
    ops=io(&m);assert(lmi_epss_prepare(&m.state,&ops));assert(lmi_epss_apply(&m.state));assert(!m.writes && !m.state.changed);
    assert(lmi_epss_restore(&m.state));assert(!lmi_epss_apply(&m.state));scenarios++;
    init(&m);ops=io(&m);assert(!lmi_epss_apply(&m.state));assert(lmi_epss_prepare(&m.state,&ops));
    unsigned n=m.op;assert(!lmi_epss_prepare(&m.state,&ops) && m.op==n);scenarios++;
    /* A readback mismatch causes rollback; success is never fabricated. */
    init(&m);ops=io(&m);assert(lmi_epss_prepare(&m.state,&ops));m.corrupt_read=1;
    assert(!lmi_epss_apply(&m.state));restored(&m);scenarios++;
    /* Persistent restore failure keeps all dirty bits. Retry succeeds later. */
    init(&m);ops=io(&m);assert(lmi_epss_prepare(&m.state,&ops));assert(lmi_epss_apply(&m.state));
    m.restore_failure=1;assert(!lmi_epss_restore(&m.state) && m.state.dirty==7);
    m.restore_failure=0;assert(lmi_epss_restore(&m.state));restored(&m);n=m.op;
    assert(lmi_epss_restore(&m.state) && m.op==n);scenarios++;
    /* Every fallible map/read/write, including a failed write that reached
     * hardware. No preparation failure writes. All domains eventually recover. */
    for(unsigned writes_on_error=0;writes_on_error<2;writes_on_error++)
        for(unsigned fail=1;fail<=operations;fail++) {
            init(&m);m.fail=fail;m.write_on_failure=writes_on_error;ops=io(&m);
            if(lmi_epss_prepare(&m.state,&ops)) {
                int applied=lmi_epss_apply(&m.state);
                int done=lmi_epss_restore(&m.state);
                if(!done)assert(lmi_epss_restore(&m.state));
                assert(!applied || m.state.applied);
            } else assert(!m.writes && !m.state.dirty);
            assert(m.failed);restored(&m);scenarios++;
        }
    printf("PASS: %u scenarios; %u distinct fallible operations, two write-failure models\n",scenarios,operations);
    return 0;
}
