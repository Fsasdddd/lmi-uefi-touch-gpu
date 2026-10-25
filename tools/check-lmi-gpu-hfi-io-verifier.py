"""Verifier regressions using recorded mode28 plus MODEL HFI text, not hardware."""
from pathlib import Path
import copy,json,runpy
root=Path(__file__).resolve().parents[1]
snapshot=root/'out/lmi-checkpoint-63-ios-probe-test-a650-gmu-boot-25'
log=(snapshot/'checkpoint-63.log').read_bytes().replace(b'\0',b'').decode()
fw=(root/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
window=json.loads((snapshot/'hardware-test.json').read_text())['kernel_window']
verify=runpy.run_path(str(root/'tools/verify-lmi-gpu-hfi-io.py'))['verify']
model=(root/'out/lmi-gmu-hfi-io-host.log').read_text().split('PASS:')[0]
model+='LMI_GPU_HFI_IO_RESULT\n0000000000000001\n'
combined=log.replace('LMI_GPU_GMU_BOOT_STATUS\n',model+'LMI_GPU_GMU_BOOT_STATUS\n')
assert verify(combined,fw,window)['bidirectional_hfi_dma_verified']
bad=[log,combined.replace('LMI_GPU_HFI_IO_ACK_VERIFIED\n',''),
     combined.replace('0000000000100201\n0000000000000000','0000000000200201\n0000000000000000'),
     combined.replace('0000000020010008\nLMI_GPU_HFI_IO_ACK','0000000020010009\nLMI_GPU_HFI_IO_ACK'),
     combined.replace('0000000000010400\n','0000000000000400\n'),
     combined.replace('0000000000010400\n','0000000000010300\n'),
     combined.replace('LMI_GPU_HFI_IO_RESULT\n0000000000000001','LMI_GPU_HFI_IO_RESULT\n0000000000000000'),
     combined.replace('LMI_GPU_HFI_IO_REPLY\n0000000000000004','LMI_GPU_HFI_IO_REPLY\n0000000000000400'),
     combined+model,combined+'LMI_GPU_RSC_INIT_RESTORED\n']
for i,text in enumerate(bad):
    try:verify(text,fw,window)
    except (AssertionError,ValueError,IndexError):pass
    else:raise AssertionError(f'Negative case {i} accepted')
report=dict(result='PASS',positive_cases=1,negative_cases=len(bad),evidence='synthetic/model only',hardware_verified=False)
(root/'out/lmi-gmu-hfi-io-verifier-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
