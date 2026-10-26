"""Relink the asynchronous backend in its already audited obsolete init bodies.

Reproduce the old linked payload, accept only named branch relocations outside
the replacement region, preserve v57's touch/display/frequency bytes, and hook
the existing RAM return through verified SMP/DPU cleanup then GPU drain.
"""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v58');args=p.parse_args()
assert re.fullmatch(r'v58[a-z]?',args.attempt)
root=Path(__file__).resolve().parents[1];out=root/('out/lmi-gpu-async-'+args.attempt)
assert not out.exists();out.mkdir()
sha=lambda b:hashlib.sha256(b).hexdigest()
module=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))
base=root/'out/lmi-display-probe-v57b/mach.development.bcm2837';raw=base.read_bytes()
assert sha(raw)=='5fe49222bc6bbed6678b2a2bfae7c32196f9414438e59fb457c5efd0198b4c43'
frozen=root/'out/lmi-kernel-ios-continue'
relocated=Path('/root/hackios-lmi/out/lmi-display-runtime-v41/touch-relocated.elf')
proof=json.loads((root/'out/lmi-display-runtime-v41/result.json').read_text())['runtime']['touch']
assert sha(relocated.read_bytes())==proof['relocated_elf_sha256']
kernel_symbols={n:a for a,k,n in module['symbols']((root/'out/lmi-display-probe-v56f/kernel-symbols.txt').read_text())}
def elf(path):
    b=path.read_bytes();assert b[:6]==b'\x7fELF\x02\x01'
    at=struct.unpack_from('<Q',b,40)[0];size,count,ns=struct.unpack_from('<HHH',b,58)
    h=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*size) for i in range(count)]
    strings=b[h[ns][4]:h[ns][4]+h[ns][5]]
    return {strings[s[0]:strings.index(b'\0',s[0])].decode():(s[3],b[s[4]:s[4]+s[5]]) for s in h if s[0] and s[2]&2 and s[5]}
def symbols(path):
    return {v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(path)],text=True).splitlines() if len(v:=line.split())==3}
builder=(root/'tools/build-lmi-ios-probe.py').read_text()
order=['touch.o']+re.findall(r"touch_objects\.append\(str\(out/'([^']+\.o)'\)\)",builder)
objects=[frozen/n for n in order if (frozen/n).exists()]
assert {v.name for v in frozen.glob('*.o')}=={'probe.o',*[v.name for v in objects]}
aliases=module['elf_absolutes'](relocated.read_bytes())
abi=runpy.run_path(str(root/'tools/lmi-gpu-desktop-profile.py'))['ABI']
command=['ld.lld','-T',str(frozen/'touch.ld'),'--entry=lmi_touch_thread','--gc-sections',
    '--undefined=lmi_gpu_probe',*['--undefined=lmi_desktop_'+n for n in sorted({v[2] for v in abi.values()})]]
def link(name,objs,bindings,extra=(),script=None):
    dest=out/(name+'.elf')
    with (out/(name+'-link.log')).open('w') as stream:
        cmd=list(command)
        if script:cmd[2]=str(script)
        subprocess.run([*cmd,*extra,*[f'--defsym={n}={a:#x}' for n,a in bindings.items()],*map(str,objs),'-o',str(dest)],
            stdout=stream,stderr=subprocess.STDOUT,check=True)
    return dest
baseline=link('baseline',objects,aliases)
assert elf(baseline)==elf(relocated),'Frozen object/linker reconstruction changed'
obj=out/'gpu-desktop.o'
flags=['--target=aarch64-none-elf','-Oz','-mllvm','-enable-machine-outliner=always','-ffunction-sections','-fdata-sections','-ffreestanding',
    '-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-Wall','-Wextra','-Werror']
subprocess.run(['clang',*flags,'-c',str(root/'tools/lmi-gpu-desktop-v58.c'),'-o',str(obj)],check=True)
bindings=dict(aliases,lmi_display_smp_prepare=kernel_symbols['_lmi_display_smp_prepare'])
script=(frozen/'touch.ld').read_text()
assert script.count('EXCLUDE_FILE (*gpu-context.o *gpu-resources.o) .text*')==1
script=script.replace('EXCLUDE_FILE (*gpu-context.o *gpu-resources.o) .text*',
    'EXCLUDE_FILE (*gpu-context.o *gpu-resources.o *gpu-desktop.o) .text*')
assert script.count('*gpu-desktop.o(.rodata*)')==1
script=script.replace('*gpu-desktop.o(.rodata*)','*gpu-desktop.o(.rodata* .text*)')
(out/'async.ld').write_text(script)
candidate=link('async', [obj if v.name=='gpu-desktop.o' else v for v in objects],bindings,
    ['--undefined=lmi_gpu_async_return'],out/'async.ld')
before,after=elf(baseline),elf(candidate);oldsyms,newsyms=symbols(baseline),symbols(candidate)
start=0xfffffff0074d9c88;end=0xfffffff0074db04c
assert before['.gpu_desktop'][0]==after['.gpu_desktop'][0]==start
payload=after['.gpu_desktop'][1]
report=dict(result='LINKED_NOT_INTEGRATED',bytes=len(payload),capacity=end-start,hardware_tested=False)
(out/'size-audit.json').write_text(json.dumps(report,indent=2)+'\n')
assert len(payload)<=end-start, 'Reject region overflow; no kernel emitted'
segs=module['segments'](raw)
def at(address,length=4):
    found=[s[2]+address-s[0] for s in segs.values() if s[0]<=address and address+length<=s[0]+s[3]]
    assert len(found)==1;return found[0]
def target(w,pc):
    assert w&0x7c000000==0x14000000
    d=w&0x3ffffff;return pc+((d-(1<<26) if d&(1<<25) else d)*4)
result=bytearray(raw);edits=[]
old=before['.gpu_desktop'][1];offset=at(start,len(old))
assert raw[offset:offset+len(old)]==old,'Current backend differs from frozen relocated payload'
result[offset:offset+len(payload)]=payload
edits.append((offset,offset+len(payload)))
relocations=[]
assert before.keys()==after.keys()
for name,(address,data) in before.items():
    if name=='.gpu_desktop':continue
    assert after[name][0]==address and len(after[name][1])==len(data)
    new=after[name][1]
    for i in range(0,len(data),4):
        if data[i:i+4]==new[i:i+4]:continue
        assert len(data[i:i+4])==4
        a,b=struct.unpack_from('<I',data,i)[0],struct.unpack_from('<I',new,i)[0]
        assert a&0xfc000000==b&0xfc000000 and a&0x7c000000==0x14000000
        was,now=target(a,address+i),target(b,address+i)
        names=[n for n,v in oldsyms.items() if v==was and start<=v<end]
        assert len(names)==1 and newsyms[names[0]]==now and start<=now<start+len(payload)
        pos=at(address+i);assert raw[pos:pos+4]==data[i:i+4]
        result[pos:pos+4]=new[i:i+4];edits.append((pos,pos+4))
        relocations.append(dict(pc=hex(address+i),symbol=names[0],before=hex(was),after=hex(now)))
for symbol,(pc,original,entry) in abi.items():
    pos=at(pc);oldword=struct.unpack_from('<I',raw,pos)[0]
    assert target(oldword,pc)==oldsyms['lmi_desktop_'+entry]
    dest=newsyms['lmi_desktop_'+entry];assert start<=dest<start+len(payload)
    struct.pack_into('<I',result,pos,0x14000000|(((dest-pc)//4)&0x3ffffff));edits.append((pos,pos+4))
pc=0xfffffff007460cd0;pos=at(pc)
assert target(struct.unpack_from('<I',raw,pos)[0],pc)==kernel_symbols['_lmi_display_smp_prepare']
struct.pack_into('<I',result,pos,0x94000000|(((newsyms['lmi_gpu_async_return']-pc)//4)&0x3ffffff));edits.append((pos,pos+4))
check=bytearray(result)
for a,b in edits:check[a:b]=raw[a:b]
assert check==raw and len(result)==len(raw)
names=['build-lmi-gpu-async-v58.py','lmi-gpu-desktop-v58.c','lmi-gpu-boot-regs.h','lmi-gpu-desktop-profile.py']
report.update(result='HOST_BUILT_ONLY',sha256=sha(result),base_sha256=sha(raw),sources={n:sha((root/'tools'/n).read_bytes()) for n in names},
    compile_flags=flags,baseline_reproduced=True,outside_edits_exact=True,allowed_file_ranges=edits,branch_relocations=relocations,
    timer_cleanup=hex(kernel_symbols['_lmi_display_smp_prepare']),timer_wrapper=hex(newsyms['lmi_gpu_async_return']),
    single_outstanding=True,submission_asynchronous=True,hardware_ready=False)
(out/'mach.development.bcm2837').write_bytes(result)
(out/'runtime-symbols.json').write_text(json.dumps(newsyms,indent=2)+'\n')
(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
subprocess.run(['llvm-objdump','-d',str(candidate)],stdout=(out/'disassembly.txt').open('w'),check=True)
print(json.dumps(report,indent=2))
