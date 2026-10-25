"""Mode28: fresh GMU firmware/HFI replies with all DMA dependencies retained.
Successful firmware boot still does not verify CP submit/fence/pixels.
"""
from pathlib import Path
import re,runpy

def verify(log,firmware,window=None):
    def rows(marker,count):
        assert log.count(marker+'\n')==1, 'Missing/duplicate '+marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log)
        assert m, 'Incomplete '+marker
        return [int(v,16) for v in m[1].splitlines()]
    def scalar(marker,value):assert rows(marker,1)==[value],marker
    for marker,value in [('LMI_GPU_EXEC_CANARY',0x7ea61d23),('LMI_GPU_GMU_BOOT_TCM_MISMATCHES',0),
            ('LMI_GPU_GMU_BOOT_FW_READY',1),('LMI_GPU_GMU_BOOT_HFI_READY',1),('LMI_GPU_GMU_BOOT_RESULT',3),
            ('LMI_GPU_RAM_CONSUMER_RESULT',3),('LMI_GPU_GMU_ROUTE_RESULT',3),
            ('LMI_GPU_GMU_200MHZ_RESULT',3),('LMI_GPU_RSC_INIT_RESULT',3)]:scalar(marker,value)
    config=rows('LMI_GPU_GMU_BOOT_CONFIG',14)
    expected=[(0x14730,1),(0x14070,0),(0x14004,2),(0x14614,0x60001000),(0x14610,1),
        (0x24c44,0x80a008a0),(0x14608,0x06050200),(0x14400,0x60000000),
        (0x1303c,1),(0x13000,1),(0x13004,1),(0x14300,0x9c40400),(0x143a0,0xf11),(0x14404,0)]
    assert config==[((0x3d6a000+a)<<32)|v for a,v in expected], 'Boot config differs from source-defined settings'
    raw=rows('LMI_GPU_GMU_BOOT_STATUS',14)
    offsets=[0x14000,0x14070,0x14068,0x14600,0x14604,0x24c14,0x24c4c,0x143b0,0xafdc,0xafe0]
    assert [v>>32 for v in raw]==[0x3d6a000+a for a in offsets]+[0x3da8058,0x3da8060,0x3da8064,0x3da0048]
    status=[v&0xffffffff for v in raw]
    assert status[0]==0 and status[1]&0x1ff==0x100 and status[3]&1, 'Firmware/HFI response not fresh or ready'
    assert status[9]==0x20010008 and status[10]==0x400 and status[13]==0, 'Core version or SMMU faults differ'
    # AO watchdog/fence/AHB errors, per pinned kgsl_gmu.h, cannot count as success.
    assert status[5]&0x29==0 and status[6]==0, 'GMU AO/fence error'
    assert log.count('LMI_GPU_GMU_BOOT_ACTIVE_HELD\n')==1
    assert all(v not in log for v in ('LMI_GPU_RSC_INIT_RESTORED','LMI_GPU_CX_RESTORED_STATUS',
        'LMI_GPU_CLOCK_RESTORE_OFFSET','LMI_GPU_CX_POWER_END','LMI_GPU_CLOCK_END'))
    markers=['LMI_GPU_GMU_ROUTE_ACTUAL','LMI_GPU_EXEC_CANARY','LMI_GPU_GMU_BOOT_BEGIN',
        'LMI_GPU_GMU_BOOT_TCM_MISMATCHES','LMI_GPU_GMU_BOOT_CONFIG','LMI_GPU_GMU_BOOT_RELEASE',
        'LMI_GPU_GMU_BOOT_FW_READY','LMI_GPU_GMU_BOOT_HFI_READY','LMI_GPU_GMU_BOOT_STATUS',
        'LMI_GPU_GMU_BOOT_ACTIVE_HELD','LMI_GPU_RAM_ACTIVE_RETAINED','LMI_GPU_RSC_INIT_RESULT']
    positions=[log.index(m+'\n') for m in markers];assert positions==sorted(positions)
    assert (rows('LMI_GPU_CX_POWER_STATUS',1)[0]|rows('LMI_GPU_CX_HW_STATUS',1)[0])&0x80000000
    clocks=re.findall(r'LMI_GPU_CLOCK_OFFSET\n([0-9a-f]{16})\nLMI_GPU_CLOCK_STATUS\n([0-9a-f]{16})\n',log)
    assert {int(k,16) for k,v in clocks}=={0x1078,0x109c,0x1098}
    assert all(not int(v,16)&0x80000000 for k,v in clocks if int(k,16)!=0x1078)
    assert rows('LMI_GPU_CLOCK_SOURCE',1)[0]&0x371f==1
    def load(name):return runpy.run_path(str(Path(__file__).with_name(name)))['verify']
    route=load('verify-lmi-gpu-route.py')(log,firmware,window,active=True)
    clock=load('verify-lmi-gpu-clock.py')(log,active=True)
    rsc=load('verify-lmi-gpu-rsc-init.py')(log,sequence_only=True,pdc_enable=True,vote_probe=True,clock_probe=True,route_probe=True,active=True)
    return dict(mode=28,firmware_reply_verified=True,hfi_reply_verified=True,code_padding_execution_verified=True,
        boot_config=config,status=status,route=route,clock=clock,rsc=rsc,
        dependencies_retained_until_bounded_reset=True,hardware_acceleration_verified=False)
