"""Exercise the actual TCM loader on host RAM; this cannot prove MMIO behavior."""
from pathlib import Path
import hashlib, json, subprocess

repo = Path(__file__).resolve().parents[1]
out = repo / 'out/lmi-gpu-tcm-host-check'
out.mkdir(exist_ok=True)
source = (repo / 'tools/lmi-gpu-probe.c').read_text()
# Compile the actual production function, replacing only its ARM barrier for x86.
prefix = source[:source.index('static int clock_on')] + source[source.index('static void tcm_load'):source.index('/* kona GPUCC:')]
assert prefix.count('__asm__ volatile("dsb sy":::"memory");') == 1
prefix = prefix.replace('__asm__ volatile("dsb sy":::"memory");', '__atomic_thread_fence(5);')
harness = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned char firmware[41548];
static unsigned int mmio[0x30000/4], initial[0x30000/4];
static char logbuf[8192];
static int absent, fail_alloc, allocs, frees;
static u64 fw_size=41548;
const unsigned char *image_file(const char *dir,const char *name,u64 *size,int *disk) {
    assert(!strcmp(dir,"fw") && !strcmp(name,"a650_gmu.bin"));
    *size=fw_size;*disk=1;return absent?NULL:firmware;
}
void *alloc_data(u64 size) {
    assert(size==18404 && !memcmp(mmio,initial,sizeof(mmio)));
    allocs++;return fail_alloc?NULL:malloc(size);
}
void free_data(void *p,u64 size) {
    assert(size==18404 && !memcmp(mmio,initial,sizeof(mmio)));
    frees++;free(p);
}
void log_line(const char *s) { assert(strlen(logbuf)+strlen(s)<sizeof(logbuf));strcat(logbuf,s); }
void log_hex(u64 value) { char s[32];snprintf(s,sizeof(s),"%016llx\n",value);log_line(s); }
int main(int argc,char **argv) {
    assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);
    assert(fread(firmware,1,sizeof(firmware),f)==sizeof(firmware));fclose(f);
    for(unsigned n=0;n<sizeof(mmio)/4;n++)mmio[n]=0xdead0000u^(n*1234567u);
    mmio[0x14000/4]=1;memcpy(initial,mmio,sizeof(mmio));
    tcm_load(mmio);
    assert(!memcmp(mmio,initial,sizeof(mmio)) && allocs==1 && frees==1);
    assert(strstr(logbuf,"LMI_GPU_TCM_MISMATCHES\n0000000000000000\n"));
    assert(strstr(logbuf,"LMI_GPU_TCM_RESTORE_MISMATCHES\n0000000000000000\n"));
    assert(strstr(logbuf,"LMI_GPU_TCM_END\n"));
    for(int test=0;test<6;test++) {
        logbuf[0]=0;allocs=frees=0;
        if(test==0)absent=1;
        if(test==1)fw_size=41544;
        if(test==2)mmio[0x14000/4]=0;
        if(test==3)firmware[160]^=1;
        if(test==4)firmware[0]^=1;
        if(test==5)fail_alloc=1;
        memcpy(initial,mmio,sizeof(mmio));
        tcm_load(mmio);
        assert(!memcmp(mmio,initial,sizeof(mmio)) && frees==0);
        assert(!strstr(logbuf,"LMI_GPU_TCM_BEGIN\n"));
        assert(allocs==(test==5));
        absent=0;fw_size=41548;fail_alloc=0;mmio[0x14000/4]=1;
        if(test==3)firmware[160]^=1;
        if(test==4)firmware[0]^=1;
    }
    puts("PASS: actual TCM loader restores all RAM words; six refusal cases make no changes");
}
'''
firmware = repo / 'out/lmi-gpu-hardware/a650_gmu.bin'
assert hashlib.sha256(firmware.read_bytes()).hexdigest() == 'df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c'
test = out / 'tcm-host.c'
test.write_text(prefix + harness)
subprocess.run(['clang', '-O1', '-g', '-fsanitize=address,undefined', str(test), '-o', str(out/'tcm-host')],check=True)
result = subprocess.run([str(out/'tcm-host'), str(firmware)],check=True,capture_output=True,text=True)
print(result.stdout,end='')
(out/'result.json').write_text(json.dumps(dict(result='PASS', source_sha256=hashlib.sha256(source.encode()).hexdigest(),
    checks=['original words restored','missing file','wrong size','reset not asserted','corrupt payload','corrupt header','allocation failure'],
    sanitizers=['address','undefined'],host_ram_only=True,hardware_verified=False,stdout=result.stdout),indent=2)+'\n')
