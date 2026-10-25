"""SQE command fetch, ME_INIT, and GPU-only memory writeback proof."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-core-memory.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_CP_INIT_PACKET',9)==[0x70c80008,0x2f,3,0x20000000,0,0,0,0,0]
    assert rows('LMI_GPU_CP_WRITE_PACKET',4)==[0x703d8003,0x1010000,0,0x650c0de1]
    settings=[(0x842,1),(0x8c2,0x02000140),(0x8c1,0x8040362c),(0x8c3,128),(0x98d,1),(0x844,0x6e),
              (0x830,0x1008000),(0x831,0),(0x800,0x1000000),(0x801,0),(0x802,0x0800020c)]
    expected=[((0x3d00000+4*a)<<32)|v for a,v in settings]
    actual=rows('LMI_GPU_CP_CONFIG',11)
    if 'LMI_GPU_CP_CONFIG_READY\n' in log:
        assert actual[:1]+actual[2:]==expected[:1]+expected[2:]
        assert actual[1] in (expected[1],expected[1]&~0xffffffff)
        assert rows('LMI_GPU_CP_CONFIG_DELAYED',11)==expected
        assert rows('LMI_GPU_CP_CONFIG_MATCH_MASK',1)==[0x7ff]
        assert rows('LMI_GPU_CP_CONFIG_STOPPED',3)==[0,0,0]
        ready_order=['LMI_GPU_CP_CONFIG','LMI_GPU_CP_CONFIG_DELAYED','LMI_GPU_CP_CONFIG_MATCH_MASK',
                     'LMI_GPU_CP_CONFIG_STOPPED','LMI_GPU_CP_CONFIG_READY','LMI_GPU_CP_SQE_START']
        assert all(log.count(m+'\n')==1 for m in ready_order)
        assert [log.index(m+'\n') for m in ready_order]==sorted(log.index(m+'\n') for m in ready_order)
        assert 'LMI_GPU_CP_CONFIG_STOPPED_HELD\n' not in log
    else:
        assert actual==expected
    all_status=re.findall(r'LMI_GPU_CP_STATUS\n((?:[0-9a-f]{16}\n){14})',log)
    assert len(all_status)==log.count('LMI_GPU_CP_STATUS\n')==2
    for text,target in zip(all_status,[9,13]):
        values=[int(v,16) for v in text.splitlines()];assert values[0]==target
        offsets=[0x210,0x201,0x806,0x807,0x808,0x821,0x823,0x824]
        assert [v>>32 for v in values[1:9]]==[0x3d00000+4*a for a in offsets]
        status=[v&0xffffffff for v in values[1:9]]
        assert not status[0]&~1 and status[1]==0 and status[2:5]==[target,target,1] and status[5:]==[0,0,0]
        assert [v>>32 for v in values[9:]]==[0x3da9058,0x3da9060,0x3da9064,0x3da9068,0x3da0048]
        assert values[9]&0xffffffff==0x400 and values[13]&0xffffffff==0
    assert rows('LMI_GPU_CP_FENCE',1)==[0x650c0de1] and rows('LMI_GPU_CP_RESULT',1)==[1]
    order=['LMI_GPU_CORE_MEMORY_RETAINED','LMI_GPU_CP_INIT_PACKET','LMI_GPU_CP_CONFIG','LMI_GPU_CP_SQE_START',
           'LMI_GPU_CP_INIT_VERIFIED','LMI_GPU_CP_WRITE_PACKET','LMI_GPU_CP_FENCE','LMI_GPU_CP_FENCE_VERIFIED_HELD','LMI_GPU_CP_RESULT','LMI_GPU_CORE_MEMORY_RESULT']
    assert all(log.count(m+'\n')==1 for m in order)
    pos=[log.index(m+'\n') for m in order];assert pos==sorted(pos)
    mode=36
    if 'LMI_GPU_CP_AHB_FENCE_ALLOW\n' in log:
        assert rows('LMI_GPU_CP_AHB_FENCE_ALLOW',1)==[0]
        rows('LMI_GPU_CP_AHB_FENCE_BEFORE',1)
        assert log.index('LMI_GPU_CP_AHB_FENCE_ALLOW\n')<log.index('LMI_GPU_CP_INIT_PACKET\n')
        mode=37
    if 'LMI_GPU_CP_SP_CLOCK_ENABLED\n' in log:
        before=rows('LMI_GPU_CP_SP_CLOCK_BEFORE',1)[0]
        assert rows('LMI_GPU_CP_SP_CLOCK_ENABLED',1)==[before|1]
        assert mode==37 and log.index('LMI_GPU_CP_SP_CLOCK_ENABLED\n')<log.index('LMI_GPU_CP_INIT_PACKET\n')
        mode=38
    if 'LMI_GPU_GMU_FAL_VETO\n' in log:
        before,after=rows('LMI_GPU_GMU_FAL_VETO',2)
        assert after==1 and mode==37
        assert log.index('LMI_GPU_GMU_BOOT_BEGIN\n')<log.index('LMI_GPU_GMU_FAL_VETO\n')<log.index('LMI_GPU_GMU_BOOT_TCM_MISMATCHES\n')
        mode=40
    if 'LMI_GPU_CP_CONFIG_READY\n' in log:
        assert mode==40
        mode=42
    result.update(mode=mode,cp_started=True,cp_init_verified=True,core_dma_verified=True,gpu_memory_writeback_verified=True,
                  gpu_fence_value=0x650c0de1,gpu_secure_mode_changed=False,hardware_acceleration_verified=False)
    return result
