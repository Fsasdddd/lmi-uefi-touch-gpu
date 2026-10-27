"""Build four-inflight A650 submission backend on exact v63c; no device access."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v64');args=p.parse_args()
assert re.fullmatch(r'v64[a-z]?',args.attempt)
root=Path(__file__).resolve().parents[1];out=root/('out/lmi-gpu-queue-'+args.attempt)
assert not out.exists();out.mkdir()
sha=lambda b:hashlib.sha256(b).hexdigest()
prior=root/'out/lmi-gpu-map-v63c';base=prior/'mach.development.bcm2837';raw=base.read_bytes()
assert sha(raw)=='baa6d3ef46691f8fbeb8fe93ffbbf31e2ebf6450bb4684e57d90873147d52ccc'
module=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'));segs=module['segments'](raw)
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

oldelf=prior/'batch.elf';before=elf(oldelf);oldsyms=syms(oldelf)
assert oldsyms==json.loads((prior/'runtime-symbols.json').read_text())
space_path=root/'out/lmi-display-quiesce-space-v64/result.json'
assert sha(space_path.read_bytes())=='af411c1ee31b24d2d6664b097aee206cd8d650d50ee3a4b5067e2f45289c14f9'
space=json.loads(space_path.read_text())
assert space['base_sha256']==sha(raw) and space['full_rx_segments_scanned'] and space['accepted_bytes']==2156
regions={r['symbol']:r for r in space['regions'] if r['accepted']}
assert set(regions)=={'_gpu_block_stop','_gpu_times'}
extra={'.gpu_queue':(0xfffffff0074d22f8,1708),'.gpu_handoff':(0xfffffff0074d3338,448)}
for symbol,(lo,capacity) in zip(['_gpu_block_stop','_gpu_times'],extra.values()):
    r=regions[symbol];assert int(r['start'],16)==lo and r['bytes']==capacity and int(r['entry'],16)==lo-8
    assert list(struct.unpack_from('<II',raw,at(lo-8)))==r['original_entry_words']
    assert sha(raw[at(lo):at(lo)+capacity])==r['body_sha256']
    assert not any(r[n] for n in ['direct_references','page_references','loaded_pointers','unwind_references'])
start=0xfffffff0074d9c88;end=0xfffffff0074db04c
replace={'.gpu_desktop':(start,end-start),'.gpu_batch_aux_one':(0xfffffff0074d21d4,64),
         '.gpu_batch_aux_two':(0xfffffff0074d3220,72)}
for name,(pc,capacity) in replace.items():
    assert before[name][0]==pc and len(before[name][1])<=capacity
    assert raw[at(pc):at(pc)+len(before[name][1])]==before[name][1]
frozen=root/'out/lmi-kernel-ios-continue'
builder=(root/'tools/build-lmi-ios-probe.py').read_text()
order=['touch.o']+re.findall(r"touch_objects\.append\(str\(out/'([^']+\.o)'\)\)",builder)
objects=[frozen/n for n in order if (frozen/n).exists()]
assert {v.name for v in frozen.glob('*.o')}=={'probe.o',*[v.name for v in objects]}
flags=['--target=aarch64-none-elf','-Oz','-mllvm','-enable-machine-outliner=always',
       '-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
       '-mgeneral-regs-only','-fno-stack-protector','-Wall','-Wextra','-Werror']
obj=out/'gpu-desktop.o'
subprocess.run(['clang',*flags,'-c',str(root/'tools/lmi-gpu-desktop-v64.c'),'-o',str(obj)],check=True)
bindings=module['elf_absolutes'](oldelf.read_bytes())
script=(prior/'batch.ld').read_text();needle='          .gpu_context'
assert script.count(needle)==1
script=script.replace(needle,''.join(f'          {n} {lo:#x} : {{ *({n}) }}\n' for n,(lo,c) in extra.items())+needle)
(out/'queue.ld').write_text(script)
abi=runpy.run_path(str(root/'tools/lmi-gpu-desktop-profile.py'))['ABI']
linked=out/'queue.elf';effective=[obj if v.name=='gpu-desktop.o' else v for v in objects]
link=['ld.lld','-T',str(out/'queue.ld'),'--entry=lmi_touch_thread','--gc-sections',
    '--undefined=lmi_gpu_probe','--undefined=lmi_gpu_async_return',
    *['--undefined=lmi_desktop_'+n for n in sorted({v[2] for v in abi.values()})],
    *[f'--defsym={n}={a:#x}' for n,a in bindings.items()],*[str(v) for v in effective],'-o',str(linked)]
subprocess.run(link,check=True);after=elf(linked);newsyms=syms(linked)
assert set(after)==set(before)|set(extra)
result=bytearray(raw);ranges=[];placed=[]
for name,(lo,capacity) in {**replace,**extra}.items():
    pc,data,h=after[name];assert pc==lo and len(data)<=capacity and pc%4==0
    result[at(pc):at(pc)+len(data)]=data;ranges.append([at(pc),at(pc)+len(data)])
    placed.append(dict(section=name,start=hex(lo),bytes=len(data),capacity=capacity))
for r in regions.values():
    pc=int(r['entry'],16);struct.pack_into('<II',result,at(pc),0x52800000,0xd65f03c0)
    ranges.append([at(pc),at(pc)+8])
relocations=[]
for name,(pc,data,h) in before.items():
    if name in replace:continue
    assert after[name][0]==pc and len(after[name][1])==len(data)
    for i in range(0,len(data),4):
        b=after[name][1][i:i+4]
        if data[i:i+4]==b:continue
        a,w=struct.unpack_from('<I',data,i)[0],struct.unpack('<I',b)[0]
        assert a&0xfc000000==w&0xfc000000 and a&0x7c000000==0x14000000
        was,now=destination(a,pc+i),destination(w,pc+i)
        names=[n for n,v in oldsyms.items() if v==was and any(lo<=v<lo+c for lo,c in replace.values())]
        assert len(names)==1 and newsyms[names[0]]==now
        assert raw[at(pc+i):at(pc+i)+4]==data[i:i+4]
        result[at(pc+i):at(pc+i)+4]=b;ranges.append([at(pc+i),at(pc+i)+4])
        relocations.append(dict(pc=hex(pc+i),symbol=names[0],before=hex(was),after=hex(now)))
hooks=[]
for symbol,(pc,original_word,entry) in abi.items():
    assert destination(struct.unpack_from('<I',raw,at(pc))[0],pc)==oldsyms['lmi_desktop_'+entry]
    dest=newsyms['lmi_desktop_'+entry];assert -(1<<27)<=dest-pc<(1<<27) and (dest-pc)%4==0
    struct.pack_into('<I',result,at(pc),0x14000000|(((dest-pc)//4)&0x3ffffff))
    ranges.append([at(pc),at(pc)+4]);hooks.append(dict(pc=hex(pc),symbol='lmi_desktop_'+entry,target=hex(dest)))
pc=0xfffffff007460cd0
assert destination(struct.unpack_from('<I',raw,at(pc))[0],pc)==oldsyms['lmi_gpu_async_return']
dest=newsyms['lmi_gpu_async_return'];assert -(1<<27)<=dest-pc<(1<<27) and (dest-pc)%4==0
struct.pack_into('<I',result,at(pc),0x94000000|(((dest-pc)//4)&0x3ffffff))
ranges.append([at(pc),at(pc)+4]);hooks.append(dict(pc=hex(pc),symbol='lmi_gpu_async_return',target=hex(dest)))
check=bytearray(result)
for a,b in ranges:check[a:b]=raw[a:b]
assert check==raw and len(result)==len(raw)
display_path=root/'out/lmi-display-fast-v62d/build-audit.json'
display=json.loads(display_path.read_text())
for s in display['sections']:
    lo=int(s['start'],16);n=s['bytes'];assert result[at(lo):at(lo)+n]==raw[at(lo):at(lo)+n]
for h in display['hooks']:
    if h['symbol']=='lmi_fast_cleanup':continue
    pc=int(h['pc'],16);assert result[at(pc):at(pc)+4]==raw[at(pc):at(pc)+4]
cleanup=json.loads((root/'out/lmi-display-fast-v62d/runtime-symbols.json').read_text())['lmi_fast_cleanup']
calls=[]
for name,(pc,data,h) in after.items():
    if name not in set(replace)|set(extra):continue
    for i in range(0,len(data)-3,4):
        w=struct.unpack_from('<I',data,i)[0]
        if w&0xfc000000==0x94000000 and destination(w,pc+i)==cleanup:calls.append(pc+i)
assert len(calls)==1
host_path=root/'out/lmi-gpu-queue-v64-host/result.json';host=json.loads(host_path.read_text())
native_path=root/'out/lmi-gpu-map-v64-native-host/result.json';native=json.loads(native_path.read_text())
assert host['result']=='PASS' and host['scenarios']==50 and host['asan_ubsan'] and len(host['mutations_caught'])==7
assert native['result']=='PASS' and native['scenarios']==16 and native['asan_ubsan']
for n,d in host['sources'].items():assert sha((root/'tools'/n).read_bytes())==d
for n,d in native['inputs'].items():assert sha((root/n).read_bytes())==d
assert sha((root/'out/lmi-gpu-map-v64-native-host/check.c').read_bytes())==native['generated_source_sha256']
names=['build-lmi-gpu-queue-v64.py','lmi-gpu-desktop-v64.c','lmi-gpu-boot-regs.h','lmi-gpu-desktop-profile.py']
inputs=[base,oldelf,prior/'batch.ld',space_path,display_path,host_path,native_path,
        root/'hackios/xnu/files/iokit/Kernel/RedwoodGPU.cpp']
report=dict(result='HOST_BUILT_ONLY',sha256=sha(result),base_sha256=sha(raw),
    sources={n:sha((root/'tools'/n).read_bytes()) for n in names},
    inputs={str(v.relative_to(root)):sha(v.read_bytes()) for v in inputs},
    effective_object_inputs={str(v.relative_to(root)):sha(v.read_bytes()) for v in effective},
    compile_flags=flags,allowed_file_ranges=ranges,sections=placed,branch_relocations=relocations,hooks=hooks,
    outside_edits_exact=True,display_fence_bytes_preserved=True,cleanup_rebound_to_v62=True,cleanup_call=hex(calls[0]),
    dma_attributes_unchanged=True,first_page_real_drain=True,commit_real_drain=True,max_inflight=4,
    null_handoff_dsb_only=True,real_cache_ranges_drain=True,actual_scratch_retirement=True,rptr_space_checked=True,
    obsolete_entry_stubs=True,direct_surface_dma=False,wifi_integrated=False,
    hardware_tested=False,performance_verified=False)
(out/'mach.development.bcm2837').write_bytes(result)
(out/'runtime-symbols.json').write_text(json.dumps(newsyms,indent=2)+'\n')
(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
print(json.dumps(dict(sha256=report['sha256'],sections=placed),indent=2))

