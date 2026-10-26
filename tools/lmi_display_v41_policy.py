"""Admission and raw-log checks for the bounded v41 DPU observer."""
from pathlib import Path
import hashlib, json, re, shutil, struct
from lmi_display_v40_policy import validate, checked, KERNEL_SHA as BASE_SHA

KERNEL_SHA='0c10166d65314e93fd0db168fd814ed474628762bfbee3e3f187de724e75e6ef'
SOURCE_SHA='175de6b7375202fe96b320b4f6c04fedda36a91c05232935cf801cb91e0f56ef'

def stage(root,out):
    sealed,meta=validate(root)
    folder=root/'out/lmi-display-observer-v41c'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads((folder/'build-audit.json').read_text())
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==BASE_SHA
    assert audit['layout_unchanged'] and audit['original_source_bytes_exact'] and audit['runtime_outside_extension_exact']
    assert audit['register_writes'] is False and audit['synchronized_present'] is False
    checked(root/'tools/lmi-dpu-observer-v41.c',SOURCE_SHA)
    checked(root/'tools/build-lmi-display-v41.py',audit['builder_sha256'])
    host=json.loads((root/'out/lmi-dpu-observer-v41-host/result.json').read_text())
    assert host['result']=='PASS' and host['source_sha256']==SOURCE_SHA
    assert host['forwards']==512 and host['readonly_mapping'] and host['mapping_failure_control']
    # Only the reserved RX page, the existing show branch and two existing
    # nlist values differ. This also preserves all relocated early thunks.
    old=(sealed/'mach.development.bcm2837').read_bytes()
    assert len(raw)==len(old)
    allowed=[(11386880,11403264),(10353136,10353140),(13588952,13588960),(13964712,13964720)]
    check=bytearray(raw)
    for lo,hi in allowed:check[lo:hi]=old[lo:hi]
    assert check==old
    pc=0xfffffff0079e39f0
    word=struct.unpack_from('<I',raw,10353136)[0]
    assert word==0x1403f1a0
    trampoline=0xfffffff007ae0164
    first,branch=struct.unpack_from('<II',raw,11386880+trampoline-0xfffffff007ae0000)
    imm=branch&0x3ffffff;imm=imm-(1<<26) if imm&(1<<25) else imm
    assert first==0xd10703ff and branch&0xfc000000==0x14000000 and trampoline+4+imm*4==pc+4
    meta['sha256']=KERNEL_SHA
    meta['display_v41']=meta.pop('display_v40')
    meta['display_v41'].update(parent_sha256=BASE_SHA,raw_return_log=True)
    target=out/'display-v41-candidate'
    assert not target.exists()
    shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-dpu-observer-v41-host/result.json',target/'observer-host-check.json')
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta


def observe(log):
    pattern=re.compile(r'LMI_DPU_PRESENT_READONLY n=(\d+) mux=([0-9a-f]+) sync=([0-9a-f]+) auto=([0-9a-f]+) frame=(\d+) line=(\d+) ctl_start=([0-9a-f]+) ctl_flush=([0-9a-f]+) source=([0-9a-f]+) stride=([0-9a-f]+)')
    keys=['n','mux','sync','auto','frame','line','ctl_start','ctl_flush','source','stride']
    rows=[];malformed=[]
    for line in log.splitlines():
        if 'LMI_DPU_PRESENT_READONLY' not in line:continue
        match=pattern.fullmatch(line)
        if not match:malformed.append(line);continue
        rows.append({key:int(value,10 if key in ('n','frame','line') else 16) for key,value in zip(keys,match.groups())})
    ordered=all(b['n']>a['n'] for a,b in zip(rows,rows[1:]))
    cadence=all(1<=row['n']<=4 or row['n']%128==0 for row in rows)
    failure='LMI_DPU_OBSERVER_MAP_FAILED' in log
    valid=len(rows)>=2 and ordered and cadence and not malformed and not failure
    return dict(result='OBSERVED' if valid else 'MISSING_OR_MALFORMED',samples=rows,
        malformed=malformed,mapping_failed=failure,ordered=ordered,cadence=cadence,
        mux_values=sorted({row['mux'] for row in rows}),
        synchronized_present=False,performance_verified=False)
