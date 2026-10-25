"""Mode39 read-only power, reset and access census; no GPU execution claim."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-core-memory.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    groups=[('CC',0x3d90000,[0x100,0x104,0x138,0x1008,0x100c,0x1064,0x1068,0x106c,0x1078,0x1088,0x1098,0x109c,0x10a0,0x111c,0x1120,0x1124,0x1508,0x1540,0x5000]),
            ('GPU',0x3d00000,[4*v for v in [0,1,0x16,0x17,0x18,0x43,0x45,0x46,0xae,0x210,0x213,0x215,0x842,0x8c1,0x8c2,0x8c3,0x98d,0xa00]]),
            ('GMU',0x3d6a000,[0x200,0x14340,0x143b0,0x24c40,0x24c44,0x24c48,0x24c4c,0x24c54,0x14648,0x24c14])]
    snapshots={}
    for name,base,offsets in groups:
        raw=rows('LMI_GPU_CORE_ACCESS_'+name,len(offsets))
        assert [v>>32 for v in raw]==[base+off for off in offsets]
        snapshots[name]={hex(base+off):v&0xffffffff for off,v in zip(offsets,raw)}
    g=snapshots['GMU'];assert not g['0x3d7e340']&0xc0 and g['0x3d8ec4c']==0 and g['0x3d7e648']==0 and not g['0x3d8ec14']&0x29
    assert rows('LMI_GPU_CORE_ACCESS_RESULT',1)==[1]
    order=['LMI_GPU_CORE_MEMORY_RETAINED','LMI_GPU_CORE_ACCESS_CC','LMI_GPU_CORE_ACCESS_GPU','LMI_GPU_CORE_ACCESS_GMU',
           'LMI_GPU_CORE_ACCESS_READONLY_HELD','LMI_GPU_CORE_ACCESS_RESULT','LMI_GPU_CORE_MEMORY_RESULT']
    assert all(log.count(m+'\n')==1 for m in order)
    assert [log.index(m+'\n') for m in order]==sorted(log.index(m+'\n') for m in order)
    for m in ['LMI_GPU_CP_CONFIG','LMI_GPU_CP_SQE_START','LMI_GPU_CP_SP_CLOCK_ENABLED','LMI_GPU_CP_FENCE_VERIFIED_HELD']:
        assert m+'\n' not in log
    result.update(mode=39,core_access_readonly=True,core_access=snapshots,cp_started=False,hardware_acceleration_verified=False)
    return result
