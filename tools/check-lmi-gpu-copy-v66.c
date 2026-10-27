/* Appended to the frozen native backend fixture; probe is a separate TU. */
extern int lmi_gpu_copy_start(void);
static uint64_t recorded[6];
static unsigned emitted,copy_bells,copy_reads,probe_active,probe_fault;
static void execute_copy(void);
void *lmi_v66_state(void) {return probe_fault==1?NULL:state();}
int lmi_v66_drain(void *p) {return drain(p);}
_Noreturn void lmi_v66_hold(void *p) {hold(p);__builtin_unreachable();}
uint64_t lmi_v66_counter(void) {return lmi_gpu_counter();}
void lmi_v66_emit(const char *tag,const uint64_t *values,unsigned count)
{
    assert(!strcmp(tag,"LMI_CP_COPY") && count==6 && copy_bells==1 && !services);
    memcpy(recorded,values,sizeof(recorded));emitted++;
}
/* No production packet constants are imported. Decode odd parity, payload
 * lengths, GPU virtual intervals, ordering and fresh device-only markers. */
static void execute_copy(void)
{
    uint32_t *ring=(void *)dma;unsigned pos=72,stage=0;uint8_t pending[1020];
    while(pos<90) {
        uint32_t h=ring[pos++],n=h&0x3fff,op=(h>>16)&127,arg[5]={0};
        assert(h>>28==7 && ((h>>15)&1)==(1^__builtin_parity(n)) &&
               ((h>>23)&1)==(1^__builtin_parity(op)) && n<=5 && pos+n<=90);
        for(unsigned i=0;i<n;i++)arg[i]=ring[pos++];
        if(stage==0) {
            assert(op==0x75 && n==5 && arg[0]==255 && arg[1]==0x01010800 &&
                   !arg[2] && arg[3]==0x01010c00 && !arg[4]);
            memcpy(pending,dma+0x10800,sizeof(pending));
        } else if(stage==1) {
            assert(op==0x12 && n==0);
            if(probe_fault!=15)memcpy(dma+0x10c00,pending,sizeof(pending));
            if(probe_fault==16)dma[0x10d04]^=1;
            if(probe_fault==17)dma[0x10ffc]=1;
            if(probe_fault==18)dma[0x10800]^=1;
            if(probe_fault==19)dma[0x106fc]=1;
        } else if(stage==2 || stage==4)assert(op==0x26 && n==0);
        else if(stage==3) {
            assert(op==0x46 && n==4 && arg[0]==4 && arg[1]==0x01010600 && !arg[2] && arg[3]==0x660c0de6);
            if(probe_fault!=20)memcpy(dma+0x10600,arg+3,4);
        } else {
            assert(stage==5 && op==0x3d && n==3 && arg[0]==0x01010604 && !arg[1] && arg[2]==0x660c0de7);
            if(probe_fault!=21)memcpy(dma+0x10604,arg+2,4);
        }
        stage++;
    }
    assert(pos==90 && stage==6);gpu[0x806]=90;
}
static void init_probe(void)
{
    probe_active=probe_fault=0;seed(0);assert(start());assert(services==1);
    services=emitted=copy_bells=copy_reads=0;memset(recorded,0,sizeof(recorded));
    probe_active=1;
}
int main(void)
{
    unsigned scenarios=0;
    /* Successful copy with actual v64 bind/drain/progress and post-copy jobs. */
    init_probe();unsigned char before[sizeof(pool)];memcpy(before,dma,sizeof(before));
    assert(lmi_gpu_copy_start()==1 && services==1 && emitted==1 && copy_bells==1);
    assert(recorded[0]==1020 && recorded[1]==90 && recorded[2]==0x660c0de6 &&
           recorded[3]==0x660c0de7 && !recorded[4] && recorded[5]>0);
    assert(storage.at==90 && !storage.fence && !storage.done && !storage.failed);
    for(unsigned i=0;i<sizeof(pool);i++) {
        int changed=(i>=72*4 && i<90*4) || (i>=0x10600 && i<0x10608) ||
                    (i>=0x10800 && i<0x10bfc) || (i>=0x10c00 && i<0x10ffc);
        if(!changed)assert(dma[i]==before[i]);
    }
    uint64_t addresses[1]={0x20000000};uint32_t words[1]={16};
    for(unsigned i=1;i<=80;i++) {
        assert(lmi_desktop_submit((const u64 *)addresses,words,1)==i && lmi_desktop_done(i));
    }
    lmi_desktop_stop();assert(storage.failed==2);scenarios++;
    /* Invalid preconditions never publish a probe or a native service. */
    for(unsigned f=1;f<=13;f++) {
        init_probe();probe_fault=f;
        if(f==2)storage.ready=0;if(f==3)storage.failed=1;if(f==4)storage.mapping=1;
        if(f==5)storage.at=73;if(f==6)storage.fence=1;if(f==7)storage.done=1;
        if(f==8)s[0x9058/4]=0;
        if(f==10)dma[0x10600]=1;
        int result=lmi_gpu_copy_start();assert(!result && !copy_bells && !services && !emitted);scenarios++;
    }
    /* Device corruption and missing fresh markers cannot publish the service. */
    for(unsigned f=15;f<=21;f++) {
        init_probe();probe_fault=f;assert(!lmi_gpu_copy_start() && !services && emitted==1 && copy_bells==1);
        assert(recorded[4] || recorded[2]!=0x660c0de6 || recorded[3]!=0x660c0de7);scenarios++;
    }
    /* A post-DMA invalidation failure is refusal, never a cached success. */
    init_probe();probe_fault=14;assert(!lmi_gpu_copy_start() && copy_bells==1 && !services && !emitted);scenarios++;
    /* Real backend timeout/fault paths retain backing via hold(). */
    for(unsigned f=22;f<=23;f++) {
        init_probe();probe_fault=f;expect_hold=1;
        if(!setjmp(held)) {lmi_gpu_copy_start();assert(!"uncertain DMA released");}
        assert(storage.failed && !services && !emitted && copy_bells==1);scenarios++;
    }
    init_probe();probe_fault=24;assert(lmi_gpu_copy_start()==1 && copy_reads>=32 && sleeping && services==1);scenarios++;
    printf("PASS: %u scenarios; actual v64 backend, independent CP_MEMCPY decode, separate CPU/DMA, 80 subsequent jobs\n",scenarios);
}
