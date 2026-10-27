"""Exercise the real v64 backend with independently scheduled DMA and TS events.

CPU/device ring and scratch are separate. Parsing ahead never completes a BO;
only a published CACHE_FLUSH_TS does. This does not emulate GPU performance.
"""
from pathlib import Path
import hashlib,json,re,subprocess

root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-gpu-queue-v64-host';out.mkdir(exist_ok=True)
prefix=(root/'tools/check-lmi-gpu-desktop.c').read_text().split('int main(void) {',1)[0]
prefix=prefix.replace('#include "lmi-gpu-desktop.c"','#include "lmi-gpu-desktop-v64.c"')
prefix=prefix.replace('static u32 sleeping,pending_end,complete_at;',r'''
static u32 sleeping,pending_end,complete_at;
static u32 ends[8],head,tail,automatic,finish_after,barrier_count,range_handoffs;
static u32 deferred_ts,oldest_reads;
static u64 scratch_invalidates;
void lmi_display_smp_prepare(void) {}
void lmi_gpu_publish_barrier(void) {barrier_count++;}
static void finish_one(void);
''')
prefix=prefix.replace('maps++;p->tables[0].changed=1;',
    'assert(head==tail);maps++;p->tables[0].changed=1;')
prefix=prefix.replace('cache_calls++;','cache_calls++;\n    if(p==(u64)pool+65536+64 && n==64 && !publish)scratch_invalidates++;')
prefix=prefix.replace('} else assert(p==(u64)&storage && n==sizeof(storage));',
    '} else {assert(p==(u64)&storage && n==sizeof(storage));assert(head==tail);range_handoffs++;}')
a=prefix.index('u32 rsc_read(');b=prefix.index('/* Decode the DMA-visible',a)
prefix=prefix[:a]+r'''
u32 rsc_read(volatile u32 *p) {
    if(test==4 && p==gpu+0xb604)return *p^1;
    if(p==gpu+0x806 && finish_after && ++oldest_reads>=finish_after && head!=tail) {
        finish_one();oldest_reads=0;
    }
    return *p;
}
'''+prefix[b:]
a=prefix.index('void rsc_write(');b=prefix.index('void delay(',a)
prefix=prefix[:a]+r'''
static void finish_one(void) {
    assert(head!=tail);execute(ends[head++&7]);pending_end=head!=tail;
}
void rsc_write(volatile u32 *p,u32 v) {
    if(p==gpu+0x807) {
        assert(!memcmp(pool,dma,32768));queued++;*p=v;
        if(queued==1){execute(v);return;}
        assert(tail-head<4);ends[tail++&7]=v;pending_end=1;
        if(automatic)finish_one();
        return;
    }
    if(p==s+0x9610/4) {assert(v==2 && maps && !desktop_space.tables[0].changed && head==tail);tlbis++;}
    else if(p==s+0x97f0/4) {assert(!v && tlbis);syncs++;}
    else {int found=0;for(u32 i=0;i<sizeof(nc)/sizeof(nc[0]);i++)if(p==gpu+nc[i][0] && v==nc[i][1])found=1;assert(found);}
    *p=v;
}
'''+prefix[b:]
prefix=prefix.replace('counter=sleeping=pending_end=complete_at=0;',
    'counter=sleeping=pending_end=complete_at=0;head=tail=finish_after=barrier_count=range_handoffs=deferred_ts=oldest_reads=0;automatic=1;scratch_invalidates=0;')
prefix=prefix.replace('if(expect_hold && storage.failed)longjmp(held,1);',
    'if(storage.failed){assert(expect_hold);longjmp(held,1);}')
main=r'''
static u64 addr[128];static u32 sizes[128];static unsigned scenarios;
static void init(void) {
    seed(0);assert(start());automatic=0;
    for(unsigned i=0;i<128;i++){addr[i]=0x20000000+4096*i;sizes[i]=256;}
}
static void four(void) {
    for(unsigned i=1;i<=4;i++) {
        unsigned before=sleeping;lmi_desktop_to_memory(NULL,0);
        assert(lmi_desktop_submit(addr,sizes,128)==i && !storage.done && sleeping==before);
    }
    assert(storage.peak==4 && storage.overlaps==3 && tail-head==4 && barrier_count==4);
}
static void held_operation(unsigned op) {
    expect_hold=1;
    if(!setjmp(held)) {
        if(op==0)lmi_desktop_to_memory(&storage,sizeof(storage));
        if(op==1)lmi_desktop_map(addr[0],g_phys_base,0);
        if(op==2)lmi_desktop_unmap(addr[0],4096);
        if(op==3)lmi_desktop_mapped();
        if(op==4)lmi_desktop_stop();
        if(op==5)lmi_desktop_to_memory(NULL,0);
        assert(!"uncertain DMA released memory");
    }
    assert(storage.failed && !storage.done && head!=tail);
}
int main(void) {
    for(u32 t=0;t<=15;t++) {
        seed(t);
        if(t==5)desktop_space.table_count=1;if(t==6)s[0x9024/4]^=0x10000;
        if(t==7)((u64 *)(pool+19*4096))[16]^=128;if(t==8)((u64 *)(pool+18*4096))[9]=3;
        if(t==9)((u32 *)(dma+65536))[16]=1;if(t==10)gpu[0x806]=67;
        if(t==11)desktop_slot[1]=1;if(t==12)desktop_space.tables[1023].changed=1;
        if(t==13)((u32 *)pool)[68]=1;if(t==14)desktop_free_count=1;if(t==15)desktop_space.control=0;
        assert(start()==(t==0));scenarios++;
    }
    init();four();
    assert(!lmi_desktop_done(1) && !storage.done);scenarios++;
    /* Completing the oldest job retires it while all three later jobs run. */
    for(unsigned i=1;i<=4;i++) {
        finish_one();assert(lmi_desktop_done(i) && storage.done==i);
        assert(!lmi_desktop_done(i+1) && tail-head==4-i);
    }
    assert(!memcmp(pool+65536+64,dma+65536+64,64));scenarios++;
    init();four();finish_after=4;
    assert(lmi_desktop_submit(addr,sizes,1)==5 && storage.done==1 && tail-head==4 && storage.queue_waits==1);
    assert(storage.peak==4 && storage.overlaps==4);scenarios++;
    /* RPTR can parse ahead without the TS event having completed. */
    init();assert(lmi_desktop_submit(addr,sizes,1)==1);
    execute(ends[head++&7]);deferred_ts=((u32 *)(dma+65536))[16];
    ((u32 *)(dma+65536))[16]=0;gpu[0x210]=2;pending_end=0;
    assert(!lmi_desktop_done(1) && !storage.done && !storage.failed);
    ((u32 *)(dma+65536))[16]=deferred_ts;gpu[0x210]=1;
    assert(lmi_desktop_done(1));scenarios++;
    /* CPU's cached scratch is not completion until the DMA copy says so. */
    init();assert(lmi_desktop_submit(addr,sizes,1)==1);
    ((u32 *)(pool+65536))[16]=1;assert(!lmi_desktop_done(1) && !storage.done);scenarios++;
    /* Native real cache ranges / page changes still drain every queued job. */
    for(unsigned op=0;op<5;op++) {
        init();four();finish_after=32;
        if(op==0)lmi_desktop_to_memory(&storage,sizeof(storage));
        if(op==1){assert(lmi_desktop_map(addr[0],g_phys_base,0));lmi_desktop_mapped();}
        if(op==2)lmi_desktop_unmap(addr[0],4096);
        if(op==3)lmi_desktop_mapped();
        if(op==4)lmi_desktop_stop();
        assert(storage.done==4 && head==tail && sleeping);scenarios++;
    }
    /* No parsing of overwritten data across repeated maximum-size wrap. */
    init();
    for(unsigned round=0;round<100;round++) {
        for(unsigned j=1;j<=4;j++)assert(lmi_desktop_submit(addr,sizes,128)==round*4+j);
        for(unsigned j=1;j<=4;j++){finish_one();assert(lmi_desktop_done(round*4+j));}
    }
    assert(storage.at==(72+400*522)%8192 && decoded==1+400*132 && storage.peak==4);scenarios++;
    /* Cached completion does not authorize overwriting unconsumed ring words. */
    init();assert(lmi_desktop_submit(addr,sizes,1)==1);
    gpu[0x806]=(storage.at+5)&8191;((u32 *)(dma+65536))[16]=1;
    assert(!lmi_desktop_submit(addr,sizes,128) && storage.failed && tail-head==1);scenarios++;
    init();four();unsigned submissions=queued;
    assert(!lmi_desktop_submit(addr,sizes,1) && storage.failed && queued==submissions && tail-head==4);scenarios++;
    for(unsigned fault=0;fault<9;fault++) {
        init();four();
        if(fault==0)s[0x9058/4]=0;if(fault==1)s[0x48/4]=1;
        if(fault==2)gpu[0x821]=1;if(fault==3)gpu[0x823]=1;
        if(fault==4)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
        if(fault==5)test=3;
        if(fault==6)((u32 *)(dma+65536))[16]=5;
        if(fault==7){finish_one();assert(lmi_desktop_done(1));((u32 *)(dma+65536))[16]=0;}
        if(fault==8){while(head!=tail)finish_one();((u32 *)(dma+65536))[16]=3;}
        assert(!lmi_desktop_done(fault==7?2:1) && storage.failed);
        assert(!lmi_desktop_submit(addr,sizes,1));scenarios++;
    }
    for(unsigned op=0;op<6;op++) {init();four();if(op==5)storage.failed=1;held_operation(op);scenarios++;}
    init();test=19;assert(!lmi_desktop_submit(addr,sizes,1) && storage.failed && !storage.fence && tail==head);scenarios++;
    init();storage.fence=storage.done=0xffffffffu;((u32 *)(dma+65536))[16]=0xffffffffu;
    assert(!lmi_desktop_submit(addr,sizes,1) && storage.failed && tail==head);scenarios++;
    init();assert(!lmi_desktop_submit(addr,sizes,0));sizes[0]=0;assert(!lmi_desktop_submit(addr,sizes,1));scenarios++;
    init();for(unsigned i=0;i<2744;i++)assert(lmi_desktop_map(addr[0]+4096ull*i,g_phys_base,0));
    assert(storage.mapping && storage.map_batches==1 && storage.map_pages==2744);
    assert(!lmi_desktop_submit(addr,sizes,1));lmi_desktop_mapped();assert(!storage.mapping);scenarios++;
    init();assert(lmi_desktop_map(addr[0],g_phys_base,0));expect_hold=1;
    if(!setjmp(held)){lmi_desktop_to_memory(NULL,0);assert(!"open mapping crossed barrier");}
    assert(storage.failed && storage.mapping);scenarios++;
    init();lmi_gpu_async_return();assert(storage.failed==2 && !storage.done);scenarios++;
    printf("PASS: %u scenarios; four real jobs, partial TS retirement, RPTR ownership, bounded faults, cache/map drains\n",scenarios);
}
'''
source=prefix+main
flags=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
       '-fno-sanitize-recover=all','-I',str(root/'tools')]
check=out/'check.c';check.write_text(source)
subprocess.run([*flags,str(check),'-o',str(out/'check')],check=True)
p=subprocess.run([str(out/'check')],capture_output=True,text=True,timeout=30)
(out/'host.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr,end='');p.check_returncode()
mutations={
    'fabricated_completion':('d->done=completed;return 1;','d->done=d->fence;return 1;'),
    'scratch_not_invalidated':('!cache_sync((u64)scratch,64,0)','0'),
    'fifth_job_admitted':('d->fence-d->done<4','d->fence-d->done<5'),
    'rptr_space_ignored':('((read-d->at-1)&8191)>=need','(need>0)'),
    'empty_barrier_still_serializes':('d->barriers++;return;','if(!drain(d))hold(d);d->barriers++;return;'),
    'real_range_skips_drain':('!drain(d) || !cache_sync((u64)p','!cache_sync((u64)p'),
    'regression_admitted':('completed<d->done || ','')}
raw=(root/'tools/lmi-gpu-desktop-v64.c').read_text();caught=[]
for name,(old,new) in mutations.items():
    assert raw.count(old)==1,(name,old)
    candidate=out/(name+'.c');candidate.write_text(raw.replace(old,new))
    path=out/(name+'-check.c');path.write_text(source.replace('#include "lmi-gpu-desktop-v64.c"',f'#include "{candidate}"'))
    binary=out/(name+'-check');subprocess.run([*flags,str(path),'-o',str(binary)],check=True)
    result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
    (out/(name+'.log')).write_text(result.stdout+result.stderr)
    assert result.returncode!=0,('Mutation survived',name);caught.append(name)
names=['check-lmi-gpu-queue-v64.py','lmi-gpu-desktop-v64.c','check-lmi-gpu-desktop.c','lmi-gpu-boot-regs.h']
report=dict(result='PASS',scenarios=int(re.search(r'PASS: (\d+) scenarios',p.stdout)[1]),
    asan_ubsan=True,mutations_caught=caught,max_inflight=4,cpu_device_memory_separate=True,
    independently_decoded_packets=True,ring_wrap_submissions=400,
    actual_backend_used=True,hardware_tested=False,performance_verified=False,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names},
    generated_source_sha256=hashlib.sha256(check.read_bytes()).hexdigest())
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('Mutation checks:',len(caught))
