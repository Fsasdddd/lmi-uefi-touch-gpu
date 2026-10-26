"""Build v52 automatic owned-buffer/scaler probe in the reserved display RX page.

WSL only, host only. Original source sections must reproduce exactly; the
frozen v40 runtime is retained byte for byte outside the extension and its
existing symbol metadata. New state fits only the existing zeroed tail padding.
"""
from pathlib import Path
import argparse, hashlib, json, os, runpy, shlex, struct, subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--attempt',choices=['v52','v52b','v52c','v52d','v52e'],default='v52')
parser.add_argument('--verify-existing',action='store_true',help='Resume host validation after a rejected link, without overwriting build inputs')
args=parser.parse_args()

repo = Path(__file__).resolve().parents[1]
out = repo/('out/lmi-display-probe-'+args.attempt)
if args.verify_existing:
    assert out.is_dir() and not (out/'mach.development.bcm2837').exists()
else:
    assert not out.exists(), 'Preserve existing candidate'
    out.mkdir()
build = Path('/root/hackios-lmi/out/lmi-display-probe-'+args.attempt)
if args.verify_existing:assert (build/'extension').is_file()
else:
    assert not build.exists()
    build.mkdir()
base = Path('/root/hackios-lmi/kernel-build-v36')
obj = base/'xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837'
toolbin = base/'xnu-deps/host/bin'
env = dict(os.environ, THEOS='/root/hackios-lmi/gpu-build-env/theos',
    XNUDEPS=str(base/'xnu-deps'), XNU_SDK_PATH=str(base/'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'),
    XNU_SDK_VERSION='16.5', XNU_PLATFORM_PATH=str(base/'xnu-deps/sdk/Platforms/iPhoneOS.platform'))
env['PATH'] = str(toolbin)+':'+env['PATH']
sha = lambda raw: hashlib.sha256(raw).hexdigest()
m = runpy.run_path(str(repo/'tools/build-lmi-source-runtime.py'))
sealed = repo/'out/lmi-display-v40-paused'
frozen = (sealed/'mach.development.bcm2837').read_bytes()
assert sha(frozen) == '3f33d8891b3e3640d7c5b834ee487eeaa0f561e5c835b6a10b9b733608d9c42c'
old_source = Path('/root/hackios-lmi/out/lmi-display-extension-v41/extension').read_bytes()
assert sha(old_source) == '304e630feb466e1de19789f8b7c9fd7a539a7cd00e9bb0a8ecca650e3f5c2108'
inputs = json.loads((repo/'out/lmi-display-extension-v41/input-sha256.json').read_text())
assert all(sha(Path(name).read_bytes()) == digest for name,digest in inputs.items())

def run(args, log):
    if parser_args.verify_existing:
        assert (out/log).is_file()
        return
    with (out/log).open('w') as f:
        f.write(shlex.join(map(str,args))+'\n'); f.flush()
        subprocess.run(list(map(str,args)), cwd=obj, env=env, stdout=f, stderr=subprocess.STDOUT, check=True)

parser_args=args
names=['lmi-display-native-state-v50.S','lmi-display-native-v50.c','lmi-display-pipeline-v51.c',
       'lmi-display-dma-v52.c','lmi-display-probe.c','lmi-display-compositor.c','lmi-display-compositor.h','lmi-display-compositor-abi.h','lmi-display-pipeline.h','lmi-display-dma.h','lmi-display-probe.h']
# Bind every adapter field offset to the actual frozen C++ declaration and
# independently compiled layout evidence. The source class is unchanged.
layout_folder=repo/'out/lmi-display-compositor-layout'
layout=json.loads((layout_folder/'layout.json').read_text())
class_source=repo/'hackios/xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp'
assert sha(class_source.read_bytes())==layout['source_sha256']=='78141b3294b6c16b9173d5a7af64dc0b8a16f57d8027c93be608ef9dbbf764e9'
assert class_source.read_bytes()==(base/'xnu-src/xnu-8796.121.2/iokit/Kernel/MiniIOMobileFramebuffer.cpp').read_bytes()
assert sha((layout_folder/'framebuffer-declaration.h').read_bytes())==layout['declaration_sha256']
abi='/* Generated from the exact frozen class with the XNU toolchain. */\n#ifndef LMI_COMPOSITOR_ABI_H\n#define LMI_COMPOSITOR_ABI_H\n'
for name,value in layout['offsets'].items():abi+=f'#define LMI_FB_{name} {value}u\n'
abi+='#define LMI_FB_CLASS_BYTES 3136u\n#endif\n'
assert (repo/'tools/lmi-display-compositor-abi.h').read_text()==abi
assert layout['class_bytes']==3136
if not args.verify_existing:
    (out/'compositor-layout.json').write_bytes((layout_folder/'layout.json').read_bytes())
objects=[]
compile_flags=['-arch','arm64','-Oz','-mllvm','-enable-machine-outliner=always','-Wall','-Wextra','-Werror','-ffreestanding','-mgeneral-regs-only',
    '-fomit-frame-pointer','-fno-jump-tables','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-DLMI_PIPELINE_NATIVE']
for name in names:
    src=repo/'tools'/name
    if args.verify_existing:assert (out/name).read_bytes()==src.read_bytes()
    else:(out/name).write_bytes(src.read_bytes())
    if name.endswith('.h'):continue
    target=build/(Path(name).stem+'.o');objects.append(target)
    run([toolbin/'xnu-clang',*compile_flags,'-c',src,'-o',target],name+'.log')
flags = shlex.split((obj/'.LDFLAGS').read_text().rstrip('\0\n'))
assert flags.pop(0) == 'xnu-clang++'
archives = shlex.split((obj/'mach.development.bcm2837.link/mach.development.bcm2837.linkarchives').read_text())
extras = [obj/name for name in ['version.o','lastkerneldataconst.o','lastkernelconstructor.o','nonlto.o']]
run([toolbin/'xnu-clang++',*flags,'-filelist',obj/'link.filelist',*extras,*archives,
    *objects,'/root/hackios-lmi/out/lmi-display-extension-v41/show-trampoline.o',
    '-o',build/'extension.unstripped'],'link.log')
run([toolbin/'strip','-S',build/'extension.unstripped','-o',build/'extension'],'strip.log')
new_source = (build/'extension').read_bytes()
assert all(sha(Path(name).read_bytes()) == digest for name,digest in inputs.items())
oldsegs,newsegs = m['segments'](old_source),m['segments'](new_source)
assert oldsegs.keys()==newsegs.keys()
assert all(all(oldsegs[name][i]==newsegs[name][i] for i in (0,1,3)) for name in oldsegs if name!='__LINKEDIT'), 'Reserved extension must not change loaded virtual ranges'
assert oldsegs['__TEXT_EXEC']==newsegs['__TEXT_EXEC']
oldsyms = m['symbols']((sealed/'kernel-symbols.txt').read_text())
newtext = subprocess.check_output([str(toolbin/'nm'),'-n',str(build/'extension.unstripped')],env=env,text=True)
newsyms = m['symbols'](newtext)
lo,hi = 0xfffffff007ae0000,0xfffffff007ae4000
from collections import Counter
old_fixed=Counter((va,name) for va,kind,name in oldsyms if not lo<=va<hi)
new_fixed=Counter((va,name) for va,kind,name in newsyms if not lo<=va<hi)
assert not old_fixed-new_fixed, 'Original symbol addresses changed'
added_data=list((new_fixed-old_fixed).elements())
assert added_data==[(0xfffffff007b46fe0,'_state')]

pos=32;uuid=[]
for _ in range(struct.unpack_from('<I',old_source,16)[0]):
    cmd,size=struct.unpack_from('<II',old_source,pos)
    if cmd==0x1b:uuid.append((pos+8,pos+24))
    pos+=size
assert len(uuid)==1
def offset(va,length=1):
    spans=[s[2]+va-s[0] for s in oldsegs.values() if s[0]<=va and va+length<=s[0]+s[3]]
    assert len(spans)==1
    return spans[0]
start,end=offset(lo),offset(hi-1)+1
for name,(va,vs,fo,fs) in oldsegs.items():
    if not fs or name in ('__LINKINFO','__LINKEDIT'):continue
    newfo=newsegs[name][2]
    a,b=bytearray(old_source[fo:fo+fs]),bytearray(new_source[newfo:newfo+fs])
    # Fresh link headers describe different extension section/symbol lengths.
    # They are not transplanted: retain the complete frozen v40 header.
    header_end=32+struct.unpack_from('<I',old_source,20)[0]
    assert header_end==32+struct.unpack_from('<I',new_source,20)[0]
    for x,y in [*uuid,(0,header_end),(start,end)]:
        x,y=max(x,fo),min(y,fo+fs)
        if x<y:a[x-fo:y-fo]=b[x-fo:y-fo]
    assert a==b, 'Source section outside reserved code changed: '+name
symbols={name:va for va,kind,name in newsyms}
assert symbols['__Z18MiniIOSurfaceDrawnP13MiniIOSurfacey']==0xfffffff0079e5970
observer=symbols['_lmi_dpu_observe_show'];trampoline=symbols['_lmi_dpu_original_show']
assert lo<=observer<hi and lo<=trampoline<hi
assert symbols['_display_map']==0xfffffff007b46fd0 and symbols['_display_samples']==0xfffffff007b46fd8
word,branch=struct.unpack_from('<II',new_source,offset(trampoline,8))
imm=branch&0x3ffffff;imm=imm-(1<<26) if imm&(1<<25) else imm
assert word==0xd10703ff and branch&0xfc000000==0x14000000
assert trampoline+4+imm*4==0xfffffff0079e39f4
result=bytearray(frozen);result[start:end]=new_source[start:end]
hook=offset(0xfffffff0079e39f0,4)
struct.pack_into('<I',result,hook,0x14000000|(((observer-0xfffffff0079e39f0)//4)&0x3ffffff))
# The timer's one existing call to the native eight-core stop is wrapped;
# the wrapper must still call that exact native entry before restoration.
return_pc=0xfffffff007460cd0
return_offset=offset(return_pc,4)
assert struct.unpack_from('<I',frozen,return_offset)[0]==0x97ffe6d2
cleanup=symbols['_lmi_display_smp_prepare']
assert lo<=cleanup<hi
struct.pack_into('<I',result,return_offset,0x94000000|(((cleanup-return_pc)//4)&0x3ffffff))
# Update existing extension symbols for truthful debugger metadata. Do not add
# entries or move LINKEDIT: the original runtime remains an exact v40 snapshot.
pos=32;symtab=None
for _ in range(struct.unpack_from('<I',frozen,16)[0]):
    cmd,size=struct.unpack_from('<II',frozen,pos)
    if cmd==2:symtab=struct.unpack_from('<IIII',frozen,pos+8)
    pos+=size
assert symtab
symoff,count,stroff,strsize=symtab;symbol_edits=[]
for n in range(count):
    at=symoff+16*n;index,typ,sect,desc,value=struct.unpack_from('<IBBHQ',frozen,at)
    if lo<=value<hi:
        name=frozen[stroff+index:frozen.index(b'\0',stroff+index)].decode()
        assert name in symbols
        if symbols[name]!=value:
            struct.pack_into('<Q',result,at+8,symbols[name]);symbol_edits.append((at+8,at+16))
allowed=[(start,end),(hook,hook+4),(return_offset,return_offset+4),*symbol_edits]
check=bytearray(result)
for x,y in allowed:check[x:y]=frozen[x:y]
assert check==frozen, 'Mutation outside bounded observer or metadata'
(out/'mach.development.bcm2837').write_bytes(result)
(out/'kernel-symbols.txt').write_text(newtext)
report=dict(result='HOST_BUILT_ONLY',sha256=sha(result),base_sha256=sha(frozen),
    sources={name:sha((repo/'tools'/name).read_bytes()) for name in names},builder_sha256=sha(Path(__file__).read_bytes()),
    candidate_source_sha256=sha(new_source),layout_unchanged=True,original_source_bytes_exact=True,
    runtime_outside_extension_exact=True,observer=hex(observer),trampoline=hex(trampoline),
    allowed_file_ranges=allowed,return_hook=hex(return_pc),cleanup=hex(cleanup),register_writes=True,
    compile_flags=compile_flags,compositor_layout_sha256=sha((out/'compositor-layout.json').read_bytes()),automatic_pattern_probe=True,desktop_pipeline=True,conditional_desktop_enable=True,hardware_tested=False)
(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
