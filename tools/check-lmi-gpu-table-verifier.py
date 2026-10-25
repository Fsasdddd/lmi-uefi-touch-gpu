"""Host-model table verification on recorded mode29; not an extra hardware test."""
from pathlib import Path
import json,runpy
r=Path(__file__).resolve().parents[1];p=r/'out/lmi-checkpoint-63-ios-probe-test-a650-hfi-io-mode29-retry-25'
h=json.loads((p/'hardware-test.json').read_text());log=(p/'checkpoint-63.log').read_bytes().replace(b'\0',b'').decode()
model=(r/'out/lmi-gmu-table-plan-host.log').read_text().split('LMI_GPU_TABLE_PLAN_VERIFIED\n')[0]+'LMI_GPU_TABLE_PLAN_VERIFIED\nLMI_GPU_TABLE_PLAN_RESULT\n0000000000000001\n'
log=log.replace('LMI_GPU_GMU_BOOT_STATUS\n',model+'LMI_GPU_GMU_BOOT_STATUS\n')
v=runpy.run_path(str(r/'tools/verify-lmi-gpu-table-plan.py'))['verify'];fw=(r/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
assert v(log,fw,h['kernel_window'])['performance_table_prepared']
bad=[log.replace('000000007eadb000','000000007eadb001'),log.replace('000000000004a768','000000000004a769'),
     log.replace('LMI_GPU_TABLE_PLAN_VERIFIED\n',''),log.replace('LMI_GPU_TABLE_PLAN_RESULT\n0000000000000001','LMI_GPU_TABLE_PLAN_RESULT\n0000000000000000'),
     log.replace('LMI_GPU_PLAN_BCM\n0000000000050000','LMI_GPU_PLAN_BCM\n0000000000030000'),log+model]
for n,s in enumerate(bad):
    assert s!=log,n
    try:v(s,fw,h['kernel_window'])
    except (AssertionError,ValueError,StopIteration):pass
    else:raise AssertionError(n)
print('PASS: model plan plus',len(bad),'negative verifier cases; no hardware claim')
