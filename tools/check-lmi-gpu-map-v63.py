"""Exercise the actual v63 backend, including native map-batch boundaries."""
from pathlib import Path
import ast,hashlib,json,re,subprocess

root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-gpu-map-v63-host';out.mkdir(exist_ok=True)
prior=root/'tools/check-lmi-gpu-async-v58.py'
tree=ast.parse(prior.read_text())
main=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and
          any(isinstance(t,ast.Name) and t.id=='main' for t in n.targets))
prefix=(root/'tools/check-lmi-gpu-desktop.c').read_text().split('int main(void) {',1)[0]
prefix=prefix.replace('#include "lmi-gpu-desktop.c"','#include "lmi-gpu-desktop-v63.c"')
prefix=prefix.replace('static u32 sleeping,pending_end,complete_at;',
    'static u32 sleeping,pending_end,complete_at;\nstatic u64 reads,scratch_invalidates;\nvoid lmi_display_smp_prepare(void) {}')
prefix=prefix.replace('maps++;p->tables[0].changed=1;',
    'assert(gpu[0x806]==gpu[0x807] && !pending_end);maps++;p->tables[0].changed=1;')
prefix=prefix.replace('} else assert(p==(u64)&storage && n==sizeof(storage));',
    '} else {assert(p==(u64)&storage && n==sizeof(storage));assert(gpu[0x806]==gpu[0x807] && !pending_end);}')
prefix=prefix.replace('if(test==33 && p==gpu+0x806 && pending_end && counter>=complete_at)',
    'if((test==33 || test==34) && p==gpu+0x806 && pending_end && counter>=complete_at)')
prefix=prefix.replace('if(test==33) {pending_end=v;gpu[0x806]=previous;}',
    'if(test==33 || test==34) {pending_end=v;gpu[0x806]=previous; if(test==34)((u32 *)(dma+65536))[16]=0;}')
prefix=prefix.replace('u32 rsc_read(volatile u32 *p) {','u32 rsc_read(volatile u32 *p) {\n    reads++;')
prefix=prefix.replace('cache_calls++;','cache_calls++;\n    if(p==(u64)pool+65536+64 && n==64 && !publish)scratch_invalidates++;')
extra=r'''
    /* A full 4608-pitch surface: 2744 pages, two real checks rather than
     * one check per page. No submitted fence is mistaken for completion. */
    init();reads=scratch_invalidates=0;
    for(unsigned i=0;i<2744;i++)assert(lmi_desktop_map(0x20000000ull+4096ull*i,g_phys_base,0));
    assert(storage.mapping && storage.map_batches==1 && storage.map_pages==2744);
    assert(reads==8 && scratch_invalidates==1);
    lmi_desktop_mapped();
    assert(!storage.mapping && reads==16 && scratch_invalidates==2 && !desktop_space.tables[0].changed);
    assert(lmi_desktop_map(addr[0],g_phys_base,1));lmi_desktop_mapped();
    assert(storage.map_batches==2 && storage.map_pages==2745 && reads==32);scenarios++;
    /* A busy prior submission must finish before even the first PTE write. */
    init();test=33;complete_at=76800;assert(lmi_desktop_submit(addr,sizes,1)==1);
    assert(lmi_desktop_map(addr[0],g_phys_base,0) && !pending_end && sleeping && storage.done==1);
    lmi_desktop_mapped();assert(!storage.mapping);scenarios++;
    /* Native newBuffer always calls mapped(), including partial failure,
     * before rollback/unmap. Check both the first and a later bad page. */
    for(unsigned first=0;first<2;first++) {
        init();
        if(!first)assert(lmi_desktop_map(addr[0],g_phys_base,0));
        assert(!lmi_desktop_map(addr[0]+1,g_phys_base,0));
        lmi_desktop_mapped();assert(!storage.mapping);
        lmi_desktop_unmap(addr[0],8192);assert(tlbis==1 && syncs==1);scenarios++;
    }
    init();test=25;assert(!lmi_desktop_map(addr[0],g_phys_base,0) && storage.mapping);
    test=0;lmi_desktop_mapped();lmi_desktop_unmap(addr[0],4096);assert(!storage.mapping);scenarios++;
    /* Faults arriving during a batch are observed at commit, before any
     * dirty table publication or return to a caller that releases memory. */
    for(unsigned fault=0;fault<7;fault++) {
        init();assert(lmi_desktop_map(addr[0],g_phys_base,0));
        if(fault==0)s[0x9058/4]=0;if(fault==1)s[0x48/4]=1;
        if(fault==2)gpu[0x821]=1;if(fault==3)gpu[0x823]=1;
        if(fault==4)g[BOOT_GMU_AHB_FENCE_STATUS/4]=1;
        if(fault==5)((u32 *)(dma+65536))[16]=1;
        if(fault==6)test=3;
        /* No new ring work exists between pages under gGPULock. */
        assert(lmi_desktop_map(addr[1],g_phys_base,0));expect_hold=1;
        if(!setjmp(held)){lmi_desktop_mapped();assert(!"faulty batch committed");}
        assert(storage.failed && storage.mapping && desktop_space.tables[0].changed);scenarios++;
    }
    /* An uncommitted batch cannot escape via submit, cache handoff or unmap. */
    init();assert(lmi_desktop_map(addr[0],g_phys_base,0));
    unsigned before=queued;assert(!lmi_desktop_submit(addr,sizes,1) && queued==before);
    lmi_desktop_mapped();assert(lmi_desktop_submit(addr,sizes,1)==1);scenarios++;
    for(unsigned op=0;op<2;op++) {
        init();assert(lmi_desktop_map(addr[0],g_phys_base,0));expect_hold=1;
        if(!setjmp(held)) {
            if(op)lmi_desktop_unmap(addr[0],4096);else lmi_desktop_to_memory(&storage,sizeof(storage));
            assert(!"uncommitted batch escaped");
        }
        assert(storage.failed && storage.mapping && !tlbis);scenarios++;
    }
'''
assert main.count('    printf("PASS:')==1
main=main.replace('    printf("PASS:',extra+'    printf("PASS:')
source=prefix+main
flags=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
       '-I',str(root/'tools')]
(out/'check.c').write_text(source)
subprocess.run([*flags,str(out/'check.c'),'-o',str(out/'check')],check=True)
p=subprocess.run([str(out/'check')],capture_output=True,text=True,timeout=30)
(out/'host.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr,end='');p.check_returncode()
mutations={
    'first_page_skips_drain':('if(!drain(d))hold(d);d->mapping=1;','d->mapping=1;'),
    'commit_skips_drain':('if(!drain(d) || !commit())hold(d);','if(!commit())hold(d);'),
    'commit_forgets_end':('d->mapping=0;','/* mutation: not ended */'),
    'cache_allows_open_batch':('if(d->mapping || bytes>','if(bytes>'),
    'page_checks_return':('if(!d->mapping) {if(!drain(d))hold(d);','if(1) {if(!drain(d))hold(d);'),
}
raw=(root/'tools/lmi-gpu-desktop-v63.c').read_text();caught=[]
for name,(old,new) in mutations.items():
    assert raw.count(old)==1,(name,old)
    candidate=out/(name+'.c');candidate.write_text(raw.replace(old,new))
    check=out/(name+'-check.c')
    check.write_text(source.replace('#include "lmi-gpu-desktop-v63.c"',f'#include "{candidate}"'))
    binary=out/(name+'-check')
    subprocess.run([*flags,str(check),'-o',str(binary)],check=True)
    failure=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
    (out/(name+'.log')).write_text(failure.stdout+failure.stderr)
    assert failure.returncode!=0,('Mutation survived',name);caught.append(name)
names=['check-lmi-gpu-map-v63.py','lmi-gpu-desktop-v63.c','check-lmi-gpu-async-v58.py',
       'check-lmi-gpu-desktop.c','lmi-gpu-boot-regs.h']
report=dict(result='PASS',scenarios=int(re.search(r'PASS: (\d+) scenarios',p.stdout)[1]),
    prior_scenarios=41,asan_ubsan=True,mutations_caught=caught,
    full_surface_map_pages=2744,full_surface_mmio_reads=16,full_surface_scratch_invalidates=2,
    actual_backend_used=True,hardware_tested=False,performance_verified=False,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('Mutation checks:',len(caught))
