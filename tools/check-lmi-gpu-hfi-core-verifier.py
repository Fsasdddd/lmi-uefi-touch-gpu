"""Model-only BW/core verifier regression; original mode31 evidence intact."""
from pathlib import Path
import json,runpy
r=Path(__file__).resolve().parents[1];p=r/'out/lmi-checkpoint-63-ios-probe-test-a650-hfi-perf-mode31-25'
h=json.loads((p/'hardware-test.json').read_text());s=(p/'checkpoint-63.log').read_bytes().replace(b'\0',b'').decode()
model=(r/'out/lmi-gmu-hfi-core-host.log').read_text().split('PASS:')[0]+'LMI_GPU_HFI_CORE_RESULT\n0000000000000001\n'
s=s.replace('LMI_GPU_GMU_BOOT_STATUS\n',model+'LMI_GPU_GMU_BOOT_STATUS\n')
s=s.replace('LMI_GPU_RAM_SOFTWARE_WALK_OK\n','LMI_GPU_RAM_HFI_RING_OFFSET\n0000000000000100\nLMI_GPU_RAM_SOFTWARE_WALK_OK\n')
verify=runpy.run_path(str(r/'tools/verify-lmi-gpu-hfi-core.py'))['verify'];fw=(r/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
assert verify(s,fw,h['kernel_window'])['core_firmware_start_acknowledged']
bad=[s.replace('LMI_GPU_HFI_CORE_ACK_VERIFIED\n',''),s.replace('LMI_GPU_HFI_BW_ACK_VERIFIED\n',''),
     s.replace('000000000030a003\n0000000000000000\nLMI_GPU_HFI_BW_ACK','0000000000203b04\n0000000000000000\nLMI_GPU_HFI_BW_ACK'),
     s.replace('000000000040020e\n0000000000000000\nLMI_GPU_HFI_CORE_ACK','000000000040020e\n00000000ffffffff\nLMI_GPU_HFI_CORE_ACK'),
     s.replace('LMI_GPU_HFI_CORE_RESULT\n0000000000000001','LMI_GPU_HFI_CORE_RESULT\n0000000000000000'),
     s.replace('LMI_GPU_HFI_BW_REPLY\n00000000000000e0','LMI_GPU_HFI_BW_REPLY\n0000000000000400'),
     s.replace('LMI_GPU_HFI_CORE_REQUEST\n000000000040020e','LMI_GPU_HFI_CORE_REQUEST\n000000000040021e'),s+model]
for n,text in enumerate(bad):
    assert text!=s,n
    try:verify(text,fw,h['kernel_window'])
    except (AssertionError,ValueError,StopIteration):pass
    else:raise AssertionError(n)
print('PASS: BW/core model +',len(bad),'negative verifier cases; no hardware claim')
