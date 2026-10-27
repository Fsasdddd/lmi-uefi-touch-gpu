"""Bounded one-copy full-frame hooks on the exact qualified v58 image.

Only audited dead GPU interiors and three verified BL instructions may change.
Original entries, touch, DMA/scaler, frequencies and GPU async exit remain.
WSL/host only, no device access.
"""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v60');args=p.parse_args()
assert re.fullmatch(r'v60[a-z]?',args.attempt)
root=Path(__file__).resolve().parents[1];out=root/('out/lmi-display-fast-'+args.attempt)
assert not out.exists();out.mkdir()
sha=lambda b:hashlib.sha256(b).hexdigest()
raw=(root/'out/lmi-gpu-async-v58h/mach.development.bcm2837').read_bytes()
assert sha(raw)=='52068a7d3c30af9cbbaea89cf906f61848c607f82d3e3bc7a7a35bdc1f14c0ea'
audit_path=root/'out/lmi-replaced-gpu-body-audit/result.json'
audit_raw=audit_path.read_bytes();audit=json.loads(audit_raw)
# Audit contents are frozen in this builder, rather than trusting editable ranges.
regions=[(0xfffffff0074d2a04,200),(0xfffffff0074d30b0,112),(0xfffffff0074d3124,324),
         (0xfffffff0074d3274,36),(0xfffffff0074d32a8,136),(0xfffffff0074d34fc,928),
         (0xfffffff0074d3968,512),(0xfffffff0074d3c54,768)]
assert audit['base_sha256']==sha(raw) and audit['accepted_bytes']==3016
assert [(int(r['start'],16),r['bytes']) for r in audit['regions']]==regions
assert all(r['accepted'] and not any(r[n] for n in ['external_references','interior_page_references','interior_pointers','unwind_references']) for r in audit['regions'])
module=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'));segs=module['segments'](raw)
symbols={n:a for a,k,n in module['symbols']((root/'out/lmi-display-probe-v56f/kernel-symbols.txt').read_text())}
def at(pc,n=4):
    hits=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(hits)==1;return hits[0]
for r in audit['regions']:
    lo=int(r['start'],16);n=r['bytes']
    assert r['file_offset']==at(lo,n) and sha(raw[at(lo):at(lo)+n])==r['body_sha256']
    assert struct.unpack_from('<I',raw,at(lo-4))[0]==int(r['entry_branch'],16)
layout=json.loads((root/'out/lmi-direct-surface-layout/layout.json').read_text())
header=root/'hackios/xnu/files/iokit/Kernel/MiniIOSurface.h'
assert sha(header.read_bytes())==layout['source_sha256']=='48f962c8ce00188d79f5dc2ef8cb67891d532e4c163d59f19877f09d0fe1af83'
assert layout['class_bytes']==728
expected='/* Compiled from the real MiniIOSurface.h; checked against layout.json. */\n#ifndef LMI_DISPLAY_SURFACE_ABI_H\n#define LMI_DISPLAY_SURFACE_ABI_H\n'
for name,value in layout['offsets'].items():expected+=f'#define LMI_SURF_{name} {value}u\n'
expected+='#endif\n'
assert (root/'tools/lmi-display-surface-abi.h').read_text()==expected
# Only the unused eight bytes after the exact 24-byte state journal are used
# for a pointer. All data bytes in the file remain zero and unchanged.
state=symbols['_state'];pad=state+24
assert state==0xfffffff007b46fe0 and pad+8==0xfffffff007b47000
assert raw[at(state,32):at(state,32)+32]==bytes(32)
assert not any(pad<=a<pad+8 for a in symbols.values())
assert not any(pad<=struct.unpack_from('<Q',raw,i)[0]<pad+8 for i in range(0,len(raw)-7,4))
names=['lmi-display-fast-v60.c','lmi-display-fast-v60.h','lmi-display-surface-abi.h',
       'lmi-display-direct-plan.c','lmi-display-direct-plan.h','lmi-display-compositor.h',
       'lmi-display-compositor-abi.h','lmi-display-pipeline.h','build-lmi-display-v60.py']
flags=['--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding',
       '-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-Wall','-Wextra','-Werror']
objects=[]
for source in ['lmi-display-fast-v60.c','lmi-display-direct-plan.c']:
    dest=out/(Path(source).stem+'.o');objects.append(dest)
    subprocess.run(['clang',*flags,'-c',str(root/'tools'/source),'-o',str(dest)],check=True)
def elf(path):
    b=path.read_bytes();assert b[:6]==b'\x7fELF\x02\x01'
    off=struct.unpack_from('<Q',b,40)[0];size,count,ns=struct.unpack_from('<HHH',b,58)
    hs=[struct.unpack_from('<IIQQQQIIQQ',b,off+i*size) for i in range(count)]
    ss=b[hs[ns][4]:hs[ns][4]+hs[ns][5]]
    return {ss[h[0]:ss.index(b'\0',h[0])].decode():(h,b[h[4]:h[4]+h[5]]) for h in hs if h[0] and h[2]&2 and h[5]}
sections=[]
for obj in objects:
    for name,(h,data) in elf(obj).items():
        assert not h[2]&1 and h[1]==1 and name.startswith(('.text.','.rodata.'))
        sections.append((obj,name,len(data),h[8]))
# First-fit decreasing with alignment, without expanding ANY audited range.
slots=[dict(start=lo,capacity=n,used=0,inputs=[]) for lo,n in regions]
for obj,name,n,align in sorted(sections,key=lambda v:-v[2]):
    fit=[(s['capacity']-((s['used']+align-1)&-align)-n,i) for i,s in enumerate(slots) if ((s['used']+align-1)&-align)+n<=s['capacity']]
    assert fit,('Reject code-space overflow',name,n)
    _,i=min(fit);s=slots[i];s['used']=((s['used']+align-1)&-align)+n;s['inputs'].append((obj.name,name))
script='SECTIONS {\n'
for i,s in enumerate(slots):
    if not s['inputs']:continue
    script+=f".slot{i} {s['start']:#x} : {{ "+' '.join(f'KEEP(*{obj}({section}))' for obj,section in s['inputs'])+' }\n'
script+=' /DISCARD/ : { *(.comment .note* .llvm_addrsig) }\n}\n'
(out/'fast.ld').write_text(script)
bindings=dict(lmi_fast_state=pad,lmi_fast_original_fields=symbols['_original_fields'],
    lmi_fast_original_frame=symbols['_lmi_compositor_frame'],lmi_fast_original_draw=symbols['__ZN19IOMobileFramebuffer9drawLayerEP13MiniIOSurfacePKiS3_'],
    lmi_fast_original_cleanup=symbols['_lmi_display_smp_prepare'],IOMallocAligned=symbols['_IOMallocAligned'],
    memcpy=symbols['_memcpy'],memset=symbols['_memset'],bzero=symbols['_bzero'],loader_log_line=symbols['_loader_log_line'])
linked=out/'fast.elf'
subprocess.run(['ld.lld','-T',str(out/'fast.ld'),'--entry=lmi_fast_frame',*map(str,objects),
    *[f'--defsym={n}={v:#x}' for n,v in bindings.items()],'-o',str(linked)],check=True)
newsyms={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(linked)],text=True).splitlines() if len(v:=line.split())==3}
result=bytearray(raw);edits=[];placed=[]
for name,(h,data) in elf(linked).items():
    assert name.startswith('.slot');s=slots[int(name[5:])]
    assert h[3]==s['start'] and len(data)<=s['capacity']
    offset=at(h[3],len(data));result[offset:offset+len(data)]=data;edits.append([offset,offset+len(data)])
    placed.append(dict(section=name,start=hex(h[3]),bytes=len(data),capacity=s['capacity'],inputs=s['inputs']))
def destination(w,pc):
    d=w&0x3ffffff;return pc+((d-(1<<26) if d&(1<<25) else d)*4)
hooks=[]
for old,new in [('lmi_fast_original_frame','lmi_fast_frame'),('lmi_fast_original_draw','lmi_fast_draw'),('lmi_fast_original_cleanup','lmi_fast_cleanup')]:
    # Scan the exact live image, accepting only one BL caller for each hook.
    calls=[]
    for va,vs,fo,fs in segs.values():
        if not fs:continue
        for i in range(0,fs-3,4):
            w=struct.unpack_from('<I',raw,fo+i)[0]
            if w&0xfc000000==0x94000000 and destination(w,va+i)==bindings[old]:calls.append(va+i)
    assert len(calls)==1,(old,list(map(hex,calls)))
    pc=calls[0];dest=newsyms[new];assert abs(dest-pc)<(1<<27) and not (dest-pc)&3
    offset=at(pc);struct.pack_into('<I',result,offset,0x94000000|(((dest-pc)//4)&0x3ffffff))
    edits.append([offset,offset+4]);hooks.append(dict(pc=hex(pc),old=hex(bindings[old]),new=hex(dest),symbol=new))
check=bytearray(result)
for a,b in edits:check[a:b]=raw[a:b]
assert check==raw and len(result)==len(raw)
assert result[at(state,32):at(state,32)+32]==bytes(32)
for r in audit['regions']:
    offset=at(int(r['entry'],16));assert result[offset:offset+4]==raw[offset:offset+4]
report=dict(result='HOST_BUILT_ONLY',sha256=sha(result),base_sha256=sha(raw),sources={n:sha((root/'tools'/n).read_bytes()) for n in names},
    reused_region_audit_sha256=sha(audit_raw),surface_layout_sha256=sha((root/'out/lmi-direct-surface-layout/layout.json').read_bytes()),
    source_class_sha256=sha(header.read_bytes()),allowed_file_ranges=edits,sections=placed,hooks=hooks,
    bindings={n:hex(v) for n,v in bindings.items()},compile_flags=flags,abi_entries_preserved=True,outside_edits_exact=True,
    dma_mappings_unchanged=True,gpu_async_unchanged=True,touch_unchanged=True,native_show_queue_record_retained=True,
    full_frame_one_copy=True,direct_surface_dma=False,hardware_tested=False)
(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'runtime-symbols.json').write_text(json.dumps(newsyms,indent=2)+'\n')
(out/'mach.development.bcm2837').write_bytes(result)
subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
print(json.dumps(report,indent=2))
