"""Mode31: PERF_TBL accepted; neither GX power nor rendering is proven."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-table-plan.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    request=rows('LMI_GPU_HFI_PERF_REQUEST',59)
    assert request==[0x203b04]+result['performance_table'][1:]
    reply=rows('LMI_GPU_HFI_PERF_REPLY',8)
    assert reply[:5]==[64,64,4,8,1] and reply[5]&0xfff00==0x10300 and reply[6:]==[0x203b04,0]
    if 'LMI_GPU_RAM_HFI_RING_OFFSET\n' in log:assert rows('LMI_GPU_RAM_HFI_RING_OFFSET',1)==[256]
    assert result['route']['hfi_ring_offset']==256
    assert rows('LMI_GPU_HFI_PERF_RESULT',1)==[1] and log.count('LMI_GPU_HFI_PERF_ACK_VERIFIED\n')==1
    order=['LMI_GPU_TABLE_PLAN_RESULT','LMI_GPU_HFI_PERF_REQUEST','LMI_GPU_HFI_PERF_REPLY',
           'LMI_GPU_HFI_PERF_ACK_VERIFIED','LMI_GPU_HFI_PERF_RESULT','LMI_GPU_GMU_BOOT_STATUS']
    pos=[log.index(m+'\n') for m in order];assert pos==sorted(pos)
    result.update(mode=31,performance_table_sent=True,performance_table_acknowledged=True,hfi_headers_isolated_from_payload=True)
    return result
