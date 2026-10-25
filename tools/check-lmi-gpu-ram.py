"""Exercise the actual RAM plan with noncontiguous host-model physical pages."""
from pathlib import Path
import hashlib,json,subprocess,sys
repo=Path(__file__).resolve().parents[1]
out=repo/'out/lmi-gpu-ram-host-check';out.mkdir(exist_ok=True)
source=(repo/'tools/lmi-gpu-ram.c').read_text()
hfi='--hfi' in sys.argv
if hfi:source='#define LMI_GPU_RAM_HFI'+chr(10)+(repo/'tools/lmi-gpu-hfi.c').read_text()+source
compact='--compact' in sys.argv
assert not compact or hfi
if compact:source='#define LMI_GPU_GMU_ROUTE'+chr(10)+source
booting='--boot' in sys.argv
assert not booting or compact
if booting:source='#define LMI_GPU_GMU_BOOT'+chr(10)+source
combined='--context' in sys.argv
stage1='--stage1' in sys.argv
assert not stage1 or combined
if stage1:source='#define LMI_GPU_STAGE1_INIT'+chr(10)+source
assert not combined or hfi
if combined:
    model=(repo/'tools/check-lmi-gpu-context.c').read_text().split('int main(void)')[0]
    model=model.replace('#include "lmi-gpu-context.c"',(repo/'tools/lmi-gpu-context.c').read_text())
    model=model.replace('void log_line(const char *s) {(void)s;}','').replace('void log_hex(ctx_u64 n) {(void)n;}','')
    source='#define LMI_GPU_COMBINED_HOST'+chr(10)+source+model
assert source.count('__asm__ volatile("dsb sy":::"memory");')==(2 if combined else 1)
test_source=source.replace('__asm__ volatile("dsb sy":::"memory");','__atomic_thread_fence(5);')
# libc's size_t has the same width, but a different C spelling on the host.
test_source=test_source.replace('extern void *memset(void *,int,u64);','').replace('extern void *memcpy(void *,const void *,u64);','')
harness=r'''
static unsigned char firmware[41548];
static char text[16384];
static u64 boot[4]={0,0,0x100000000ULL,0x180000000ULL};
u64 kernel_map_value=0xf00,boot_args_ptr=(u64)boot,g_phys_base=0x100000000ULL,g_phys_size=0x180000000ULL,xnu_page_size;
u32 xnu_page_shift;
static int scenario,allocs,frees,cleans;
static u64 live_pool,live_bytes;
void log_line(const char *s) {assert(strlen(text)+strlen(s)<sizeof(text));strcat(text,s);}
void log_hex(u64 v) {char s[32];snprintf(s,sizeof(s),"%016llx\n",v);log_line(s);}
const unsigned char *image_file(const char *dir,const char *name,u64 *size,int *disk) {
    assert(!strcmp(dir,"fw") && !strcmp(name,"a650_gmu.bin"));*size=41548;*disk=1;return firmware;
}
struct kmem_result kmem_alloc_tagged(u64 map,u64 size,u64 mask,u32 flags,u64 guard,void *callback) {
    assert(map==kernel_map_value && !live_pool && !mask && !flags && guard==3 && !callback);allocs++;
    if(scenario==2)return (struct kmem_result){3,0};
    live_pool=(u64)aligned_alloc(xnu_page_size,size);assert(live_pool);
    live_bytes=size;memset((void *)live_pool,0xa5,size);return (struct kmem_result){0,live_pool};
}
void kmem_free3(u64 map,u64 va,u64 bytes) {
    assert(map==kernel_map_value && va==live_pool && bytes==live_bytes);
    free((void *)va);live_pool=0;live_bytes=0;frees++;
}
u64 pa_of(u64 va) {
    assert(live_pool && va>=live_pool && va<live_pool+live_bytes);
    u64 offset=va-live_pool,n=offset/4096,factor=xnu_page_size/4096;
    if(scenario==3 && n==3)return 0;
    if(scenario==4 && n==1)n=0;
    u64 pa=g_phys_base+0x100000+(n/factor)*0x8000+(n%factor)*4096+(offset&4095);
    if(scenario==5)pa+=1ULL<<36;
    if(scenario==8)pa|=256;
    if(scenario==9 && (offset&4095)==4095)pa++;
    return pa;
}
void clean_cache(u64 va,u32 size,int phys) {
    assert(va==live_pool && size==live_bytes && phys==0);cleans++;
}
static int consumer_calls;
static int test_consumer(u64 root,void *context) {
    assert(live_pool && allocs==1 && frees==0 && cleans==1);
    assert(root==pa_of(live_pool+PAYLOAD_PAGES*4096));
    u64 *table=(u64 *)(live_pool+PAYLOAD_PAGES*4096);
    assert(table[0]==(pa_of(live_pool+(PAYLOAD_PAGES+1)*4096)|3));
#ifdef LMI_GPU_RAM_HFI
    struct lmi_hfi_table *hfi=(void *)(live_pool+37*4096);
    assert(hfi->queue[0].start_addr==0x60001100);
    assert(hfi->queue[3].start_addr==0x60004100);
#endif
#ifdef LMI_GPU_GMU_BOOT
    struct lmi_gpu_live_backing *live=context;
    assert(live->cpu_address==live_pool && live->allocation_bytes==live_bytes);
    context=live->owner_context;
#endif
    consumer_calls++;return *(int *)context;
}
#ifdef LMI_GPU_COMBINED_HOST
static int combined_consumer(u64 root,void *context) {
    int ok=1;test_consumer(root,&ok);
    return lmi_gmu_root_probe(root,context);
}
#endif
int main(int argc,char **argv) {
    assert(argc==2);FILE *file=fopen(argv[1],"rb");assert(file);
    assert(fread(firmware,1,41548,file)==41548);fclose(file);
    for(scenario=0;scenario<10;scenario++) {
        xnu_page_size=scenario==1?16384:4096;xnu_page_shift=scenario==1?14:12;
        text[0]=0;allocs=frees=cleans=0;
        if(scenario==6)firmware[160]^=1;
        if(scenario==7)boot[3]-=4096;
        lmi_gpu_ram_plan();
        assert(!live_pool);
        if(scenario<2) {
            assert(allocs==1 && frees==1 && cleans==1);
            assert(strstr(text,"LMI_GPU_RAM_SOFTWARE_WALK_OK\n"));
            assert(strstr(text,"LMI_GPU_RAM_FAILED\n0000000000000000\n"));
            char path[4096];snprintf(path,sizeof(path),"%s/scenario-%d.log",OUTPUT_DIR,scenario);
            FILE *log=fopen(path,"w");assert(log);fputs(text,log);fclose(log);
        } else {
            assert(!strstr(text,"LMI_GPU_RAM_SOFTWARE_WALK_OK\n"));
            assert(allocs==(scenario==6 || scenario==7?0:1));
            assert(frees==(scenario==2 || scenario==6 || scenario==7?0:1));
        }
        if(scenario==6)firmware[160]^=1;
        if(scenario==7)boot[3]+=4096;
    }
    scenario=0;xnu_page_size=16384;xnu_page_shift=14;
    int statuses[]={1,2,0,-1
#ifdef LMI_GPU_GMU_BOOT
        ,3
#endif
    };
    for(unsigned i=0;i<sizeof(statuses)/sizeof(statuses[0]);i++) {
        allocs=frees=cleans=consumer_calls=0;text[0]=0;
        lmi_gpu_ram_use(test_consumer,&statuses[i]);
        assert(consumer_calls==1);
        if(i<2) {
            assert(!live_pool && frees==1);
            assert(strstr(text,"LMI_GPU_RAM_CLEANUP_DONE\n"));
            assert(strstr(text,i==0?"LMI_GPU_RAM_FAILED\n0000000000000000\n":"LMI_GPU_RAM_FAILED\n0000000000000001\n"));
        }
        else {
            assert(live_pool && frees==0);
            assert(strstr(text,statuses[i]==3?"LMI_GPU_RAM_ACTIVE_RETAINED\n":"LMI_GPU_RAM_RETAINED\n"));
            assert(!strstr(text,"LMI_GPU_RAM_CLEANUP_DONE\n"));
            kmem_free3(kernel_map_value,live_pool,live_bytes);
        }
    }
#ifdef LMI_GPU_COMBINED_HOST
    for(int n=0;n<
#ifdef LMI_GPU_STAGE1_INIT
        5
#else
        4
#endif
        ;n++) {
        reset();scenario=0;xnu_page_size=16384;xnu_page_shift=14;
        allocs=frees=cleans=consumer_calls=0;text[0]=0;
        if(n==1)request_fail=1;
        if(n==2)restore_fail=1;
        if(n==3)regs[0x8000/4]=1;
#ifdef LMI_GPU_STAGE1_INIT
        if(n==4)tlb_timeout=1;
#endif
        lmi_gpu_ram_use(combined_consumer,regs);
        assert(consumer_calls==1);
        if(n==2
#ifdef LMI_GPU_STAGE1_INIT
            || n==4
#endif
            ) {
            assert(live_pool && !frees && strstr(text,"LMI_GPU_RAM_RETAINED\n"));
            kmem_free3(kernel_map_value,live_pool,live_bytes);
        } else {
            assert(!live_pool && frees==1);
            assert(strstr(text,n==0?"LMI_GPU_RAM_FAILED\n0000000000000000\n":"LMI_GPU_RAM_FAILED\n0000000000000001\n"));
#ifdef LMI_GPU_STAGE1_INIT
            if(n==0) {
                assert(regs[0x1000/4]==0x1f300 && tlb_reads==3 && writes==21);
            }
            if(n==0 || n==1)saved[0x1000/4]=0x1f300;
#endif
            assert(!memcmp(regs,saved,sizeof(regs)) || n==3);
        }
    }
#endif
    puts("PASS: wired firmware/HFI walks, consumer lifetime, cleanup and retention on unconfirmed detach");
}
'''
if compact:
    harness=harness.replace('LMI_GPU_RAM_FAILED\\n0000000000000000\\n','LMI_GPU_RAM_CONSUMER_RESULT\\n0000000000000001\\n').replace('LMI_GPU_RAM_FAILED\\n0000000000000001\\n','LMI_GPU_RAM_CONSUMER_RESULT\\n0000000000000002\\n')
prefix='#include <assert.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n'
test=out/'ram-host.c';test.write_text(prefix+test_source+harness)
subprocess.run(['clang','-O1','-g','-I'+str(repo/'tools'),'-fsanitize=address,undefined',f'-DOUTPUT_DIR="{out}"',str(test),'-o',str(out/'ram-host')],check=True)
fw=repo/'out/lmi-gpu-hardware/a650_gmu.bin'
assert hashlib.sha256(fw.read_bytes()).hexdigest()=='df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c'
result=subprocess.run([str(out/'ram-host'),str(fw)],capture_output=True,text=True)
print(result.stdout,end='');print(result.stderr,end='');result.check_returncode()
(out/'result.json').write_text(json.dumps(dict(result='PASS',source_sha256=hashlib.sha256(source.encode()).hexdigest(),
    host_ram_only=True,hardware_verified=False,sanitizers=['address','undefined'],stdout=result.stdout),indent=2)+'\n')
