"""Rebuild the linked worker, exercise concurrency mutants and bind evidence."""
from pathlib import Path
from importlib.machinery import SourceFileLoader
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/lmi-display-async-v80-review-b'
OUT.mkdir(exist_ok=False)
helper=SourceFileLoader('v73_review',str(ROOT/'tools/build-lmi-display-timing-v73.py')).load_module()
candidate=ROOT/'out/lmi-display-async-v80a'
audit=json.loads((candidate/'build-audit.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in audit['inputs'].items():assert sha(ROOT/name)==digest,name
flags=['--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
       '-mgeneral-regs-only','-fno-stack-protector','-fno-omit-frame-pointer','-Wall','-Wextra','-Werror']
obj=OUT/'independent.o';linked=OUT/'independent.elf'
subprocess.run(['clang',*flags,'-c',str(ROOT/'tools/lmi-display-async-v80.c'),'-o',str(obj)],check=True)
subprocess.run(['ld.lld','-T',str(candidate/'async.ld'),'--entry=lmi_async_show',str(obj),
    *[f'--defsym={n}={v}' for n,v in audit['bindings'].items()],'-o',str(linked)],check=True)
assert helper.elf(linked)['.async'][1]==helper.elf(candidate/'async.elf')['.async'][1]
original=(ROOT/'out/lmi-render-cpu-v79/mach.development.bcm2837').read_bytes()
raw=(candidate/'mach.development.bcm2837').read_bytes();check=bytearray(raw)
for a,z in audit['allowed_file_ranges']:check[a:z]=original[a:z]
assert check==original
source=(ROOT/'tools/lmi-display-async-v80.c').read_text()
mutants={
    'bypass-pending-and-buffer-pressure':('while(!stopping() && !c->failed && (c->pending>=0 || !free_buffer(p))) {','while(!stopping() && !c->failed && 0 && (c->pending>=0 || !free_buffer(p))) {'),
    'skip-idle-scan-completion':('if(p->scanning>=0) {','if(p->scanning>=0 && c->pending>=0) {'),
    'publish-partial-frame':('if(result!=1 || index>=2 || p->state[index]!=LMI_READY || !ticket || p->ticket[index]!=ticket) {',
        'if(0 && (result!=1 || index>=2 || p->state[index]!=LMI_READY || !ticket || p->ticket[index]!=ticket)) {'),
}
results=[]
for name,(old,new) in mutants.items():
    assert source.count(old)==1
    folder=OUT/name;folder.mkdir()
    src=folder/'mutant.c';src.write_text(source.replace(old,new));binary=folder/'check'
    with (folder/'build.log').open('w') as log:
        subprocess.run(['clang','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
            '-I'+str(ROOT/'tools'),str(src),str(ROOT/'tools/lmi-display-pipeline-v51.c'),
            str(ROOT/'tools/lmi-display-timing-v73.c'),str(ROOT/'tools/check-lmi-display-async-v80.c'),'-o',str(binary)],
            stdout=log,stderr=subprocess.STDOUT,check=True)
    with (folder/'run.log').open('w') as log:
        done=subprocess.run([str(binary)],stdout=log,stderr=subprocess.STDOUT,timeout=15)
    text=(folder/'run.log').read_text()
    assert done.returncode!=0 and 'Assertion' in text,(name,done.returncode,text)
    results.append(dict(name=name,compiled=True,returncode=done.returncode,assertion_detected=True))
    print('Detected:',name,flush=True)
for folder in ['lmi-display-async-v80-host-b','lmi-display-async-v80-tsan-a']:
    text=(ROOT/'out'/folder/'run.log').read_text()
    assert text.strip()=='PASS: 12 asynchronous integration scenarios; 512-frame stream; real pipeline/timing code'
native=json.loads((ROOT/'out/lmi-display-async-v80-native-a/result.json').read_text())
assert native['result']=='PASS' and native['scenarios']==11 and native['actual_linked_arm64_executed']
for name,digest in native['inputs'].items():assert sha(ROOT/name)==digest,name
paths=[Path(__file__),candidate/'build-audit.json',candidate/'async.elf',candidate/'async.ld',candidate/'mach.development.bcm2837',
       ROOT/'tools/lmi-display-async-v80.c',ROOT/'tools/lmi-display-async-v80.h',ROOT/'tools/check-lmi-display-async-v80.c',
       ROOT/'tools/lmi-display-pipeline-v51.c',ROOT/'tools/lmi-display-timing-v73.c',
       ROOT/'out/lmi-display-async-v80-host-b/check',ROOT/'out/lmi-display-async-v80-host-b/run.log',
       ROOT/'out/lmi-display-async-v80-tsan-a/check',ROOT/'out/lmi-display-async-v80-tsan-a/build.log',
       ROOT/'out/lmi-display-async-v80-tsan-a/run.log',ROOT/'out/lmi-display-async-v80-native-a/result.json']
report=dict(result='PASS',kernel_sha256=audit['sha256'],linked_code_reproduced=True,outside_edits_exact=True,
    host_scenarios=12,stream_frames=512,asan_ubsan=True,thread_sanitizer=True,native_scenarios=11,
    mutations_caught=results,hardware_tested=False,performance_verified=False,wifi_integrated=False,
    limitation='Concurrency, ABI and fail/retain paths use modeled OS/hardware services; physical completion and FPS remain unverified.',
    inputs={p.relative_to(ROOT).as_posix():sha(p) for p in paths})
(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: independent native rebuild, concurrency/ASan/TSan, 11 ARM64 scenarios, 3 compiled mutants',flush=True)
