"""Relink batched GPU mappings on the pinned v62d display/fence kernel.

Two small function groups occupy unused tails of independently audited old
GPU bodies. The producer-fence and display instructions stay byte-identical.
"""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess

p=argparse.ArgumentParser();p.add_argument('--attempt',default='v63');args=p.parse_args()
assert re.fullmatch(r'v63[a-z]?',args.attempt)
root=Path(__file__).resolve().parents[1];out=root/('out/lmi-gpu-map-'+args.attempt)
assert not out.exists();out.mkdir()
sha=lambda b:hashlib.sha256(b).hexdigest()
base=root/'out/lmi-display-fast-v62d/mach.development.bcm2837';raw=base.read_bytes()
assert sha(raw)=='c5f46d3325de6c52b6b5698ac7d24cbd1f1c07829e0d2305674921dade7ad373'
prior=root/'out/lmi-gpu-async-v58h'
old=(prior/'mach.development.bcm2837').read_bytes()
assert sha(old)=='52068a7d3c30af9cbbaea89cf906f61848c607f82d3e3bc7a7a35bdc1f14c0ea'
module=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))
segs=module['segments'](raw)

def at(pc,n=4):
    found=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(found)==1;return found[0]

def elf(path):
    b=path.read_bytes();assert b[:6]==b'\x7fELF\x02\x01'
    offset=struct.unpack_from('<Q',b,40)[0];size,count,ns=struct.unpack_from('<HHH',b,58)
    hs=[struct.unpack_from('<IIQQQQIIQQ',b,offset+i*size) for i in range(count)]
    strings=b[hs[ns][4]:hs[ns][4]+hs[ns][5]]
    return {strings[h[0]:strings.index(b'\0',h[0])].decode():(h[3],b[h[4]:h[4]+h[5]],h)
            for h in hs if h[0] and h[2]&2 and h[5]}

def syms(path):
    return {v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(path)],text=True).splitlines()
            if len(v:=line.split())==3}

def destination(w,pc):
    assert w&0x7c000000==0x14000000
    d=w&0x3ffffff;return pc+((d-(1<<26) if d&(1<<25) else d)*4)

oldelf=prior/'async.elf';before=elf(oldelf);oldsyms=syms(oldelf)
assert oldsyms==json.loads((prior/'runtime-symbols.json').read_text())
start=0xfffffff0074d9c88;end=0xfffffff0074db04c
assert before['.gpu_desktop'][0]==start
original=before['.gpu_desktop'][1]
assert old[at(start):at(start)+len(original)]==original
fast_syms=json.loads((root/'out/lmi-display-fast-v62d/runtime-symbols.json').read_text())
# v62 changes exactly this one BL within the GPU section to emit fence stats
# after the native SMP/DPU cleanup. Rebind the same call in the new link.
different=[]
for i in range(0,len(original),4):
    if raw[at(start)+i:at(start)+i+4]!=original[i:i+4]:different.append(i)
assert different==[oldsyms['lmi_gpu_async_return']+8-start]
pc=start+different[0]
assert destination(struct.unpack_from('<I',raw,at(pc))[0],pc)==fast_syms['lmi_fast_cleanup']

audit=json.loads((root/'out/lmi-replaced-gpu-body-audit-v62/result.json').read_text())
display=json.loads((root/'out/lmi-display-fast-v62d/build-audit.json').read_text())
assert audit['accepted_bytes']==3816 and audit['base_sha256']==sha(old)
regions={int(r['start'],16):r for r in audit['regions']}
extra={'.gpu_batch_aux_one':(0xfffffff0074d21d4,64),
       '.gpu_batch_aux_two':(0xfffffff0074d3220,72)}
for name,(lo,n) in extra.items():
    candidates=[r for a,r in regions.items() if a<=lo and lo+n<=a+r['bytes']]
    assert len(candidates)==1 and candidates[0]['accepted']
    assert not any(candidates[0][k] for k in ['external_references','interior_page_references','interior_pointers','unwind_references'])
    assert not any(int(s['start'],16)<lo+n and lo<int(s['start'],16)+s['bytes'] for s in display['sections'])
    assert raw[at(lo):at(lo)+n]==old[at(lo):at(lo)+n]

frozen=root/'out/lmi-kernel-ios-continue'
builder=(root/'tools/build-lmi-ios-probe.py').read_text()
order=['touch.o']+re.findall(r"touch_objects\.append\(str\(out/'([^']+\.o)'\)\)",builder)
objects=[frozen/n for n in order if (frozen/n).exists()]
assert {v.name for v in frozen.glob('*.o')}=={'probe.o',*[v.name for v in objects]}
flags=['--target=aarch64-none-elf','-Oz','-mllvm','-enable-machine-outliner=always',
       '-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
       '-mgeneral-regs-only','-fno-stack-protector','-Wall','-Wextra','-Werror']
obj=out/'gpu-desktop.o'
subprocess.run(['clang',*flags,'-c',str(root/'tools/lmi-gpu-desktop-v63.c'),'-o',str(obj)],check=True)
bindings=module['elf_absolutes'](oldelf.read_bytes())
bindings['lmi_display_smp_prepare']=fast_syms['lmi_fast_cleanup']
script=(prior/'async.ld').read_text()
needle='          .gpu_context'
assert script.count(needle)==1
script=script.replace(needle,''.join(f'          {name} {lo:#x} : {{ *({name}) }}\n' for name,(lo,n) in extra.items())+needle)
(out/'batch.ld').write_text(script)
abi=runpy.run_path(str(root/'tools/lmi-gpu-desktop-profile.py'))['ABI']
linked=out/'batch.elf'
subprocess.run(['ld.lld','-T',str(out/'batch.ld'),'--entry=lmi_touch_thread','--gc-sections',
    '--undefined=lmi_gpu_probe','--undefined=lmi_gpu_async_return',
    *['--undefined=lmi_desktop_'+n for n in sorted({v[2] for v in abi.values()})],
    *[f'--defsym={n}={a:#x}' for n,a in bindings.items()],
    *[str(obj if v.name=='gpu-desktop.o' else v) for v in objects],'-o',str(linked)],check=True)
after=elf(linked);newsyms=syms(linked)
assert set(after)==set(before)|set(extra)
assert after['.gpu_desktop'][0]==start and len(after['.gpu_desktop'][1])<=end-start
result=bytearray(raw);ranges=[];placed=[]
for name,(lo,capacity) in {'.gpu_desktop':(start,end-start),**extra}.items():
    pc,data,h=after[name]
    assert pc==lo and len(data)<=capacity and h[8]>=4 and pc%4==0
    result[at(pc):at(pc)+len(data)]=data;ranges.append([at(pc),at(pc)+len(data)])
    placed.append(dict(section=name,start=hex(lo),bytes=len(data),capacity=capacity))
relocations=[]
for name,(pc,data,h) in before.items():
    if name=='.gpu_desktop':continue
    assert after[name][0]==pc and len(after[name][1])==len(data)
    for i in range(0,len(data),4):
        b=after[name][1][i:i+4]
        if data[i:i+4]==b:continue
        a,w=struct.unpack_from('<I',data,i)[0],struct.unpack('<I',b)[0]
        assert a&0xfc000000==w&0xfc000000 and a&0x7c000000==0x14000000
        was,now=destination(a,pc+i),destination(w,pc+i)
        names=[n for n,v in oldsyms.items() if v==was and start<=v<end]
        assert len(names)==1 and newsyms[names[0]]==now
        assert raw[at(pc+i):at(pc+i)+4]==data[i:i+4]
        result[at(pc+i):at(pc+i)+4]=b;ranges.append([at(pc+i),at(pc+i)+4])
        relocations.append(dict(pc=hex(pc+i),symbol=names[0],before=hex(was),after=hex(now)))
hooks=[]
for symbol,(pc,original_word,entry) in abi.items():
    assert destination(struct.unpack_from('<I',raw,at(pc))[0],pc)==oldsyms['lmi_desktop_'+entry]
    dest=newsyms['lmi_desktop_'+entry]
    assert -(1<<27)<=dest-pc<(1<<27) and (dest-pc)%4==0
    struct.pack_into('<I',result,at(pc),0x14000000|(((dest-pc)//4)&0x3ffffff))
    ranges.append([at(pc),at(pc)+4]);hooks.append(dict(pc=hex(pc),symbol='lmi_desktop_'+entry,target=hex(dest)))
pc=0xfffffff007460cd0
assert destination(struct.unpack_from('<I',raw,at(pc))[0],pc)==oldsyms['lmi_gpu_async_return']
dest=newsyms['lmi_gpu_async_return']
struct.pack_into('<I',result,at(pc),0x94000000|(((dest-pc)//4)&0x3ffffff))
ranges.append([at(pc),at(pc)+4]);hooks.append(dict(pc=hex(pc),symbol='lmi_gpu_async_return',target=hex(dest)))
check=bytearray(result)
for a,b in ranges:check[a:b]=raw[a:b]
assert check==raw and len(result)==len(raw)
# Retain all v62 display/fence hooks and all occupied body instructions.
for s in display['sections']:
    lo=int(s['start'],16);n=s['bytes'];assert result[at(lo):at(lo)+n]==raw[at(lo):at(lo)+n]
for h in display['hooks']:
    pc=int(h['pc'],16)
    if h['symbol']=='lmi_fast_cleanup':
        assert start<=pc<end
        continue  # Same cleanup call was rebound in the newly linked wrapper.
    assert result[at(pc):at(pc)+4]==raw[at(pc):at(pc)+4]
cleanup_calls=[]
for offset in range(0,len(after['.gpu_desktop'][1])-3,4):
    pc=start+offset;w=struct.unpack_from('<I',result,at(pc))[0]
    if w&0xfc000000==0x94000000 and destination(w,pc)==fast_syms['lmi_fast_cleanup']:
        cleanup_calls.append(pc)
assert len(cleanup_calls)==1
host=json.loads((root/'out/lmi-gpu-map-v63-host/result.json').read_text())
assert host['result']=='PASS' and host['asan_ubsan'] and len(host['mutations_caught'])==5
for n,digest in host['sources'].items():assert sha((root/'tools'/n).read_bytes())==digest
names=['build-lmi-gpu-map-v63.py','lmi-gpu-desktop-v63.c','lmi-gpu-boot-regs.h','lmi-gpu-desktop-profile.py']
report=dict(result='HOST_BUILT_ONLY',sha256=sha(result),base_sha256=sha(raw),
    sources={n:sha((root/'tools'/n).read_bytes()) for n in names},
    inputs={str(q.relative_to(root)):sha(q.read_bytes()) for q in [oldelf,prior/'async.ld',
       root/'out/lmi-display-fast-v62d/build-audit.json',root/'out/lmi-replaced-gpu-body-audit-v62/result.json',
       root/'out/lmi-gpu-map-v63-host/result.json',root/'hackios/xnu/files/iokit/Kernel/RedwoodGPU.cpp']},
    object_inputs={v.name:sha(v.read_bytes()) for v in objects},
    compile_flags=flags,allowed_file_ranges=ranges,sections=placed,branch_relocations=relocations,hooks=hooks,
    outside_edits_exact=True,display_fence_bytes_preserved=True,cleanup_rebound_to_v62=True,
    cleanup_call=hex(cleanup_calls[0]),
    dma_attributes_unchanged=True,first_page_real_drain=True,commit_real_drain=True,
    native_map_batch_under_gpu_lock=True,single_outstanding=True,direct_surface_dma=False,
    hardware_tested=False,performance_verified=False)
(out/'mach.development.bcm2837').write_bytes(result)
(out/'runtime-symbols.json').write_text(json.dumps(newsyms,indent=2)+'\n')
(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
print(json.dumps(dict(sha256=report['sha256'],sections=placed),indent=2))
