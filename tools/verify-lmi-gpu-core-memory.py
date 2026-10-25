"""Mode35 independent GPU backing and CB1 attach; CP remains stopped."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-cp-plan.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    memory=rows('LMI_GPU_CORE_MEMORY',24);base,span,page,bytes_,*pas=memory
    assert base>=0x100000000 and span==0x180000000 and page in (4096,16384) and bytes_==81920
    assert len(set(pas))==20 and all(p&4095==0 and p>>36==0 and base<=p<=base+span-4096 for p in pas)
    gmu=rows('LMI_GPU_RAM_LIVE_MAP',52)
    assert memory[:3]==gmu[:3] and not set(pas)&set(gmu[5:])
    assert rows('LMI_GPU_CORE_LAYOUT',4)==[0x1000000,0x1008000,0x1010000,0x097dc176]
    raw=rows('LMI_GPU_CORE_ATTACH_ACTUAL',15)
    offsets=[0x1804,0x1004,0x9010,0x9030,0x9020,0x9024,0x9028,0x902c,0x9038,0x903c,0x9000,0xc04,0x804,0x9058,0x48]
    assert [v>>32 for v in raw]==[0x3da0000+a for a in offsets]
    old=result['core_streams_snapshot'][3]&0xffffffff
    expected=[1,0x1f300,0x38071,0x803519,pas[17]&0xffffffff,pas[17]>>32|0x20000,0,0,0xf404ff44,0,0xc000e7,(old&~0x030303ff)|0x301,0x84010000,0x400,0]
    assert [v&0xffffffff for v in raw]==expected
    assert rows('LMI_GPU_CORE_MEMORY_RESULT',1)==[1]
    order=['LMI_GPU_CP_PLAN_RESULT','LMI_GPU_CORE_MEMORY','LMI_GPU_CORE_LAYOUT','LMI_GPU_CORE_SOFTWARE_TABLES_OK',
           'LMI_GPU_CORE_ATTACH_BEGIN','LMI_GPU_CORE_ATTACH_ACTUAL','LMI_GPU_CORE_ATTACHED_HELD','LMI_GPU_CORE_MEMORY_RETAINED','LMI_GPU_CORE_MEMORY_RESULT','LMI_GPU_GX_RESULT']
    assert all(log.count(m+'\n')==1 for m in order)
    pos=[log.index(m+'\n') for m in order];assert pos==sorted(pos)
    result.update(mode=35,core_backing_pages=pas,core_context=1,core_asid=2,core_stream_id=0,core_stream_mask=0x401,
                  core_translation_configured=True,sqe_backing_verified=True,core_dma_verified=False,cp_started=False)
    return result
