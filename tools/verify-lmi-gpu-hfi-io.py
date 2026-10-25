"""Mode29 one-shot FW_VER DMA proof; requires the complete mode28 proof."""
from pathlib import Path
import re,runpy

def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-boot.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1, 'Missing/duplicate '+marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log)
        assert m, 'Incomplete '+marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_HFI_IO_REQUEST',4)==[0x00100201,0x20000000,0xfafafafa,0xfafafafa]
    reply=rows('LMI_GPU_HFI_IO_REPLY',9)
    assert reply[:5]==[4,4,0,4,1], 'Stale/out-of-range indices or IRQ'
    assert reply[5]&0xfff00==0x10400 and reply[6:]==[0x00100201,0,0x20010008], 'Wrong ACK type/size/echo/result/version'
    assert rows('LMI_GPU_HFI_IO_RESULT',1)==[1]
    assert log.count('LMI_GPU_HFI_IO_ACK_VERIFIED\n')==1
    order=['LMI_GPU_GMU_BOOT_HFI_READY','LMI_GPU_HFI_IO_REQUEST','LMI_GPU_HFI_IO_REPLY',
           'LMI_GPU_HFI_IO_ACK_VERIFIED','LMI_GPU_HFI_IO_RESULT','LMI_GPU_GMU_BOOT_STATUS']
    positions=[log.index(m+'\n') for m in order];assert positions==sorted(positions)
    result.update(mode=29,bidirectional_hfi_dma_verified=True,fw_version=hex(reply[8]),
                  request_echo=hex(reply[6]),ack_header=hex(reply[5]),hardware_acceleration_verified=False)
    return result
