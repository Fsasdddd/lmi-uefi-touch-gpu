"""Owned contiguous Normal-NC GPU13 MDT accepted by PAS_INIT_IMAGE only."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-cp.py')))['verify'](log,firmware,window)
    assert result['mode']==42 and 'LMI_GPU_SCM_QUERY\n' not in log
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    pool,physical,allocated,page=rows('LMI_GPU_ZAP_METADATA_CLAIM',4)
    assert page in (4096,16384) and pool>=0xfffffff000000000 and pool%page==physical%page==0
    assert physical>>36==0 and allocated==((6860+page-1)//page)*page
    if window:
        base=int(window['base'],16);span=int(window['size'],16)
        assert base<=physical<=base+span-allocated
    raw=rows('LMI_GPU_RAM_LIVE_MAP',52);base,span=raw[:2]
    assert base<=physical<=base+span-allocated
    prior=set(raw[5:])|set(result['core_backing_pages'])
    assert not set(range(physical,physical+allocated,4096))&prior, 'Metadata overlaps live GMU/GPU allocation'
    assert rows('LMI_GPU_ZAP_METADATA_NC',2)==[0x2361d154,6]
    status,value,attempts=rows('LMI_GPU_ZAP_METADATA_REPLY',3)
    assert status==value==0 and 1<=attempts<=64
    assert rows('LMI_GPU_ZAP_METADATA_RESULT',1)==[1]
    order=['LMI_GPU_CP_FENCE_VERIFIED_HELD','LMI_GPU_CP_RESULT','LMI_GPU_ZAP_METADATA_CLAIM',
           'LMI_GPU_ZAP_METADATA_NC','LMI_GPU_ZAP_METADATA_REPLY','LMI_GPU_ZAP_METADATA_RETAINED',
           'LMI_GPU_ZAP_METADATA_RESULT','LMI_GPU_CORE_MEMORY_RESULT']
    assert all(log.count(m+'\n')==1 for m in order)
    positions=[log.index(m+'\n') for m in order];assert positions==sorted(positions)
    result.update(mode=44,zap_metadata_accepted=True,zap_authenticated=False,zap_metadata_pa=hex(physical),
                  zap_metadata_bytes=allocated,zap_metadata_cache_policy='Normal-NC (WIMG6)',
                  zap_metadata_retained=True,pas_operation='INIT_IMAGE only')
    return result
