"""Original b02 relocated into owned NC memory and authenticated by GPU PAS13."""
from pathlib import Path
import re,runpy
def verify(log,firmware,window=None):
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-zap-metadata.py')))['verify'](log,firmware,window)
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_ZAP_CODE_CANARY',1)==[0x7eabe047]
    pool,physical,allocated,page=rows('LMI_GPU_ZAP_PAYLOAD_CLAIM',4)
    assert page in (4096,16384) and allocated==0x100000
    assert pool>=0xfffffff000000000 and pool%page==0 and physical%0x100000==0 and physical>>36==0
    ram=rows('LMI_GPU_RAM_LIVE_MAP',52);base,span=ram[:2]
    assert base<=physical<=base+span-allocated
    prior=set(ram[5:])|set(result['core_backing_pages'])
    meta=int(result['zap_metadata_pa'],16)
    prior|=set(range(meta,meta+result['zap_metadata_bytes'],4096))
    assert not set(range(physical,physical+allocated,4096))&prior, 'ZAP payload overlaps another live allocation'
    blocks=re.findall(r'LMI_GPU_ZAP_LOAD_SMC\n((?:[0-9a-f]{16}\n){4})',log)
    assert len(blocks)==log.count('LMI_GPU_ZAP_LOAD_SMC\n')==2
    replies=[]
    for block,command in zip(blocks,[2,5]):
        reply=[int(v,16) for v in block.splitlines()]
        assert reply[:3]==[command,0,0] and 1<=reply[3]<=64
        replies.append(reply)
    assert rows('LMI_GPU_ZAP_PAYLOAD_CRC',1)==[0x5384b346]
    assert rows('LMI_GPU_ZAP_LOAD_RESULT',1)==[1]
    assert log.count('LMI_GPU_ZAP_AUTHENTICATED_HELD\n')==1
    order=['LMI_GPU_ZAP_METADATA_RESULT','LMI_GPU_ZAP_CODE_CANARY','LMI_GPU_ZAP_PAYLOAD_CLAIM',
           'LMI_GPU_ZAP_LOAD_SMC','LMI_GPU_ZAP_PAYLOAD_CRC','LMI_GPU_ZAP_AUTHENTICATED_HELD',
           'LMI_GPU_ZAP_LOAD_RESULT','LMI_GPU_CORE_MEMORY_RESULT']
    positions=[log.index(m+'\n') for m in order];assert positions==sorted(positions)
    second=log.index('LMI_GPU_ZAP_LOAD_SMC\n',positions[3]+1)
    assert positions[4]<second<positions[5]
    result.update(mode=45,zap_authenticated=True,zap_payload_pa=hex(physical),zap_payload_bytes=allocated,
                  zap_mem_setup_span=4096,zap_pas_replies=replies,zap_payload_retained=True,
                  zap_code_execution_verified=True,gpu_secure_mode_changed=None,secure_mode_packet_sent=False,
                  pas_operation='INIT_IMAGE, MEM_SETUP, AUTH_AND_RESET')
    return result
