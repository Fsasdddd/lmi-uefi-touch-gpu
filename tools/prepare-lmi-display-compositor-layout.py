"""Extract the exact frozen framebuffer declaration and compile its ABI layout.
Host-only: no kernel patch and no device access. This prepares a compositor
adapter without inventing field offsets or changing the original class.
"""
from pathlib import Path
import hashlib,json,os,re,shlex,struct,subprocess
root=Path(__file__).resolve().parents[1]
base=Path('/root/hackios-lmi/kernel-build-v36')
xnu=base/'xnu-src/xnu-8796.121.2'
obj=xnu/'BUILD/obj/DEVELOPMENT_ARM64_BCM2837'
source=root/'hackios/xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp'
raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='78141b3294b6c16b9173d5a7af64dc0b8a16f57d8027c93be608ef9dbbf764e9'
assert raw==(xnu/'iokit/Kernel/MiniIOMobileFramebuffer.cpp').read_bytes()
s=raw.decode()
start=s.index('class IOMobileFramebuffer : public IOService')
end=s.index('\n};',start)+3
macros=[]
for name in ('SWAP_QUEUE','SWAP_SIZE','SWAP_LAYERS','FRAME_TIMES'):
    macros.append(re.search(r'^#define '+name+r'\s+.*$',s,re.M).group(0))
header='#include <IOKit/IOService.h>\n#include <IOKit/IOLocks.h>\n#include <kern/thread.h>\nclass MiniIOSurface;\nstruct RowJob;\n'+'\n'.join(macros)+'\n'+s[start:end]+'\n'
fields=['fLock','fBase','fPanelWidth','fPanelHeight','fRowBytes','fWidth','fHeight','fGraphics','fColumn','fColumnWeight','fThreads','fHelpersBusy']
unit=header+'extern "C" __attribute__((used)) const unsigned long long lmi_compositor_layout[] = {sizeof(IOMobileFramebuffer),'+','.join('__builtin_offsetof(IOMobileFramebuffer,'+f+')' for f in fields)+'};\n'
out=root/'out/lmi-display-compositor-layout'
assert not out.exists(),'Preserve prior layout evidence'
out.mkdir()
(out/'framebuffer-declaration.h').write_text(header)
(out/'layout.cpp').write_text(unit)
flags=shlex.split((obj/'.CFLAGS').read_text().rstrip('\0\n'))[1:]
compiler=base/'xnu-deps/host/bin/xnu-clang++'
env=dict(os.environ,PATH=str(compiler.parent)+':'+os.environ['PATH'])
command=[str(compiler),*flags,'-std=gnu++17','-fapple-kext','-fno-exceptions','-fno-rtti','-Wno-invalid-offsetof','-c',str(out/'layout.cpp'),'-o',str(out/'layout.o')]
r=subprocess.run(command,cwd=obj,env=env,text=True,capture_output=True)
(out/'compile.log').write_text(shlex.join(command)+'\n'+r.stdout+r.stderr)
r.check_returncode()
blob=(out/'layout.o').read_bytes();pos=32;sections=[];symtab=None
for _ in range(struct.unpack_from('<I',blob,16)[0]):
    cmd,size=struct.unpack_from('<II',blob,pos)
    if cmd==0x19:
        for n in range(struct.unpack_from('<I',blob,pos+64)[0]):
            row=struct.unpack_from('<16s16sQQIIIIIIII',blob,pos+72+80*n)
            sections.append(row)
    if cmd==2:symtab=struct.unpack_from('<4I',blob,pos+8)
    pos+=size
assert symtab
so,count,st,_=symtab
for n in range(count):
    name,typ,sect,desc,value=struct.unpack_from('<IBBHQ',blob,so+16*n)
    label=blob[st+name:blob.index(b'\0',st+name)].decode()
    if label=='_lmi_compositor_layout':
        section=sections[sect-1];offset=section[4]+value-section[2]
        values=struct.unpack_from('<'+'Q'*(len(fields)+1),blob,offset)
        break
else:raise AssertionError('Missing layout symbol')
report=dict(result='ABI_COMPILED_ONLY',source_sha256=hashlib.sha256(raw).hexdigest(),class_bytes=values[0],offsets=dict(zip(fields,values[1:])),declaration_sha256=hashlib.sha256(header.encode()).hexdigest(),hardware_tested=False,desktop_integrated=False)
(out/'layout.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
