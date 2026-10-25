"""Synthetic CP verifier regression; modeled output is never hardware proof."""
from pathlib import Path
import json,runpy
r=Path(__file__).resolve().parents[1]
p=r/'out/lmi-checkpoint-63-ios-probe-test-a650-core-memory-mode35-25'
h=json.loads((p/'hardware-test.json').read_text())
s=(p/'checkpoint-63.log').read_bytes().replace(b'\0',b'').decode()
model=(r/'out/lmi-gmu-cp-sp-clock-host.log').read_text().split('PASS:')[0]
model+='LMI_GPU_CP_RESULT\n0000000000000001\n'
s=s.replace('LMI_GPU_CORE_MEMORY_RESULT\n',model+'LMI_GPU_CORE_MEMORY_RESULT\n')
verify=runpy.run_path(str(r/'tools/verify-lmi-gpu-cp.py'))['verify']
fw=(r/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
assert verify(s,fw,h['kernel_window'])['mode']==38
bad=[s.replace('LMI_GPU_CP_SP_CLOCK_ENABLED\n0000000000000001','LMI_GPU_CP_SP_CLOCK_ENABLED\n0000000000000000'),
     s.replace('LMI_GPU_CP_SP_CLOCK_BEFORE\n0000000000000000','LMI_GPU_CP_SP_CLOCK_BEFORE\n0000000000000002'),
     s.replace('LMI_GPU_CP_INIT_VERIFIED\n',''),
     s.replace('LMI_GPU_CP_FENCE\n00000000650c0de1','LMI_GPU_CP_FENCE\n0000000000000000'),
     s.replace('03d0210800000001','03d0210800000000'),s+model]
for n,text in enumerate(bad):
    assert text!=s,n
    try:verify(text,fw,h['kernel_window'])
    except (AssertionError,ValueError,StopIteration):pass
    else:raise AssertionError(n)
print('PASS: synthetic CP/SP model and',len(bad),'negative cases; no hardware claim')
