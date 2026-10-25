"""Synthetic regression only; never substitute modeled GX output for hardware."""
from pathlib import Path
import json,runpy
r=Path(__file__).resolve().parents[1];p=r/'out/lmi-checkpoint-63-ios-probe-test-a650-hfi-core-mode32-25'
h=json.loads((p/'hardware-test.json').read_text());s=(p/'checkpoint-63.log').read_bytes().replace(b'\0',b'').decode()
model=(r/'out/lmi-gmu-gx-host.log').read_text().split('PASS:')[0]+'LMI_GPU_GX_RESULT\n0000000000000001\n'
s=s.replace('LMI_GPU_GMU_BOOT_STATUS\n',model+'LMI_GPU_GMU_BOOT_STATUS\n')
verify=runpy.run_path(str(r/'tools/verify-lmi-gpu-gx.py'))['verify'];fw=(r/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
assert verify(s,fw,h['kernel_window'])['gpu_oob_acknowledged']
bad=[s.replace('LMI_GPU_HFI_START_ACK_VERIFIED\n',''),s.replace('LMI_GPU_HFI_DCVS_ACK_VERIFIED\n',''),
     s.replace('LMI_GPU_GX_OOB_REPLY\n0000000080000000','LMI_GPU_GX_OOB_REPLY\n0000000080000001'),
     s.replace('LMI_GPU_GX_AFTER\n0000000000000028','LMI_GPU_GX_AFTER\n0000000000000068'),
     s.replace('LMI_GPU_GX_OOB_HELD\n',''),s.replace('LMI_GPU_GX_RESULT\n0000000000000001','LMI_GPU_GX_RESULT\n0000000000000000'),
     s.replace('000000000060041e\n0000000000000001\n0000000000000001\n00000000000000ff','000000000060041e\n0000000000000001\n0000000000000007\n00000000000000ff'),s+model]
for n,text in enumerate(bad):
    assert text!=s,n
    try:verify(text,fw,h['kernel_window'])
    except (AssertionError,ValueError,StopIteration):pass
    else:raise AssertionError(n)
print('PASS: synthetic GX model +',len(bad),'negative verifier cases; no hardware claim')
