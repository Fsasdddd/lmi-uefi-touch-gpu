"""Create a single-core diagnostic copy, bypassing an uninitialized PE boot-arg query.

Only for the restricted checkpoint <=10 profile: bootcpu is never requested.
The original kernel remains unchanged. This is not a general kernel build.
"""
from pathlib import Path
import difflib,hashlib,json,struct

root=Path(__file__).resolve().parents[1]
source=root/'hackios/prebuilt/mach.development.bcm2837'
b=bytearray(source.read_bytes())
original_sha=hashlib.sha256(b).hexdigest()
assert original_sha=='9239d4adb7a2c433d7ed5729b47b63acc5281af73d8a81640ef3c678c8afd26c'
va=0xfffffff007472a6c
pos=32
offset=None
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,size=struct.unpack_from('<II',b,pos)
    if cmd==0x19:
        base,vmsize,fileoff,filesize=struct.unpack_from('<QQQQ',b,pos+24)
        if base<=va and va+4<=base+filesize:offset=fileoff+va-base
    pos+=size
assert offset is not None
assert struct.unpack_from('<I',b,offset)[0]==0x9417841b # bl _PE_parse_boot_argn
struct.pack_into('<I',b,offset,0x52800000) # mov w0,#0: no bootcpu on this single-core profile
out=root/'out/lmi-kernel-early-return'
out.mkdir(exist_ok=True)
(out/source.name).write_bytes(b)
report=dict(source=str(source),source_sha256=original_sha,sha256=hashlib.sha256(b).hexdigest(),
    patch_va=hex(va),file_offset=hex(offset),before='bl _PE_parse_boot_argn',after='mov w0,#0',
    rationale='checkpoint 10 precedes PE_init_platform; PE_state.bootArgs is still NULL',
    restrictions='Only current-core, single-CPU checkpoints <=10; no general boot or bootcpu argument',hardware_tested=False)
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
c=(root/'hackios/xnu/files/osfmk/arm64/loader_return.c').read_text()
before='if (PE_parse_boot_argn("bootcpu", &own_core, sizeof(own_core))) {'
assert c.count(before)==1
patched=c.replace(before,'/* lmi diagnostic: no bootcpu; PE_state is not initialized at checkpoint 10. */\n\tif (0 && PE_parse_boot_argn("bootcpu", &own_core, sizeof(own_core))) {')
(out/'loader_return.c').write_text(patched)
(out/'diagnostic-source-equivalent.patch').write_text(''.join(difflib.unified_diff(c.splitlines(True),patched.splitlines(True),fromfile='a/osfmk/arm64/loader_return.c',tofile='b/osfmk/arm64/loader_return.c')))
print(json.dumps(report,indent=2))
