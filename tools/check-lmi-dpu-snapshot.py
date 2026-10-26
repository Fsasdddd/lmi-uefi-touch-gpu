"""Exercise the source snapshot against a protected read-only register page."""
from pathlib import Path
import hashlib, json, subprocess

repo=Path(__file__).resolve().parents[1]
source=repo/'tools/lmi-dpu-snapshot.c'
out=repo/'out/lmi-dpu-snapshot-host'
out.mkdir(exist_ok=True)
prefix='''#define LMI_DPU_SNAPSHOT_HOST 1
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
'''
suffix=r'''
int main(void) {
    const size_t size=0x84000;
    dpu_u32 *page=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(page!=MAP_FAILED);
    for(unsigned i=0;i<size/4;i++)page[i]=0x65000000u^i;
    assert(mprotect(page,size,PROT_READ)==0);
    struct lmi_dpu_snapshot result,before;
    memset(&result,0xa5,sizeof(result));before=result;
    assert(!lmi_dpu_read_snapshot(NULL,&result));
    assert(!memcmp(&before,&result,sizeof(result)));
    assert(!lmi_dpu_read_snapshot(page,NULL));
    assert(!lmi_dpu_read_snapshot(NULL,NULL));
    assert(lmi_dpu_read_snapshot(page,&result)==1);
    const unsigned offsets[]={0x6ba5c,0x6ba88,0x6bab4,0x6b8ac,0x6bab0,0x201c,0x2018,0x5014,0x5024};
    dpu_u32 fields[9];memcpy(fields,&result,sizeof(fields));
    assert(sizeof(fields)==sizeof(result));
    for(unsigned i=0;i<9;i++)assert(fields[i]==(0x65000000u^(offsets[i]/4)));
    assert(munmap(page,size)==0);
    puts("PASS: read-only mapping, all 9 register fields, 3 null controls; no register writes");
}
'''
(out/'check.c').write_text(prefix+source.read_text()+suffix)
subprocess.run(['clang','-std=c11','-D_GNU_SOURCE','-O2','-Wall','-Wextra','-Werror',
    '-fsanitize=address,undefined',str(out/'check.c'),'-o',str(out/'check')],check=True)
subprocess.run([str(out/'check')],check=True)
report=dict(result='PASS',register_fields=9,null_controls=3,readonly_mapping=True,
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),hardware_verified=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
