"""Pin the first synchronized CPU/GOP candidate independently of v40/v41."""
import json, shutil, struct
from lmi_display_v40_policy import checked
from lmi_display_v41_policy import stage as stage41, observe as observe41

KERNEL_SHA='76eb63eb83c25762eba5a5daacedcc44a7f9e997bd55c54e11c54e5bd7164730'
SOURCE_SHA='7ea196239baf9fdef67ae35978c978589598088037c6470540de27145857e306'

def stage(root,out):
    parent,meta=stage41(root,out)
    folder=root/'out/lmi-display-sync-v42b'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads((folder/'build-audit.json').read_text())
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    assert audit['layout_unchanged'] and audit['original_source_bytes_exact'] and audit['runtime_outside_extension_exact']
    assert audit['register_writes'] and audit['synchronized_present']
    checked(root/'tools/lmi-dpu-sync-v42.c',SOURCE_SHA)
    checked(root/'tools/lmi-dpu-observer-v42.c',audit['source_sha256'])
    checked(root/'tools/build-lmi-display-v42.py',audit['builder_sha256'])
    host=json.loads((root/'out/lmi-dpu-sync-v42-host/result.json').read_text())
    assert host['result']=='PASS' and host['source_sha256']==SOURCE_SHA
    assert host['protocol_scenarios']==19 and host['rollback_readback'] and host['return_after_verified_cpu_stop']
    old=parent.read_bytes();assert len(raw)==len(old)
    allowed=[(11386880,11403264),(10353136,10353140),(4574416,4574420),(13588952,13588960),(13964712,13964720)]
    check=bytearray(raw)
    for lo,hi in allowed:check[lo:hi]=old[lo:hi]
    assert check==old
    pc=0xfffffff007460cd0;word=struct.unpack_from('<I',raw,4574416)[0]
    imm=word&0x3ffffff;imm=imm-(1<<26) if imm&(1<<25) else imm
    assert word&0xfc000000==0x94000000 and pc+imm*4==0xfffffff007ae071c
    assert struct.unpack_from('<I',old,4574416)[0]==0x97ffe6d2
    assert raw[0xb42fe0:0xb43000]==bytes(32), 'Restoration journal must start zeroed in the old padding'
    meta['sha256']=KERNEL_SHA
    meta['display_v42']=meta.pop('display_v41')
    meta['display_v42'].update(parent_sha256=audit['base_sha256'],synchronized_present=True,
        readonly=False,hardware_verified=False,return_restoration=True)
    target=out/'display-v42-candidate';assert not target.exists()
    shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-dpu-sync-v42-host/result.json',target/'sync-host-check.json')
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta


def observe(log):
    import re
    result=observe41(log)
    pattern=re.compile(r'LMI_DPU_SYNC n=(\d+) ok=(\d+) phase=(\d+) frames=(\d+) line=(\d+) status=([0-9a-f]+) restored=(\d+)')
    rows=[];bad=[]
    for line in log.splitlines():
        if 'LMI_DPU_SYNC n=' not in line:continue
        m=pattern.fullmatch(line)
        if not m:bad.append(line);continue
        keys=['n','ok','phase','frames','line','status','restored']
        rows.append({k:int(v,16 if k=='status' else 10) for k,v in zip(keys,m.groups())})
    restored='LMI_DPU_SYNC_RETURN restored=1' in log.splitlines()
    refused='LMI_DPU_SYNC_REFUSED' in log
    valid=(len(rows)>=2 and not bad and not refused and restored and
        all(b['n']>a['n'] for a,b in zip(rows,rows[1:])) and
        all(r['ok']==r['frames']==r['restored']==1 and r['phase']==2 and r['line']>=2400 and r['status']&0x100 for r in rows) and
        'LMI_SMP_OTHER_CORES_OFF' in log and log.index('LMI_SMP_OTHER_CORES_OFF')<log.index('LMI_DPU_SYNC_RETURN restored=1'))
    result.update(sync_result='OBSERVED_COMPLETE' if valid else 'NOT_VERIFIED',sync_samples=rows,
        sync_malformed=bad,configuration_refused=refused,return_restored=restored,
        synchronized_present=valid,performance_verified=False)
    return result
