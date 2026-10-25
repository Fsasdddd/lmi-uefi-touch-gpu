"""Pinned-kernel checkpoint 50 immediately before PE_init_cpu/GIC init. Run in WSL."""
from pathlib import Path
import difflib,hashlib,json,struct,subprocess
root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-kernel-return-guard/mach.development.bcm2837'
b=bytearray(src.read_bytes())
sha=hashlib.sha256(b).hexdigest()
assert sha=='29416b9a2d821978b6df40734453bc71d13b5ac5e53d3b280ce6aac57bffa1da'
out=root/'out/lmi-kernel-preirq-probe';out.mkdir(exist_ok=True)
patch=0xfffffff007454250
thunk=0xfffffff00745e600
asm='''.text
.global _start
_start:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    mov w0, #50
    bl checkpoint
    ldp x29, x30, [sp], #16
    b original
'''
(out/'probe.S').write_text(asm)
subprocess.run(['clang','--target=aarch64-none-elf','-c',str(out/'probe.S'),'-o',str(out/'probe.o')],check=True)
subprocess.run(['ld.lld',f'-Ttext={thunk:#x}','--entry=_start','--defsym=checkpoint=0xfffffff007472bf0','--defsym=original=0xfffffff007a55ee4',str(out/'probe.o'),'-o',str(out/'probe.elf')],check=True)
subprocess.run(['llvm-objcopy','-O','binary',str(out/'probe.elf'),str(out/'probe.bin')],check=True)
regions=[];pos=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,size=struct.unpack_from('<II',b,pos)
    if cmd==0x19:regions.append(struct.unpack_from('<QQQQ',b,pos+24))
    pos+=size
def offset(va,size):
    found=[fo+va-base for base,vs,fo,fs in regions if base<=va and va+size<=base+fs]
    assert len(found)==1
    return found[0]
def branch(pc,target):
    assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
    return 0x94000000|(((target-pc)//4)&0x3ffffff)
code=(out/'probe.bin').read_bytes()
assert len(code)==24
co=offset(thunk,len(code));po=offset(patch,4)
assert b[co:co+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
assert struct.unpack_from('<I',b,po)[0]==branch(patch,0xfffffff007a55ee4)
b[co:co+len(code)]=code
struct.pack_into('<I',b,po,branch(patch,thunk))
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
dev=Path('/root/hackios-lmi/hackios/xnu-src/xnu-8796.121.2/osfmk/arm/arm_init.c')
source=dev.read_text()
needle='\tPE_init_cpu();\n\tfiq_context_init(TRUE);'
assert source.count(needle)==1
# Export a source equivalent for a future full XNU build; the hardware-tested
# binary remains derived from the pinned prebuilt rather than that source build.
before=source.replace('\tloader_checkpoint(50);\n'+needle,needle)
after=before.replace(needle,'\tloader_checkpoint(50);\n'+needle)
(out/'source-equivalent.patch').write_bytes(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/osfmk/arm/arm_init.c',tofile='b/osfmk/arm/arm_init.c')).encode())
report=dict(source_sha256=sha,sha256=hashlib.sha256(b).hexdigest(),patch_va=hex(patch),thunk_va=hex(thunk),probe_bytes=len(code),hardware_tested=False,
    scope='Insert checkpoint 50 before PE_init_cpu. When not matched, tail-call original PE_init_cpu. No kernel code skipped; GIC initialization has not run at checkpoint 50.')
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
