"""Verify the pinned display observation candidate and its relocation proofs.

This is a host integration gate, not proof of hardware synchronization.
"""
from pathlib import Path
import hashlib, json, runpy, struct

repo=Path(__file__).resolve().parents[1]
folder=repo/'out/lmi-kernel-display-runtime-v41b'
report=json.loads((folder/'integration-audit.json').read_text())
raw=(folder/'mach.development.bcm2837').read_bytes()
expected='3f33d8891b3e3640d7c5b834ee487eeaa0f561e5c835b6a10b9b733608d9c42c'
assert hashlib.sha256(raw).hexdigest()==report['sha256']==expected
assert report['result']=='INTEGRATED_HOST_ONLY'
assert report['runtime_bindings_relinked'] and report['executable_symbol_addresses_unchanged']
assert len(report['accepted_abi_relocations'])==6
assert all(row['source_data_page_delta']=='0x4000' and row['branch_target_unchanged'] for row in report['accepted_abi_relocations'])
m=runpy.run_path(str(repo/'tools/build-lmi-source-runtime.py'))
segments=m['segments'](raw)
def offset(va,length=4):
    found=[s[2]+va-s[0] for s in segments.values() if s[0]<=va and va+length<=s[0]+s[3]]
    assert len(found)==1
    return found[0]

def hook_check(data):
    pc=0xfffffff0079e39f0
    instruction=struct.unpack_from('<I',data,offset(pc))[0]
    assert instruction&0xfc000000==0x14000000
    immediate=instruction&0x3ffffff
    if immediate&(1<<25):immediate-=1<<26
    assert pc+immediate*4==0xfffffff007ae0070
    trampoline=0xfffffff007ae014c
    first,branch=struct.unpack_from('<2I',data,offset(trampoline,8))
    assert first==0xd10703ff and branch&0xfc000000==0x14000000
    immediate=branch&0x3ffffff
    if immediate&(1<<25):immediate-=1<<26
    assert trampoline+4+immediate*4==pc+4
    assert segments['__TEXT_EXEC'][0]<=trampoline<segments['__TEXT_EXEC'][0]+segments['__TEXT_EXEC'][1]
hook_check(raw)
controls=[]
for name,address in [('changed-show-target',0xfffffff0079e39f0),
                     ('changed-displaced-instruction',0xfffffff007ae014c),
                     ('changed-trampoline-return',0xfffffff007ae0150)]:
    damaged=bytearray(raw);damaged[offset(address)]^=1
    try:hook_check(damaged)
    except AssertionError:controls.append(name)
    else:raise AssertionError('Accepted '+name)
relocation=json.loads((repo/'out/lmi-display-runtime-v41/result.json').read_text())
assert relocation['extension_sha256']==report['source_sha256']
assert relocation['runtime']['probe']['moved_bindings']==10
assert relocation['runtime']['touch']['moved_bindings']==6
early=json.loads((repo/'out/lmi-display-early-v41/result.json').read_text())
assert len(early['thunks'])==7
for proof in list(relocation['runtime'].values())+list(early['thunks'].values()):
    assert proof['baseline_allocated_bytes_exact']
    assert all(row['symbol'] and int(row['after'],16)>0xfffffff000000000 for row in proof['dependencies'])
snapshot=json.loads((repo/'out/lmi-dpu-snapshot-host/result.json').read_text())
assert snapshot['result']=='PASS' and snapshot['readonly_mapping'] and snapshot['register_fields']==9
sources=['lmi-dpu-snapshot.c','check-lmi-dpu-snapshot.py','build-lmi-display-extension.py',
         'relink-lmi-display-runtime.py','relink-lmi-display-early-thunks.py',
         'integrate-lmi-display-runtime.py','check-lmi-display-runtime.py']
hashes={name:hashlib.sha256((repo/'tools'/name).read_bytes()).hexdigest() for name in sources}
assert snapshot['source_sha256']==hashes['lmi-dpu-snapshot.c']
result=dict(result='PASS',kernel_sha256=expected,negative_controls=controls,
    relinked_early_thunks=7,moved_runtime_bindings=16,readonly_dpu_observer=True,
    source_sha256=hashes,hardware_verified=False)
(folder/'host-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
