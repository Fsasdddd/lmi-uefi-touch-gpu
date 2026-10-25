"""GPU PAS discovery after real CP/fence proof; not firmware authentication."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-cp.py')))['verify'](log,firmware,window)
    assert result['mode']==42
    blocks=re.findall(r'LMI_GPU_SCM_QUERY\n((?:[0-9a-f]{16}\n){5})',log)
    assert len(blocks)==log.count('LMI_GPU_SCM_QUERY\n')==5, 'Missing/duplicate SCM query'
    queries=[0x42000601,0x02000201,0x02000202,0x02000205,0x02000206]
    replies=[]
    for i,block in enumerate(blocks):
        values=[int(v,16) for v in block.splitlines()]
        assert values[:4]==[0x42000601 if i else 0xc2000601,queries[i],0,1], 'SCM ABI/query/service unavailable'
        assert 1<=values[4]<=64, 'Unbounded SCM interrupt resumes'
        replies.append(values)
    assert log.count('LMI_GPU_SCM_PAS_AVAILABLE\n')==1
    assert re.findall(r'LMI_GPU_SCM_RESULT\n([0-9a-f]{16})\n',log)==['0000000000000001']
    order=['LMI_GPU_CP_FENCE_VERIFIED_HELD','LMI_GPU_CP_RESULT','LMI_GPU_SCM_QUERY',
           'LMI_GPU_SCM_PAS_AVAILABLE','LMI_GPU_SCM_RESULT','LMI_GPU_CORE_MEMORY_RESULT']
    positions=[log.index(m+'\n') for m in order];assert positions==sorted(positions)
    result.update(mode=43,scm64_convention_verified=True,pas_service_availability_verified=True,
                  scm_queries=replies,pas_state_changed=False,zap_authenticated=False)
    return result
