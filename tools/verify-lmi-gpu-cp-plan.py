"""Read-only powered CP/CB1 snapshot after real GX OOB; no CP submit proof."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-gx.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    regs=rows('LMI_GPU_CP_PLAN_REGISTERS',17)
    cp=[0x210,0x213,0x201,0x800,0x801,0x802,0x804,0x805,0x806,0x807,0x808,0x821,0x823,0x824,0x825,0x830,0x831]
    assert [v>>32 for v in regs]==[0x3d00000+4*x for x in cp]
    streams=rows('LMI_GPU_CP_PLAN_STREAMS',12)
    assert [v>>32 for v in streams]==[a for n in range(6) for a in (0x3da0800+4*n,0x3da0c00+4*n)]
    assert streams[0]&0xffffffff==0x84000005
    assert all(streams[n]&0xffffffff==0 for n in range(2,12,2))
    cb=rows('LMI_GPU_CP_PLAN_CB1',13)
    offsets=[0x1804,0x1004,0x9000,0x9010,0x9030,0x9020,0x9024,0x9028,0x902c,0x9038,0x903c,0x9058,0x48]
    assert [v>>32 for v in cb]==[0x3da0000+x for x in offsets]
    values=[v&0xffffffff for v in cb]
    assert not values[2]&1 and values[11:]==[0,0]
    assert rows('LMI_GPU_CP_PLAN_RESULT',1)==[1] and log.count('LMI_GPU_CP_PLAN_IDLE_CB1\n')==1
    order=['LMI_GPU_GX_OOB_HELD','LMI_GPU_CP_PLAN_REGISTERS','LMI_GPU_CP_PLAN_STREAMS','LMI_GPU_CP_PLAN_CB1',
           'LMI_GPU_CP_PLAN_IDLE_CB1','LMI_GPU_CP_PLAN_RESULT','LMI_GPU_GX_RESULT']
    pos=[log.index(m+'\n') for m in order];assert pos==sorted(pos)
    result.update(mode=34,cp_registers={hex(a):v&0xffffffff for a,v in zip(cp,regs)},cb1_snapshot=values,
                  core_streams_snapshot=streams,cb1_idle_candidate=True,cp_started=False)
    return result
