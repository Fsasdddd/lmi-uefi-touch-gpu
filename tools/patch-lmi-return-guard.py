"""Pinned-kernel diagnostic: guard PE boot-arg query until PE_state is initialized.

The small AArch64 thunk occupies verified unused NOP padding after __start.
The original entry branch and original prebuilt are unchanged. Source-equivalent
patch is also exported for a subsequent full kernel build.
"""
from pathlib import Path
import difflib,hashlib,json,struct

root=Path(__file__).resolve().parents[1]
source=root/'hackios/prebuilt/mach.development.bcm2837'
b=bytearray(source.read_bytes())
before_sha=hashlib.sha256(b).hexdigest()
assert before_sha=='9239d4adb7a2c433d7ed5729b47b63acc5281af73d8a81640ef3c678c8afd26c'
segments=[];pos=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,size=struct.unpack_from('<II',b,pos)
    if cmd==0x19:
        va,vs,fo,fs=struct.unpack_from('<QQQQ',b,pos+24)
        segments.append((va,fs,fo))
    pos+=size
def offset(va,size=4):
    found=[fo+va-base for base,fs,fo in segments if base<=va and va+size<=base+fs]
    assert len(found)==1
    return found[0]
def branch(pc,target,link=False):
    assert (target-pc)%4==0
    imm=(target-pc)//4
    assert -(1<<25)<=imm<(1<<25)
    return (0x94000000 if link else 0x14000000)|(imm&0x3ffffff)
def adrp(pc,target,rd):
    imm=((target&~4095)-(pc&~4095))//4096
    assert -(1<<20)<=imm<(1<<20)
    return 0x90000000|((imm&3)<<29)|(((imm>>2)&0x7ffff)<<5)|rd

thunk=0xfffffff00745e4ac
call=0xfffffff007472a6c
parser=0xfffffff007a53ad8
pe_bootargs=0xfffffff007252900
off=offset(thunk,24);calloff=offset(call)
assert struct.unpack_from('<I',b,offset(thunk-4))[0]==0x14000aed # original entry branch
assert b[off:off+24]==struct.pack('<I',0xd503201f)*6
assert struct.unpack_from('<I',b,calloff)[0]==branch(call,parser,True)==0x9417841b
words=[adrp(thunk,pe_bootargs,8),
       0xf9400000|((pe_bootargs&4095)//8<<10)|(8<<5)|8, # ldr x8,[x8,#0x900]
       0xb4000000|(2<<5)|8, # cbz x8, thunk+16
       branch(thunk+12,parser), # tail-call original parser, arguments and LR unchanged
       0x52800000, # mov w0,#0
       0xd65f03c0] # ret
b[off:off+24]=struct.pack('<6I',*words)
struct.pack_into('<I',b,calloff,branch(call,thunk,True))
out=root/'out/lmi-kernel-return-guard';out.mkdir(exist_ok=True)
(out/source.name).write_bytes(b)
c=(root/'hackios/xnu/files/osfmk/arm64/loader_return.c').read_text()
needle='if (PE_parse_boot_argn("bootcpu", &own_core, sizeof(own_core))) {'
assert c.count(needle)==1
patched=c.replace(needle,'/* PE_init_platform has not run at checkpoint 10. */\n\tif (PE_state.bootArgs != NULL && PE_parse_boot_argn("bootcpu", &own_core, sizeof(own_core))) {')
(out/'loader_return.c').write_text(patched)
(out/'source-equivalent.patch').write_bytes(''.join(difflib.unified_diff(c.splitlines(True),patched.splitlines(True),fromfile='a/osfmk/arm64/loader_return.c',tofile='b/osfmk/arm64/loader_return.c')).encode())
report=dict(source_sha256=before_sha,sha256=hashlib.sha256(b).hexdigest(),hardware_tested=False,
    patch='PE_state.bootArgs null guard; original argument query resumes after platform initialization',
    call_va=hex(call),thunk_va=hex(thunk),pe_bootargs_va=hex(pe_bootargs),thunk_instructions=[hex(w) for w in words],
    restrictions='Pinned artifact only; reviewed early checkpoints, one CPU; no general-boot or secondary-CPU validation')
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
