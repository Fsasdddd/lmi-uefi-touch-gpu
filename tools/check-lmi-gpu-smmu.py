"""Run the actual read-only SMMU census against host RAM, never real MMIO."""
from pathlib import Path
import hashlib,json,subprocess
repo=Path(__file__).resolve().parents[1]
out=repo/'out/lmi-gpu-smmu-host-check';out.mkdir(exist_ok=True)
source=(repo/'tools/lmi-gpu-probe.c').read_text()
prefix=source[:source.index('#ifndef LMI_GPU_CONTEXT_PROBE'+chr(10)+'static void tcm_load')]
read_asm=prefix[prefix.index('__asm__ volatile("ldr'):prefix.index('return (u32)value;')].strip()
assert prefix.count(read_asm)==1
prefix=prefix.replace(read_asm,'value=*address;')
assert prefix.count('__asm__ volatile("dsb sy":::"memory");')==4
prefix=prefix.replace('__asm__ volatile("dsb sy":::"memory");','__atomic_thread_fence(5);')
prefix=prefix.replace('__asm__ volatile('+chr(34)+'dsb sy'+chr(34)+'::: '+chr(34)+'memory'+chr(34)+');','__atomic_thread_fence(5);')
store='__asm__ volatile("str %w0, [%1]" : "+r"(value) : "r"(&s[0x1800/4]) : "memory");'
assert prefix.count(store)==2
prefix=prefix.replace(store,'s[0x1800/4]=value;')
start=prefix.index('    __asm__ volatile(',prefix.index('static void __attribute__((noinline)) smmu_wr32'))
end=prefix.index(chr(10)+'}',start)
prefix=prefix[:start]+'    extern void model_smmu_store(volatile u32 *,u32); model_smmu_store(address,value);'+prefix[end:]
prefix='#define LMI_GPU_CONTEXT_PROBE'+chr(10)+prefix
prefix=prefix.replace('extern void *memset(void *,int,u64);','')
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
u64 kernel_map_value=1,xnu_page_size=16384,g_phys_base=0x100000000ULL,g_phys_size=0x180000000ULL;
static u64 model_pool;
static int model_frees,model_cleans,model_cbar_writes;
struct kmem_result kmem_alloc_tagged(u64 map,u64 size,u64 mask,u32 flags,u64 tag,void *callback) {
    assert(map==1 && size==16384 && !mask && !flags && tag==3 && !callback && !model_pool);
    model_pool=(u64)(uintptr_t)aligned_alloc(16384,16384);assert(model_pool);
    memset((void *)(uintptr_t)model_pool,0xa5,16384);return (struct kmem_result){0,model_pool};
}
u64 pa_of(u64 va) {assert(model_pool && va>=model_pool && va<model_pool+16384);return 0x19e610000ULL+va-model_pool;}
void clean_cache(u64 va,u32 size,int mode) {
    assert(va==model_pool && size==16384 && mode==0);
    for(unsigned i=0;i<size;i++)assert(!((unsigned char *)(uintptr_t)va)[i]);model_cleans++;
}
void kmem_free3(u64 map,u64 va,u64 size) {assert(map==1 && va==model_pool && size==16384);free((void *)(uintptr_t)va);model_pool=0;model_frees++;}
static u32 gcc[0x80000/4], smmu[0x10000/4];
static u32 gcc_before[0x80000/4], smmu_before[0x10000/4];
static char text[65536];
static int no_map, smmu_maps;
static int observed_filter_model,refuse_ttbr_restore;
void model_smmu_store(volatile u32 *address,u32 value) {
    if(address==&smmu[0x1000/4])model_cbar_writes++;
    if(refuse_ttbr_restore && address==&smmu[0x8020/4] && value==0x24680000)return;
    /* Reproduce observed results, not an asserted architectural explanation. */
    if(observed_filter_model && address==&smmu[0x1000/4] && !value)return;
    if(observed_filter_model && address==&smmu[0x8010/4] && value==0x38011)value|=0x60;
    *address=value;
}
u64 io_map(u64 address,u64 size) {
    if(address==0x100000) {assert(size==0x80000);return (u64)(uintptr_t)gcc;}
    assert(address==0x3da0000 && size==0x10000);smmu_maps++;
    return no_map?0:(u64)(uintptr_t)smmu;
}
void delay(u32 interval,u32 scale) {assert(interval<=1000 && scale==1000);}
void log_line(const char *s) {assert(strlen(text)+strlen(s)<sizeof(text));strcat(text,s);}
void log_hex(u64 value) {char s[32];snprintf(s,sizeof(s),"%016llx\n",value);log_line(s);}
int main(void) {
    gcc[0x7100c/4]=1;gcc[0x71018/4]=1;
    smmu[0x20/4]=(1u<<27)|128;smmu[0x24/4]=7|(2u<<16);
    smmu[0x28/4]=0x1033;
    for(unsigned i=0;i<128;i++) {
        smmu[(0x800+4*i)/4]=0x80000000u|(0x400u<<16)|i;
        smmu[(0xc00+4*i)/4]=i%7;
    }
    for(int test=0;test<4;test++) {
        if(test==1)smmu[0x24/4]|=1u<<31; /* 64KiB page layout exceeds DT window */
        if(test==2)no_map=1;
        if(test==3)gcc[0x7100c/4]|=1u<<31; /* no clock transitions in this model */
        text[0]=0;smmu_maps=0;
        memcpy(gcc_before,gcc,sizeof(gcc));memcpy(smmu_before,smmu,sizeof(smmu));
        smmu_readonly(6);
        assert(!memcmp(gcc_before,gcc,sizeof(gcc)));
        assert(!memcmp(smmu_before,smmu,sizeof(smmu)));
        assert(strstr(text,"LMI_GPU_SMMU_END\n"));
        if(test==0) {
            assert(strstr(text,"LMI_GPU_SMMU_STREAMS_END\n"));
            unsigned count=0;const char *p=text;
            while((p=strstr(p,"LMI_GPU_SMMU_STREAM_INDEX\n"))) {count++;p++;}
            assert(count==128);
        } else {
            assert(!strstr(text,"LMI_GPU_SMMU_STREAMS_END\n"));
            assert(strstr(text,test==1?"LMI_GPU_SMMU_LAYOUT_REFUSED":test==2?"LMI_GPU_SMMU_MAP_FAILED":"LMI_GPU_SMMU_CLOCK_REFUSED"));
        }
        if(test==3)assert(smmu_maps==0);
        smmu[0x24/4]=7|(2u<<16);no_map=0;
    }
    memset(smmu,0,sizeof(smmu));
    gcc[0x7100c/4]=gcc[0x71018/4]=1;
    smmu[0x20/4]=0x4c017e06;smmu[0x24/4]=0x20000005;
    for(int trial=0;trial<3;trial++) {
        if(trial==1)smmu[0x800/4]=1u<<31;
        if(trial==2) {smmu[0x800/4]=0;smmu[0]|=8;}
        memcpy(smmu_before,smmu,sizeof(smmu));text[0]=0;
        smmu_readonly(8);
        assert(!memcmp(smmu_before,smmu,sizeof(smmu)));
        assert(!!strstr(text,"LMI_GPU_CB0_END\n")==!trial);
        if(!trial) {
            unsigned count=0;const char *p=text;
            while((p=strstr(p,"LMI_GPU_CB0_READ_ADDRESS\n"))) {count++;p++;}
            assert(count==45);
            assert(strstr(text,"LMI_GPU_CB0_CHANGED_READS\n0000000000000000\n"));
        } else assert(strstr(text,"LMI_GPU_CB0_REFUSED_LAYOUT\n"));
    }
    memset(smmu,0,sizeof(smmu));text[0]=0;
    memcpy(smmu_before,smmu,sizeof(smmu));
    cb0_format_probe(smmu);
    assert(!memcmp(smmu_before,smmu,sizeof(smmu)));
    assert(strstr(text,"LMI_GPU_CB0_FORMAT_WRITTEN\n0000000000000001\n"));
    assert(strstr(text,"LMI_GPU_CB0_FORMAT_END\n"));
    smmu[0x8000/4]=1;text[0]=0;cb0_format_probe(smmu);
    assert(strstr(text,"LMI_GPU_CB0_FORMAT_REFUSED\n"));
    smmu[0x8000/4]=0;smmu[0x800/4]=1u<<31;text[0]=0;cb0_format_probe(smmu);
    assert(strstr(text,"LMI_GPU_CB0_FORMAT_REFUSED\n"));
    memset(smmu,0,sizeof(smmu));
    for(unsigned i=0x8010/4;i<=0x803c/4;i++)smmu[i]=0x13579bdfu+i;
    memcpy(smmu_before,smmu,sizeof(smmu));text[0]=0;cb0_context_probe(smmu,0);
    assert(!memcmp(smmu_before,smmu,sizeof(smmu)));
    assert(strstr(text,"LMI_GPU_CB0_CONTEXT_END\n"));
    for(int trial=0;trial<4;trial++) {
        memset(smmu,0,sizeof(smmu));
        smmu[(trial==0?0x8000:trial==1?0x48:trial==2?0x8058:0x800)/4]=trial==3?0x80000000u:1;
        memcpy(smmu_before,smmu,sizeof(smmu));text[0]=0;cb0_context_probe(smmu,0);
        assert(!memcmp(smmu_before,smmu,sizeof(smmu)));
        assert(strstr(text,"LMI_GPU_CB0_CONTEXT_REFUSED\n"));
    }
    memset(smmu,0,sizeof(smmu));text[0]=0;observed_filter_model=1;
    cb0_context_probe(smmu,0);
    assert(smmu[0x1000/4]==0x1f300);
    assert(smmu[0x1800/4]==0 && smmu[0x8000/4]==0 && smmu[0x8010/4]==0);
    assert(strstr(text,"LMI_GPU_CB0_CONTEXT_ACTUAL\n0000000000038071\n"));
    assert(strstr(text,"LMI_GPU_CB0_CONTEXT_RESTORED\n000000000001f300\n"));
    memset(smmu,0,sizeof(smmu));text[0]=0;model_cbar_writes=0;
    smmu[0x8020/4]=0x24680000;smmu[0x8024/4]=2;
    memcpy(smmu_before,smmu,sizeof(smmu));cb0_context_probe(smmu,1);
    assert(!memcmp(smmu_before,smmu,sizeof(smmu)));
    assert(!model_cbar_writes && !model_pool && model_frees==1 && model_cleans==1);
    assert(strstr(text,"LMI_GPU_CB0_TABLE_FREED\n"));
    assert(strstr(text,"LMI_GPU_CB0_TABLE_ROOT\n000000019e610000\n"));
    memset(smmu,0,sizeof(smmu));text[0]=0;refuse_ttbr_restore=1;
    smmu[0x8020/4]=0x24680000;cb0_context_probe(smmu,1);
    assert(model_pool && model_frees==1 && model_cleans==2);
    assert(strstr(text,"LMI_GPU_CB0_TABLE_RETAINED\n"));
    assert(!strstr(text,"LMI_GPU_CB0_TABLE_FREED\n"));
    /* Host-only cleanup stands in for the bounded whole-device reset. */
    refuse_ttbr_restore=0;smmu[0x8020/4]=0x24680000;
    kmem_free3(1,model_pool,16384);
    puts("PASS: owned zero root, no CBAR writes, restore/free and mismatch model; no DMA proof");
}
'''
test=out/'smmu-host.c';test.write_text('#include <string.h>'+chr(10)+prefix+harness)
subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined',str(test),'-o',str(out/'smmu-host')],check=True)
result=subprocess.run([str(out/'smmu-host')],check=True,capture_output=True,text=True)
print(result.stdout,end='')
(out/'result.json').write_text(json.dumps(dict(result='PASS',source_sha256=hashlib.sha256(source.encode()).hexdigest(),
    host_ram_only=True,hardware_verified=False,sanitizers=['address','undefined'],stdout=result.stdout),indent=2)+'\n')
