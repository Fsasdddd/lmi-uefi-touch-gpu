"""Exercise delayed DMA against v58, with a separate CPU/device cache model."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-gpu-async-v58-host';out.mkdir(exist_ok=True)
prefix=(root/'tools/check-lmi-gpu-desktop.c').read_text().split('int main(void) {',1)[0]
prefix=prefix.replace('#include "lmi-gpu-desktop.c"','#include "lmi-gpu-desktop-v58.c"')
prefix=prefix.replace('static u32 sleeping,pending_end,complete_at;',
    'static u32 sleeping,pending_end,complete_at;\nvoid lmi_display_smp_prepare(void) {}')
prefix=prefix.replace('maps++;p->tables[0].changed=1;',
    'assert(gpu[0x806]==gpu[0x807] && !pending_end);maps++;p->tables[0].changed=1;')
prefix=prefix.replace('} else assert(p==(u64)&storage && n==sizeof(storage));',
    '} else {assert(p==(u64)&storage && n==sizeof(storage));assert(gpu[0x806]==gpu[0x807] && !pending_end);}')
prefix=prefix.replace('if(test==33 && p==gpu+0x806 && pending_end && counter>=complete_at)',
    'if((test==33 || test==34) && p==gpu+0x806 && pending_end && counter>=complete_at)')
prefix=prefix.replace('u32 previous=gpu[0x806];execute(v);',
    'u32 previous=gpu[0x806];execute(v);')
# Device commands execute into DMA scratch, but completion can be delayed. For
# test34 also keep scratch stale until the host explicitly publishes it.
prefix=prefix.replace('if(test==33) {pending_end=v;gpu[0x806]=previous;}',
    'if(test==33 || test==34) {pending_end=v;gpu[0x806]=previous; if(test==34)((u32 *)(dma+65536))[16]=0;}')
main=r'''
static u64 addr[128];static u32 sizes[128];static unsigned scenarios;
static void init(void) {seed(0);assert(start());for(unsigned i=0;i<128;i++){addr[i]=0x20000000+4096*i;sizes[i]=256;}}
static void held_operation(unsigned which) {
    expect_hold=1;
    if(!setjmp(held)) {
        if(which==0)lmi_desktop_to_memory(&storage,sizeof(storage));
        else if(which==1)lmi_desktop_map(addr[0],g_phys_base,0);
        else if(which==2)lmi_desktop_unmap(addr[0],4096);
        else if(which==3)lmi_desktop_mapped();
        else lmi_desktop_stop();
        assert(!"uncertain DMA returned to a memory-changing caller");
    }
    assert(storage.failed && !lmi_desktop_done(1));
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
    init();
    for(unsigned i=1;i<=40;i++) {
        assert(lmi_desktop_submit(addr,sizes,128)==i);
        assert(storage.done==i-1); /* queued is not completed */
        assert(!lmi_desktop_done(i+1) && lmi_desktop_done(i));
    }
    assert(storage.at==(72+40*522)%8192 && queued==41 && decoded==1+40*132);scenarios++;
    init();test=33;complete_at=76800;
    assert(lmi_desktop_submit(addr,sizes,1)==1 && storage.done==0 && !sleeping);
    unsigned calls=cache_calls;u64 began=counter;
    assert(!lmi_desktop_done(1) && cache_calls==calls && counter==began && !sleeping);
    counter=complete_at;
    assert(lmi_desktop_done(1) && storage.done==1 && !sleeping);scenarios++;
    /* An idle ring without its expected device fence never releases backing. */
    init();test=34;complete_at=0;assert(lmi_desktop_submit(addr,sizes,1)==1);
    assert(!lmi_desktop_done(1) && storage.failed && !storage.done);scenarios++;
    /* Scratch that looks complete, with a still-active ring, is insufficient. */
    init();test=33;complete_at=76800;assert(lmi_desktop_submit(addr,sizes,1)==1);
    assert(((u32 *)(dma+65536))[16]==1 && !lmi_desktop_done(1));scenarios++;
    /* Reusing the ring waits for the previous job and retires its real fence. */
    init();test=33;complete_at=76800;assert(lmi_desktop_submit(addr,sizes,1)==1);
    assert(lmi_desktop_submit(addr,sizes,1)==2 && storage.done==1 && sleeping);
    assert(lmi_desktop_done(2));scenarios++;
    for(unsigned op=0;op<5;op++) {
        init();test=33;complete_at=76800;assert(lmi_desktop_submit(addr,sizes,1)==1);
        if(op==0)lmi_desktop_to_memory(&storage,sizeof(storage));
        if(op==1)assert(lmi_desktop_map(addr[0],g_phys_base,0));
        if(op==2)lmi_desktop_unmap(addr[0],4096);
        if(op==3)lmi_desktop_mapped();
        if(op==4)lmi_desktop_stop();
        assert(storage.done==1 && !pending_end && sleeping);scenarios++;
    }
    for(unsigned fault=0;fault<6;fault++) {
        init();test=23;assert(lmi_desktop_submit(addr,sizes,1)==1);
        if(fault==0)s[0x9058/4]=0;if(fault==1)s[0x48/4]=1;
        if(fault==2)gpu[0x821]=1;if(fault==3)gpu[0x823]=1;
        if(fault==4)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
        if(fault==5)test=20; /* failed invalidation after genuine ring completion */
        if(fault==5){test=0;execute(storage.at);test=20;}
        assert(!lmi_desktop_done(1) && storage.failed && !storage.done);
        assert(!lmi_desktop_submit(addr,sizes,1));scenarios++;
    }
    for(unsigned op=0;op<5;op++) {init();test=23;assert(lmi_desktop_submit(addr,sizes,1)==1);held_operation(op);scenarios++;}
    init();test=19;assert(!lmi_desktop_submit(addr,sizes,1) && storage.failed && !storage.fence);scenarios++;
    init();storage.fence=storage.done=0xffffffffu;
    ((u32 *)(dma+65536))[16]=0xffffffffu;
    assert(!lmi_desktop_submit(addr,sizes,1) && storage.failed);scenarios++;
    init();assert(!lmi_desktop_submit(addr,sizes,0));sizes[0]=0;assert(!lmi_desktop_submit(addr,sizes,1));scenarios++;
    init();lmi_gpu_async_return();assert(storage.failed);scenarios++;
    printf("PASS: %u scenarios, delayed DMA, ring wrap, real fence, cache/map/stop drains, retained failures\n",scenarios);
}
'''
source=out/'check.c';source.write_text(prefix+main)
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
    '-I',str(root/'tools'),str(source),'-o',str(out/'check')],check=True)
p=subprocess.run([str(out/'check')],capture_output=True,text=True)
(out/'host.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr);p.check_returncode()
names=['check-lmi-gpu-async-v58.py','lmi-gpu-desktop-v58.c','check-lmi-gpu-desktop.c','lmi-gpu-boot-regs.h']
report=dict(result='PASS',sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names},
    asan_ubsan=True,hardware_tested=False,scenarios=int(p.stdout.split()[1]))
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
