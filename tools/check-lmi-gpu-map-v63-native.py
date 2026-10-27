"""Integrate v63 with verbatim native page-table routines and split CPU/DMA memory.

This is a host memory/ordering model, not GPU, SMMU or performance evidence.
Each process starts fresh, including the native allocator's static spare page.
"""
from pathlib import Path
import hashlib,json,re,subprocess

root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-gpu-map-v63-native-host';out.mkdir(exist_ok=True)
native_path=root/'hackios/xnu/files/bsd/dev/redwood_adreno.c'
native=native_path.read_text()
fragments=[]
for first,last in [('static uint64_t *\nspace_new_table(', '/* The table an entry of a higher table'),
                   ('static void\nspace_changed(', '/* The SMMU reads the tables'),
                   ('static uint64_t *\nspace_next(', '/* Memory of ours that the GPU block sees')]:
    a=native.index(first);b=native.index(last,a);fragments.append(native[a:b])
definitions='\n'.join(re.search(r'^#define '+name+r'\s+[^\n]+',native,re.M)[0]
                      for name in ['PTE_ADDRESS','PTE_TABLE','PTE_PAGE'])
template=root/'out/lmi-gpu-map-v63-host/check.c'
prefix=template.read_text().split('static u64 addr[128];',1)[0]
assert 'int main(' not in prefix and '#include "lmi-gpu-desktop-v63.c"' in prefix
prefix='#include <stdlib.h>\n#include <stdbool.h>\n'+prefix
adapter=r'''
#define PAGE_SIZE 16384
#define SPACE_TABLES 1024
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 9
#define KERN_SUCCESS 0
typedef u64 vm_offset_t;
static const u64 kernel_map=42,table_pa=0x81000000;
static unsigned char table_memory[1048576] __attribute__((aligned(16384))),table_dma[1048576];
static unsigned alloc_attempts,allocated,fail_allocation,pt_publishes,fail_publish;
static u64 kvtophys(u64 p) {
    if(p>=(u64)pool && p<(u64)pool+sizeof(pool))return pa_of(p);
    assert(p>=(u64)table_memory && p<(u64)table_memory+sizeof(table_memory));
    return table_pa+p-(u64)table_memory;
}
static int kmem_alloc(u64 map,u64 *p,u64 size,unsigned flags,unsigned tag) {
    assert(map==kernel_map && size==PAGE_SIZE && flags==7 && tag==9);
    if(++alloc_attempts==fail_allocation)return 1;
    assert(allocated+size<=sizeof(table_memory));
    *p=(u64)table_memory+allocated;memset((void *)*p,0,size);allocated+=size;return KERN_SUCCESS;
}
#define uint64_t u64
#define uint32_t u32
#define uintptr_t __UINTPTR_TYPE__
#define gpu_space desktop_space
'''+definitions+'\n'+''.join(fragments)+r'''
#undef uint64_t
#undef uint32_t
#undef uintptr_t
#undef gpu_space
int legacy_space_map(struct desktop_space *p,u64 addr,u64 phys,u64 attr) {
    assert(p==&desktop_space && addr>=0x20000000 && !(addr&4095));
    assert((!phys && !attr) || (phys>=g_phys_base && (attr==0xe40 || attr==0xec0)));
    assert(gpu[0x806]==gpu[0x807] && !pending_end);maps++;
    return space_map(p,addr,phys,attr);
}
'''
a=prefix.index('int legacy_space_map(');b=prefix.index('int cache_sync(',a)
prefix=prefix[:a]+adapter+prefix[b:]
old='    if(p>=(u64)pool && p+n<=(u64)pool+sizeof(pool)) {'
new=r'''
    if(publish && n==4096 && ((p>=(u64)pool+17*4096 && p+4096<=(u64)pool+sizeof(pool)) ||
       (p>=(u64)table_memory && p+4096<=(u64)table_memory+sizeof(table_memory)))) {
        if(++pt_publishes==fail_publish)return 0;
    }
    if(p>=(u64)table_memory && p+n<=(u64)table_memory+sizeof(table_memory)) {
        unsigned at=p-(u64)table_memory;
        if(publish)memcpy(table_dma+at,table_memory+at,n);else memcpy(table_memory+at,table_dma+at,n);
    } else if(p>=(u64)pool && p+n<=(u64)pool+sizeof(pool)) {
'''
assert prefix.count(old)==1;prefix=prefix.replace(old,new,1)
main=r'''
static u64 *device_table(u64 pa) {
    if(pa>=g_phys_base && pa<g_phys_base+sizeof(pool))return (void *)(dma+(pa-g_phys_base));
    assert(pa>=table_pa && pa+4096<=table_pa+sizeof(table_dma));return (void *)(table_dma+(pa-table_pa));
}
static u64 device_entry(u64 address) {
    u64 *table=device_table(pa_of((u64)pool+17*4096));
    for(unsigned shift=30;;shift-=9) {
        u64 entry=table[(address>>shift)&511];
        if(!(entry&1) || shift==12)return entry;
        table=device_table(entry&PTE_ADDRESS);
    }
}
static void verify(u64 address,unsigned pages,u64 physical,int ro) {
    for(unsigned i=0;i<pages;i++)assert(device_entry(address+4096ull*i)==((physical+4096ull*i)|(ro?0xec3:0xe43)));
}
static unsigned enter(u64 address,unsigned pages,u64 physical,int ro) {
    unsigned i;
    for(i=0;i<pages;i++)if(!lmi_desktop_map(address+4096ull*i,physical+4096ull*i,ro))break;
    return i;
}
static void assert_clear(u64 address,unsigned pages) {
    for(unsigned i=0;i<pages;i++)assert(!device_entry(address+4096ull*i));
}
static void simple(u64 address,unsigned pages,int ro) {
    const u64 physical=0x82000000;
    assert(enter(address,pages,physical,ro)==pages && !pt_publishes);
    assert_clear(address,pages);lmi_desktop_mapped();
    assert(!storage.mapping && pt_publishes>0);verify(address,pages,physical,ro);
    assert(!device_entry(address-4096) && !device_entry(address+4096ull*pages));
    lmi_desktop_unmap(address,pages*4096ull);assert_clear(address,pages);
    assert(tlbis==1 && syncs==1 && !storage.failed);
}
int main(int argc,char **argv) {
    assert(argc==2);unsigned scenario=(unsigned)atoi(argv[1]);
    seed(0);assert(start());const u64 address=0x20000000,physical=0x82000000;
    if(scenario==1)simple(address,1,0);
    if(scenario==2)simple(address,1,1);
    if(scenario==3)simple(address,512,0);
    if(scenario==4)simple(address,513,0);
    if(scenario==5)simple(address,2744,0);
    if(scenario==6)simple(0x3ffff000,5,1); /* crosses L1 and L2 boundaries */
    if(scenario==7)simple(0xfffff000,1,0);
    if(scenario==8) {
        assert(enter(address,1,physical,0)==1);lmi_desktop_mapped();
        u64 ib=address;u32 words=1;test=33;complete_at=76800;
        assert(lmi_desktop_submit(&ib,&words,1)==1 && pending_end);
        assert(enter(address+0x200000,513,physical+0x200000,0)==513);
        assert(!pending_end && sleeping && storage.done==1);lmi_desktop_mapped();
        verify(address+0x200000,513,physical+0x200000,0);
    }
    if(scenario==9 || scenario==10) {
        fail_allocation=scenario==9?1:2;
        unsigned got=enter(address,2744,physical,0);
        assert(got==(scenario==9?0u:2048u));
        lmi_desktop_mapped();assert(!storage.mapping && !storage.failed);
        fail_allocation=0;lmi_desktop_unmap(address,2744*4096ull);assert_clear(address,2744);
        assert(enter(address,2744,physical+0x1000000,1)==2744);
        lmi_desktop_mapped();verify(address,2744,physical+0x1000000,1);
    }
    if(scenario==11) {
        assert(enter(address,2744,physical,0)==2744);fail_publish=2;expect_hold=1;
        if(!setjmp(held)){lmi_desktop_mapped();assert(!"partial publication returned");}
        assert(storage.failed && storage.mapping && pt_publishes==2 && !tlbis);
        assert(desktop_space.table_count>4 && allocated); /* backing retained */
    }
    if(scenario==12) {
        assert(enter(address,513,physical,0)==513);s[0x48/4]=1;expect_hold=1;
        if(!setjmp(held)){lmi_desktop_mapped();assert(!"faulty batch returned");}
        assert(storage.failed && storage.mapping && !pt_publishes);assert_clear(address,513);
    }
    if(scenario==13) {
        assert(enter(address,513,physical,0)==513);lmi_desktop_mapped();verify(address,513,physical,0);
        lmi_desktop_unmap(address,513*4096ull);assert_clear(address,513);
        assert(enter(address,513,physical+0x1000000,1)==513);lmi_desktop_mapped();
        verify(address,513,physical+0x1000000,1);assert(tlbis==1 && syncs==1);
    }
    if(scenario==14) {
        assert(enter(address,513,physical,0)==513);lmi_desktop_mapped();
        s[0x97f4/4]=1;expect_hold=1;
        if(!setjmp(held)){lmi_desktop_unmap(address,513*4096ull);assert(!"uncertain TLBI returned");}
        assert(storage.failed && tlbis==1 && syncs==1 && allocated);
    }
    if(scenario==15) {
        assert(lmi_desktop_map(address,g_phys_base+g_phys_size-4096,0));
        assert(!lmi_desktop_map(address+4096,g_phys_base+g_phys_size,0));
        lmi_desktop_mapped();verify(address,1,g_phys_base+g_phys_size-4096,0);
        assert(!device_entry(address+4096));lmi_desktop_unmap(address,8192);assert_clear(address,2);
    }
    if(scenario==16) {
        unsigned before=maps;
        assert(!lmi_desktop_map(0x100000000ull,physical,0));
        assert(!lmi_desktop_map(0x1ffff000,physical,0));
        assert(!lmi_desktop_map(address,1ull<<36,0));
        assert(maps==before && !storage.mapping && !allocated);
    }
    assert(scenario>=1 && scenario<=16);
    printf("PASS native scenario %u: %u PTE attempts, %u table publications\n",scenario,maps,pt_publishes);
}
'''
source=out/'check.c';source.write_text(prefix+main)
cmd=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',
     '-I',str(root/'tools'),str(source),'-o',str(out/'check')]
subprocess.run(cmd,check=True);logs=[]
for i in range(1,17):
    result=subprocess.run([str(out/'check'),str(i)],text=True,capture_output=True,timeout=15)
    logs.append(result.stdout+result.stderr);print(logs[-1],end='');result.check_returncode()
(out/'host.log').write_text(''.join(logs))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=dict(result='PASS',scenarios=16,asan_ubsan=True,native_page_table_routines_verbatim=True,
    cpu_device_memory_separate=True,fresh_process_per_scenario=True,hardware_tested=False,performance_verified=False,
    native_fragments_sha256=[hashlib.sha256(f.encode()).hexdigest() for f in fragments],
    inputs={str(p.relative_to(root)):sha(p) for p in [Path(__file__),native_path,template,
            root/'tools/lmi-gpu-desktop-v63.c',root/'tools/lmi-gpu-boot-regs.h']},
    generated_source_sha256=sha(source),command=cmd)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
