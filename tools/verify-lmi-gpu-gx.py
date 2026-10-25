"""Mode33 HFI START/DCVS + fresh GPU OOB and GX on; no submit/pixels proof."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-hfi-core.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_HFI_START_REQUEST',1)==[0x50010a]
    assert rows('LMI_GPU_HFI_DCVS_REQUEST',4)==[0x60041e,1,1,0xff]
    for label,indices,header in [('START',[232,232,16,20,1],0x50010a),('DCVS',[236,236,20,24,1],0x60041e)]:
        reply=rows('LMI_GPU_HFI_'+label+'_REPLY',8)
        assert reply[:5]==indices and reply[5]&0xfff00==0x10300 and reply[6:]==[header,0]
        assert log.count('LMI_GPU_HFI_'+label+'_ACK_VERIFIED\n')==1
    assert rows('LMI_GPU_GX_OOB_REQUEST',1)==[0x40000000]
    assert rows('LMI_GPU_GX_OOB_REPLY',1)==[0x80000000]
    before=rows('LMI_GPU_GX_BEFORE',1)[0];after=rows('LMI_GPU_GX_AFTER',1)[0]
    assert not after&0xc0 and rows('LMI_GPU_GX_RESULT',1)==[1]
    assert log.count('LMI_GPU_GX_OOB_HELD\n')==1
    order=['LMI_GPU_HFI_CORE_RESULT','LMI_GPU_HFI_START_REQUEST','LMI_GPU_HFI_START_REPLY','LMI_GPU_HFI_START_ACK_VERIFIED',
           'LMI_GPU_HFI_DCVS_REQUEST','LMI_GPU_HFI_DCVS_REPLY','LMI_GPU_HFI_DCVS_ACK_VERIFIED','LMI_GPU_GX_BEFORE',
           'LMI_GPU_GX_OOB_REQUEST','LMI_GPU_GX_OOB_REPLY','LMI_GPU_GX_AFTER','LMI_GPU_GX_OOB_HELD','LMI_GPU_GX_RESULT','LMI_GPU_GMU_BOOT_STATUS']
    pos=[log.index(m+'\n') for m in order];assert pos==sorted(pos)
    result.update(mode=33,hfi_start_acknowledged=True,lowest_frequency_request_acknowledged=True,frequency_index=1,
                  gpu_oob_acknowledged=True,gpu_oob_held=True,gx_power_requested=True,gx_power_clock_on=True,
                  gx_status_before=before,gx_status_after=after,hardware_acceleration_verified=False)
    return result
