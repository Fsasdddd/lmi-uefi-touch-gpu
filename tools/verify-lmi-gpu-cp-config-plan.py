"""Mode41: stopped-CP config observations, including mismatches, never submit proof."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-core-memory.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_GMU_FAL_VETO',2)[1]==1 and rows('LMI_GPU_CP_AHB_FENCE_ALLOW',1)==[0]
    settings=[(0x842,1),(0x8c2,0x02000140),(0x8c1,0x8040362c),(0x8c3,128),(0x98d,1),(0x844,0x6e),
              (0x830,0x1008000),(0x831,0),(0x800,0x1000000),(0x801,0),(0x802,0x0800020c)]
    observations=[]
    for name in ['LMI_GPU_CP_CONFIG','LMI_GPU_CP_CONFIG_DELAYED']:
        raw=rows(name,11);assert [v>>32 for v in raw]==[0x3d00000+4*a for a,v in settings]
        observations.append([v&0xffffffff for v in raw])
    mask=sum(1<<n for n,((a,v),actual) in enumerate(zip(settings,observations[1])) if actual==v)
    assert rows('LMI_GPU_CP_CONFIG_MATCH_MASK',1)==[mask] and rows('LMI_GPU_CP_RESULT',1)==[1]
    assert rows('LMI_GPU_CP_CONFIG_STOPPED',3)==[0,0,0]
    order=['LMI_GPU_GMU_BOOT_BEGIN','LMI_GPU_GMU_FAL_VETO','LMI_GPU_GMU_BOOT_TCM_MISMATCHES',
           'LMI_GPU_CORE_MEMORY_RETAINED','LMI_GPU_CP_INIT_PACKET','LMI_GPU_CP_CONFIG','LMI_GPU_CP_CONFIG_DELAYED',
           'LMI_GPU_CP_CONFIG_MATCH_MASK','LMI_GPU_CP_CONFIG_STOPPED','LMI_GPU_CP_CONFIG_STOPPED_HELD','LMI_GPU_CP_RESULT','LMI_GPU_CORE_MEMORY_RESULT']
    assert all(log.count(m+'\n')==1 for m in order)
    assert [log.index(m+'\n') for m in order]==sorted(log.index(m+'\n') for m in order)
    for m in ['LMI_GPU_CP_SQE_START','LMI_GPU_CP_INIT_VERIFIED','LMI_GPU_CP_FENCE_VERIFIED_HELD']:
        assert m+'\n' not in log
    result.update(mode=41,cp_config_observations=observations,cp_config_match_mask=mask,cp_config_matches_all=mask==0x7ff,
                  cp_started=False,gpu_fence_verified=False,hardware_acceleration_verified=False)
    return result
