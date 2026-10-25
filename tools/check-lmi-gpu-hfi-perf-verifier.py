"""Model-only PERF verifier regression using recorded mode30 as scaffold."""
from pathlib import Path
import json,runpy,struct,zlib
r=Path(__file__).resolve().parents[1];p=r/'out/lmi-checkpoint-63-ios-probe-test-a650-table-plan-mode30-25'
h=json.loads((p/'hardware-test.json').read_text());s=(p/'checkpoint-63.log').read_bytes().replace(b'\0',b'').decode()
model=(r/'out/lmi-gmu-hfi-perf-host.log').read_text().split('PASS:')[0]+'LMI_GPU_HFI_PERF_RESULT\n0000000000000001\n'
s=s.replace('LMI_GPU_GMU_BOOT_STATUS\n',model+'LMI_GPU_GMU_BOOT_STATUS\n')
def crc(offset):
    b=bytearray(20480);struct.pack_into('<6I',b,0,0,54,6,12,4,4)
    for i,priority in enumerate((10,10,40,20)):
        struct.pack_into('<12I',b,24+i*48,int(i<3),0x60001000+offset+i*4096,i|(priority<<8),1024,*([0]*8))
    return f'{(0x60001000<<32)|zlib.crc32(b):016x}'
assert s.count(crc(224))==1;s=s.replace(crc(224),crc(256))
s=s.replace('LMI_GPU_RAM_SOFTWARE_WALK_OK\n','LMI_GPU_RAM_HFI_RING_OFFSET\n0000000000000100\nLMI_GPU_RAM_SOFTWARE_WALK_OK\n')
verify=runpy.run_path(str(r/'tools/verify-lmi-gpu-hfi-perf.py'))['verify'];fw=(r/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
assert verify(s,fw,h['kernel_window'])['performance_table_acknowledged']
bad=[s.replace('LMI_GPU_HFI_PERF_ACK_VERIFIED\n',''),s.replace('0000000000010304','0000000000010404'),
     s.replace('LMI_GPU_HFI_PERF_REPLY\n0000000000000040','LMI_GPU_HFI_PERF_REPLY\n0000000000000400'),
     s.replace('0000000000203b04\n0000000000000000\nLMI_GPU_HFI_PERF_ACK','0000000000100201\n0000000000000000\nLMI_GPU_HFI_PERF_ACK'),
     s.replace('0000000000203b04\n0000000000000000\nLMI_GPU_HFI_PERF_ACK','0000000000203b04\n00000000ffffffff\nLMI_GPU_HFI_PERF_ACK'),
     s.replace('LMI_GPU_HFI_PERF_RESULT\n0000000000000001','LMI_GPU_HFI_PERF_RESULT\n0000000000000000'),
     s.replace(crc(256),crc(224)),s+model]
for n,text in enumerate(bad):
    assert text!=s,n
    try:verify(text,fw,h['kernel_window'])
    except (AssertionError,ValueError,StopIteration):pass
    else:raise AssertionError(n)
print('PASS: PERF model positive +',len(bad),'negative verifier cases; no hardware claim')
