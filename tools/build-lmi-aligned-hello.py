"""Build the raw-syscall test with an AArch64 stack-aligned static entry."""
from pathlib import Path
import hashlib,json,struct,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-user-entry-fix';out.mkdir(exist_ok=True)
source=root/'userland-source/userland/src/hello.c'
asm='.text\n.globl _start\n_start:\n mov x9, sp\n and sp, x9, #0xfffffffffffffff0\n b _hello_main\n'
(out/'start.S').write_text(asm)
subprocess.run(['clang','-target','arm64-apple-ios16.5','-Os','-ffreestanding','-fno-stack-protector','-fno-builtin','-Dstart=hello_main','-c',str(source),'-o',str(out/'hello.o')],check=True)
subprocess.run(['clang','-target','arm64-apple-ios16.5','-c',str(out/'start.S'),'-o',str(out/'start.o')],check=True)
# LLD's Mach-O -static is unimplemented. Link the object layout, then replace
# the unused dynamic loader commands with LC_UNIXTHREAD (no segment movement).
subprocess.run(['ld64.lld-18','-arch','arm64','-platform_version','ios','16.5','16.5','-e','_start','-pagezero_size','0x100000000','-o',str(out/'hello.linked'),str(out/'hello.o'),str(out/'start.o')],check=True)
b=bytearray((out/'hello.linked').read_bytes());assert struct.unpack_from('<I',b)[0]==0xfeedfacf
ncmds,oldsize=struct.unpack_from('<II',b,16);commands=[];p=32;text_va=None;entryoff=None;first_section=None
for _ in range(ncmds):
    cmd,size=struct.unpack_from('<II',b,p)
    if cmd==0x19 and b[p+8:p+24].rstrip(b'\0')==b'__TEXT':
        text_va=struct.unpack_from('<Q',b,p+24)[0]
        nsects=struct.unpack_from('<I',b,p+64)[0]
        first_section=min(struct.unpack_from('<I',b,p+72+j*80+48)[0] for j in range(nsects))
    if cmd==0x80000028:entryoff=struct.unpack_from('<Q',b,p+8)[0]
    if cmd not in (0xe,0x80000028,0x80000022,0x1d):commands.append(bytes(b[p:p+size]))
    p+=size
assert text_va and entryoff and first_section
entry=text_va+entryoff
state=[0]*34;state[32]=entry
commands.append(struct.pack('<IIII',5,288,6,68)+struct.pack('<34Q',*state))
header=b''.join(commands);assert 32+len(header)<first_section
struct.pack_into('<II',b,16,len(commands),len(header))
flags=struct.unpack_from('<I',b,24)[0];struct.pack_into('<I',b,24,flags&~(0x200000|0x4))
b[32:32+max(oldsize,len(header))]=b'\0'*max(oldsize,len(header));b[32:32+len(header)]=header
(out/'hello').write_bytes(b)
(out/'disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'hello')]))
(out/'headers.txt').write_bytes(subprocess.check_output(['llvm-objdump','--macho','--private-headers',str(out/'hello')]))
meta=dict(sha256=hashlib.sha256(b).hexdigest(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),bytes=len(b),entry=hex(entry),
    scope='Own raw-syscall Darwin program. Align SP before calling C; LC_UNIXTHREAD with no dyld and no PIE. Does not contain Apple userland or prove iOS runtime.')
(out/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps(meta,indent=2))
