"""Validate the actual probe TU against the real frozen v64 ring backend."""
from pathlib import Path
import hashlib,json,re,subprocess
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-gpu-copy-v66-host';out.mkdir(exist_ok=True)
tools=root/'tools';source=tools/'lmi-gpu-copy-v66.c'
prefix=(tools/'check-lmi-gpu-desktop.c').read_text().split('int main(void) {',1)[0]
prefix=prefix.replace('#include "lmi-gpu-desktop.c"','#include <stdint.h>\n#include "lmi-gpu-desktop-v64.c"')
prefix=prefix.replace('static u32 sleeping,pending_end,complete_at;',
    'static u32 sleeping,pending_end,complete_at;\nstatic unsigned probe_active,probe_fault,copy_bells,copy_reads;\nstatic void execute_copy(void);\nvoid lmi_display_smp_prepare(void) {}\nvoid lmi_gpu_publish_barrier(void) {}')
prefix=prefix.replace('gpu[0x806]==72 && desktop_free_count==1',
                      '(gpu[0x806]==72 || gpu[0x806]==90) && desktop_free_count==1')
prefix=prefix.replace('cache_calls++;', '''cache_calls++;
    if(probe_active) {
        if(probe_fault==9 && !publish && n==4096)return 0;
        if(probe_fault==11 && publish && n==1024)return 0;
        if(probe_fault==12 && publish && n==512)return 0;
        if(probe_fault==13 && !publish && p==(u64)pool+65536+64)return 0;
        if(probe_fault==14 && !publish && n==4096 && copy_bells)return 0;
    }''')
prefix=prefix.replace('u32 rsc_read(volatile u32 *p) {','''u32 rsc_read(volatile u32 *p) {
    if(probe_active && probe_fault==24 && copy_bells && p==gpu+0x806 &&
       gpu[0x806]==72 && ++copy_reads==32)execute_copy();''')
prefix=prefix.replace('if(p==gpu+0x807) {','''if(p==gpu+0x807 && probe_active && v==90 && !storage.fence) {
        copy_bells++;*p=v;
        assert(!memcmp(pool,dma,512));
        if(probe_fault==23)gpu[0x821]=1;
        else if(probe_fault!=22 && probe_fault!=24)execute_copy();
        return;
    }
    if(p==gpu+0x807) {''')
test=out/'check.c';test.write_text(prefix+(tools/'check-lmi-gpu-copy-v66.c').read_text(),encoding='utf-8')
flags=['clang','-std=c17','-O2','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
       '-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(tools)]
command=[*flags,str(test),str(source),'-o',str(out/'check')]
subprocess.run(command,check=True)
p=subprocess.run([str(out/'check')],text=True,capture_output=True,timeout=30)
(out/'host.log').write_text(p.stdout+p.stderr,encoding='utf-8');print(p.stdout+p.stderr,end='');p.check_returncode()
raw=source.read_text();mutations={
    'source_not_published':('!cache_sync((uintptr_t)(scratch+512),1024,1)','0'),
    'ring_not_published':('!cache_sync(d->pool,512,1)','0'),
    'target_not_invalidated':('if(!cache_sync((uintptr_t)scratch,4096,0))return 0;\n    uint64_t elapsed',
                               'if(0)return 0;\n    uint64_t elapsed'),
    'wrong_copy_length':('0x70758005,255,','0x70758005,256,'),
    'missing_write_wait':('0x70928000,0x70268000,','0x70268000,0x70268000,'),
    'pixel_failure_ignored':('if(bad || scratch[384]', 'if(scratch[384]'),
    'missing_ts_accepted':('scratch[384]!=0x660c0de6 || ',''),
    'uncertain_dma_returned':('if(!lmi_v66_drain(d))lmi_v66_hold(d);','if(!lmi_v66_drain(d))return 0;'),
}
caught=[]
for name,(old,new) in mutations.items():
    assert raw.count(old)==1,(name,old)
    changed=out/(name+'.c');changed.write_text(raw.replace(old,new),encoding='utf-8')
    binary=out/(name+'-check');subprocess.run([*flags,str(test),str(changed),'-o',str(binary)],check=True)
    result=subprocess.run([str(binary)],text=True,capture_output=True,timeout=30)
    (out/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    assert result.returncode!=0,('mutation survived',name);caught.append(name)
analysis=['clang','--analyze','-std=c17','-I',str(tools),str(source),'-Xanalyzer','-analyzer-output=text']
a=subprocess.run(analysis,text=True,capture_output=True,check=True)
(out/'static-analysis.log').write_text(a.stdout+a.stderr,encoding='utf-8');assert not a.stdout+a.stderr
names=['check-lmi-gpu-copy-v66.py','check-lmi-gpu-copy-v66.c','lmi-gpu-copy-v66.c','lmi-gpu-copy-v66.h',
       'check-lmi-gpu-desktop.c','lmi-gpu-desktop-v64.c','lmi-gpu-boot-regs.h']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=dict(result='PASS',scenarios=int(re.search(r'PASS: (\d+) scenarios',p.stdout)[1]),
    asan_ubsan=True,actual_v64_backend=True,separate_cpu_dma_views=True,independent_packet_decode=True,
    post_probe_jobs=80,mutations_caught=caught,static_analysis=True,hardware_tested=False,
    desktop_gpu_copy=False,performance_verified=False,command=command,analysis_command=analysis,
    sources={n:sha(tools/n) for n in names},generated_source_sha256=sha(test))
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS:',len(caught),'mutations caught; clang static analysis clean')
