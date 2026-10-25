"""Verify reversible GMU clock configuration evidence, never measured frequency."""
import re

def verify(log,active=False):
    def rows(marker,count,addresses):
        assert log.count(marker+'\n')==1, 'Missing/duplicate '+marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log)
        assert m, 'Incomplete '+marker
        values=[int(v,16) for v in m[1].splitlines()]
        assert [v>>32 for v in values]==addresses, 'Clock address/order mismatch'
        return [v&0xffffffff for v in values]
    source=rows('LMI_GPU_GMU_200MHZ_SOURCE',9,[0x100000,0x100004,0x100040,0x10000c,0x100038,0x152000,0x3d91124,0x3d91120,0x3d7e000])
    actual=rows('LMI_GPU_GMU_200MHZ_ACTUAL',3,[0x3d91124,0x3d91120,0x152000])
    restored=[]
    if active:
        assert 'LMI_GPU_GMU_200MHZ_RESTORED' not in log and 'LMI_GPU_GMU_200MHZ_RESTORE_OK' not in log
        assert re.search(r'LMI_GPU_GMU_200MHZ_RESULT\n0000000000000003\n',log)
    else:
        restored=rows('LMI_GPU_GMU_200MHZ_RESTORED',3,[0x3d91124,0x3d91120,0x152000])
        assert log.count('LMI_GPU_GMU_200MHZ_RESTORE_OK\n')==1
        assert re.search(r'LMI_GPU_GMU_200MHZ_RESULT\n0000000000000001\n',log)
    hz=19200000*source[1]+((19200000*source[2])>>16)
    running=source[0]&0x40000000 if source[0]&0x100000 else source[4]&1
    assert source[0]&0x80000001==0x80000001 and running and source[2]<=0xffff
    assert (source[3]>>8)&15==1 and 599999000<=hz<=600001000
    assert source[6]&0x10371f==1 and not source[7]&1 and source[8]==1
    assert actual[0]==(source[6]&~0x10371f)|0x100602 and not actual[1]&1 and actual[2]&0x10000
    if not active:assert restored[0]==source[6] and not restored[1]&1
    if not active:assert restored[2]&0x10000==source[5]&0x10000
    return dict(mode=28 if active else 26,source_registers=source,actual_registers=actual,restored_registers=restored,
                parent_calculated_hz=hz,gmu_calculated_hz=hz/3,configuration_verified=True,
                original_config_and_owned_gate_restored=not active,dependencies_retained_active=active,pll_written=False,
                frequency_measured=False,firmware_execution=active,hardware_acceleration_verified=False)
