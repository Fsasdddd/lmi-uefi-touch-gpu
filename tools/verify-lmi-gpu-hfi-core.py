"""Mode32 BW table + CORE_FW_START ACK; no GX request or GPU submit proof."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-hfi-perf.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    bcm=result['bcm_addresses'];expected=[0]*160
    expected[:6]=[0x30a003,1,1,3,1,1];expected[6]=bcm[3]
    expected[12]=0x40000000;expected[18]=0x60000001
    expected[24:27]=[bcm[1],bcm[0],bcm[2]];expected[32:35]=[0x40000000]*3
    assert rows('LMI_GPU_HFI_BW_REQUEST',160)==expected
    assert rows('LMI_GPU_HFI_CORE_REQUEST',2)==[0x40020e,0]
    for label,indices,header in [('BW',[224,224,8,12,1],0x30a003),('CORE',[228,228,12,16,1],0x40020e)]:
        reply=rows('LMI_GPU_HFI_'+label+'_REPLY',8)
        assert reply[:5]==indices and reply[5]&0xfff00==0x10300 and reply[6:]==[header,0]
        assert log.count('LMI_GPU_HFI_'+label+'_ACK_VERIFIED\n')==1
    assert rows('LMI_GPU_HFI_CORE_RESULT',1)==[1] and rows('LMI_GPU_RAM_HFI_RING_OFFSET',1)==[256]
    order=['LMI_GPU_HFI_PERF_RESULT','LMI_GPU_HFI_BW_REQUEST','LMI_GPU_HFI_BW_REPLY','LMI_GPU_HFI_BW_ACK_VERIFIED',
           'LMI_GPU_HFI_CORE_REQUEST','LMI_GPU_HFI_CORE_REPLY','LMI_GPU_HFI_CORE_ACK_VERIFIED','LMI_GPU_HFI_CORE_RESULT','LMI_GPU_GMU_BOOT_STATUS']
    pos=[log.index(m+'\n') for m in order];assert pos==sorted(pos)
    result.update(mode=32,bandwidth_table_acknowledged=True,bandwidth_levels=1,bandwidth_scaling=False,
                  core_firmware_start_acknowledged=True,gx_power_requested=False,hardware_acceleration_verified=False)
    return result
