"""Break actual 2D packets; the independent frame decoder must reject them."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];tools=root/'tools'
prior=root/'out/lmi-gpu-frame-v68-host'
out=root/'out/lmi-gpu-blit-v68-host';out.mkdir(exist_ok=True)
attempt=out/('attempt-'+str(len(list(out.glob('attempt-*')))+1));attempt.mkdir()
raw=(tools/'lmi-gpu-blit-v68.c').read_text()
production=(tools/'lmi-gpu-frame-v68.c').read_text()
mutations={
    'wrong-source-stride':('(pitch>>6)<<9','(4544u>>6)<<9'),
    'solid-instead-of-copy':('0x10f03000','0x10f03080'),
    'missing-source-cache-invalidate':('out[n++]=0x31;', 'out[n++]=0x19;'),
    'wrong-post-blit-CCU-flush':('event(out+n,0x1d,state,2)', 'event(out+n,0x1c,state,2)'),
    'missing-application-state-restore':('n+=save_restore(out+n,state,1);','(void)state;'),
    'missing-register-readback':('n+=save_restore(out+n,state+LMI_BLIT_READBACK_OFFSET,0);','(void)state;'),
}
flags=['clang','-std=c17','-O2','-g','-Wall','-Wextra','-Werror','-Wno-unused-function',
       '-D_POSIX_C_SOURCE=200112L','-Wno-misleading-indentation','-DLMI_PRECLEAN_HOST',
       '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(tools)]
sources=[prior/'check.c',root/'out/lmi-display-v62-host/original-compositor.c',prior/'preclean.c',
         *[tools/n for n in ['lmi-display-fast-v62.c','lmi-display-direct-plan-v61.c','lmi-display-pipeline-v51.c']]]
caught=[]
for label,(old,new) in mutations.items():
    assert old in raw
    blit=attempt/(label+'-blit.c');blit.write_text(raw.replace(old,new))
    frame=attempt/(label+'-frame.c')
    frame.write_text(production.replace('"lmi-gpu-blit-v68.c"','"'+str(blit)+'"'))
    binary=attempt/label
    with (attempt/(label+'-compile.log')).open('w') as log:
        subprocess.run([*flags,*map(str,sources),str(frame),'-o',str(binary)],check=True,stdout=log,stderr=subprocess.STDOUT)
    with (attempt/(label+'.log')).open('w') as log:
        result=subprocess.run([str(binary)],stdout=log,stderr=subprocess.STDOUT,timeout=90)
    assert result.returncode!=0,('2D mutation survived',label)
    caught.append(label)
report=dict(result='PASS',mutations_caught=caught,asan_ubsan=True,independent_packet_decode=True,
            hardware_tested=False,performance_verified=False,attempt=str(attempt.relative_to(root)),
            sources={n:hashlib.sha256((tools/n).read_bytes()).hexdigest() for n in
                     ['check-lmi-gpu-blit-v68.py','lmi-gpu-blit-v68.c','lmi-gpu-blit-v68.h','lmi-gpu-frame-v68.c']},
            fixture_sha256={str(q.relative_to(root)):hashlib.sha256(q.read_bytes()).hexdigest() for q in sources})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(caught),'actual 2D command mutations rejected')
