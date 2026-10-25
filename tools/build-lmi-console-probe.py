"""Build a checkpoint-20-only probe using XNU's own console and RAM log APIs.

Run in WSL. The pinned original and return-guard kernels remain untouched.
"""
from pathlib import Path
import hashlib,json,struct,subprocess

root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-kernel-return-guard/mach.development.bcm2837'
b=bytearray(src.read_bytes())
sha=hashlib.sha256(b).hexdigest()
assert sha=='29416b9a2d821978b6df40734453bc71d13b5ac5e53d3b280ce6aac57bffa1da'
out=root/'out/lmi-kernel-console-probe';out.mkdir(exist_ok=True)
symbols={}
for line in (root/'out/kernel-symbols.txt').read_text().splitlines():
    parts=line.split(maxsplit=2)
    if len(parts)==3:
        try:symbols[parts[2]]=int(parts[0],16)
        except ValueError:pass
thunk=0xfffffff00745e500
patch=0xfffffff007472c04
asm=f'''.text
.global _start
_start:
    cmp x0, #20
    b.ne tail
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    mov x20, x0
    mov x0, xzr
    mov w1, #4 // kPEAcquireScreen, confirmed in pinned pexpert.h
    bl pe_console
    adr x19, message
loop:
    ldrb w0, [x19], #1
    cbz w0, done
    bl putchar_console
    ldurb w0, [x19, #-1]
    bl putchar_log
    b loop
done:
    mov x0, x20
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
tail:
    mov x1, x0
    mov w0, #2
    b return_to_loader
message:
    .asciz "HackiOS lmi: XNU framebuffer console test\\nCheckpoint 20 - RAM-only diagnostics\\n"
'''
(out/'probe.S').write_text(asm)
subprocess.run(['clang','--target=aarch64-none-elf','-c',str(out/'probe.S'),'-o',str(out/'probe.o')],check=True)
targets=dict(pe_console='_PE_initialize_console',putchar_console='_console_write_unbuffered',putchar_log='_loader_log_putc',return_to_loader='_loader_jump')
defs=[f'--defsym={name}={symbols[symbol]:#x}' for name,symbol in targets.items()]
subprocess.run(['ld.lld',f'-Ttext={thunk:#x}','--entry=_start',*defs,str(out/'probe.o'),'-o',str(out/'probe.elf')],check=True)
subprocess.run(['llvm-objcopy','-O','binary',str(out/'probe.elf'),str(out/'probe.bin')],check=True)
code=(out/'probe.bin').read_bytes()
assert len(code)<0xa00
regions=[];pos=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,size=struct.unpack_from('<II',b,pos)
    if cmd==0x19:regions.append(struct.unpack_from('<QQQQ',b,pos+24))
    pos+=size
def offset(va,size):
    matches=[fo+va-base for base,vs,fo,fs in regions if base<=va and va+size<=base+fs]
    assert len(matches)==1
    return matches[0]
co=offset(thunk,len(code));po=offset(patch,4)
padded=(len(code)+3)&~3
assert b[co:co+padded]==struct.pack('<I',0xd503201f)*(padded//4)
assert struct.unpack_from('<I',b,po)[0]==0xaa0003e1
b[co:co+len(code)]=code
imm=(thunk-patch)//4
assert -(1<<25)<=imm<(1<<25)
struct.pack_into('<I',b,po,0x14000000|(imm&0x3ffffff))
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
report=dict(source_sha256=sha,sha256=hashlib.sha256(b).hexdigest(),patch_va=hex(patch),thunk_va=hex(thunk),probe_bytes=len(code),
    hardware_tested=False,scope='Only matching checkpoint 20 acquires the XNU text console, prints diagnostic marker and returns; other checkpoints preserve the existing return behavior')
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
