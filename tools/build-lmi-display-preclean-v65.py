"""Pack preclean overlap only into proven-unused v64 tails; host-only build."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess
parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='v65');args=parser.parse_args()
assert re.fullmatch(r'v65[a-z]?',args.attempt)
root=Path(__file__).resolve().parents[1];out=root/('out/lmi-display-preclean-'+args.attempt)
assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
prior=root/'out/lmi-gpu-queue-v64b';base=prior/'mach.development.bcm2837';raw=base.read_bytes()
assert sha(base)=='ba8f526f57fd67fd9386c05a077bd1366e6f201e196d7cdebff23b6e884fea51'
helper=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'));segs=helper['segments'](raw)
native={n:a for a,k,n in helper['symbols']((root/'out/lmi-display-probe-v56f/kernel-symbols.txt').read_text())}
display=json.loads((root/'out/lmi-display-fast-v62d/runtime-symbols.json').read_text())
audit=json.loads((prior/'build-audit.json').read_text())
def off(pc,n=4):
    hits=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(hits)==1;return hits[0]
def signed(n,b):return n-(1<<b) if n&(1<<(b-1)) else n
def dest(w,pc):
    assert w&0x7c000000==0x14000000;return pc+4*signed(w&0x3ffffff,26)
def elf(path):
    b=path.read_bytes();assert b[:6]==b'\x7fELF\x02\x01'
    pos=struct.unpack_from('<Q',b,40)[0];size,count,ni=struct.unpack_from('<HHH',b,58)
    hs=[struct.unpack_from('<IIQQQQIIQQ',b,pos+i*size) for i in range(count)]
    strings=b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
    return {strings[h[0]:strings.index(b'\0',h[0])].decode():(h,b[h[4]:h[4]+h[5]]) for h in hs if h[0] and h[2]&2 and h[5]}
old_sections=elf(prior/'queue.elf')
segments=[];pos=32
for _ in range(struct.unpack_from('<I',raw,16)[0]):
    command,size=struct.unpack_from('<II',raw,pos)
    if command==25:
        va,vs,fo,fs=struct.unpack_from('<4Q',raw,pos+24)
        segments.append((va,fo,fs,struct.unpack_from('<I',raw,pos+60)[0],raw[pos+8:pos+24].split(b'\0')[0].decode()))
    pos+=size
sections=runpy.run_path(str(root/'tools/audit-lmi-gpu-normal-diag-region.py'))['sections'](raw)
eh=[s for s in sections if s[0]=='__eh_frame'];assert len(eh)==1
_,ev,en,ef,_,_=eh[0];eb=raw[ef:ef+en];assert struct.unpack_from('<II',eb)==(20,0)
unwind=[];pos=24
while pos<len(eb):
    length,cie=struct.unpack_from('<II',eb,pos);assert cie==pos+4 and length>=24
    pc=ev+pos+8+struct.unpack_from('<q',eb,pos+8)[0];span=struct.unpack_from('<Q',eb,pos+16)[0]
    unwind.append((pc,pc+span));pos+=length+4
assert pos==len(eb) and len(unwind)==4
slots=[];tail_audits=[]
for row in audit['sections']:
    if row['section'] not in {'.gpu_desktop','.gpu_queue','.gpu_handoff'}:continue
    h,data=old_sections[row['section']];lo=int(row['start'],16);assert h[3]==lo and len(data)==row['bytes']
    assert raw[off(lo,len(data)):off(lo)+len(data)]==data
    start=lo+len(data);end=lo+row['capacity'];assert start%4==0 and end%4==0
    refs=[];pages=[];pointers=[]
    for va,fo,fs,prot,name in segments:
        if prot==5:
            for i in range(0,fs-3,4):
                pc=va+i
                if start<=pc<end:continue
                w=struct.unpack_from('<I',raw,fo+i)[0];target=None
                if w&0x7c000000==0x14000000:target=dest(w,pc)
                elif w&0xff000010==0x54000000 or w&0x7e000000==0x34000000:target=pc+4*signed((w>>5)&0x7ffff,19)
                elif w&0x7e000000==0x36000000:target=pc+4*signed((w>>5)&0x3fff,14)
                elif w&0x9f000000==0x10000000:target=pc+signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)
                elif w&0x3b000000==0x18000000:target=pc+4*signed((w>>5)&0x7ffff,19)
                if target is not None and start<=target<end:refs.append([hex(pc),hex(target)])
                if w&0x9f000000!=0x90000000:continue
                page=(pc&~4095)+(signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)<<12)
                if not(start&~4095)<=page<((end+4095)&~4095):continue
                register=w&31
                for j in range(i+4,min(i+36,fs-3),4):
                    c=struct.unpack_from('<I',raw,fo+j)[0];target=None
                    if (c>>5)&31!=register:continue
                    if c&0xff000000==0x91000000:target=page+(((c>>10)&4095)<<(12 if c&(1<<22) else 0))
                    elif c&0x3b000000==0x39000000:target=page+(((c>>10)&4095)<<(c>>30))
                    if target is not None and start<=target<end:pages.append([hex(va+j),hex(target)])
        if name!='__LINKEDIT':
            for i in range(0,fs-7,4):
                if start<=va+i<end:continue
                if start<=struct.unpack_from('<Q',raw,fo+i)[0]<end:pointers.append(hex(va+i))
    uw=[list(map(hex,(a,z))) for a,z in unwind if a<end and start<z]
    row=dict(start=start,capacity=end-start,used=0,inputs=[],
        original_sha256=hashlib.sha256(raw[off(start):off(end)]).hexdigest(),
        direct_references=refs,page_references=pages,loaded_pointers=pointers,unwind_references=uw,
        accepted=not(refs or pages or pointers or uw))
    tail_audits.append(row)
    if row['accepted']:slots.append(row)
host_path=root/'out/lmi-display-preclean-v65-host/result.json';host=json.loads(host_path.read_text())
assert host['result']=='PASS' and host['asan_ubsan'] and host['separate_cpu_poc_views'] and len(host['mutations_caught'])==6
for n,d in host['sources'].items():assert sha(root/'tools'/n)==d
flags=['--target=aarch64-none-elf','-Oz','-mllvm','-enable-machine-outliner=always','-ffunction-sections',
       '-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-Wall','-Wextra','-Werror']
obj=out/'preclean.o';subprocess.run(['clang',*flags,'-c',str(root/'tools/lmi-display-preclean-v65.c'),'-o',str(obj)],check=True)
for name,(h,data) in sorted(elf(obj).items(),key=lambda v:-len(v[1][1])):
    assert h[1]==1 and not h[2]&1 and name.startswith(('.text.','.rodata.'))
    fit=[(s['capacity']-((s['used']+h[8]-1)&-h[8])-len(data),i) for i,s in enumerate(slots)
         if ((s['used']+h[8]-1)&-h[8])+len(data)<=s['capacity']]
    assert fit,('Code-space overflow',name,len(data));_,i=min(fit);s=slots[i]
    s['used']=((s['used']+h[8]-1)&-h[8])+len(data);s['inputs'].append(name)
script='SECTIONS {\n'
for i,s in enumerate(slots):
    if s['inputs']:script+=f".slot{i} {s['start']:#x} : {{ "+' '.join(f'KEEP(*({n}))' for n in s['inputs'])+' }\n'
script+=' /DISCARD/ : { *(.comment .note* .llvm_addrsig) }\n}\n';(out/'preclean.ld').write_text(script)
bindings={n:display[n] for n in ['lmi_fast_state','lmi_fast_frame','lmi_fast_cleanup','IOMallocAligned','bzero']}
bindings.update(lmi_preclean_original_clean=native['_lmi_dma_clean'],lmi_preclean_emit=display['emit'])
linked=out/'preclean.elf'
subprocess.run(['ld.lld','-T',str(out/'preclean.ld'),'--entry=lmi_preclean_frame',str(obj),
    *[f'--defsym={n}={v:#x}' for n,v in bindings.items()],'-o',str(linked)],check=True)
syms={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(linked)],text=True).splitlines() if len(v:=line.split())==3}
result=bytearray(raw);ranges=[];placed=[]
for name,(h,data) in elf(linked).items():
    s=slots[int(name[5:])];assert h[3]==s['start'] and len(data)<=s['capacity']
    at=off(h[3],len(data));result[at:at+len(data)]=data;ranges.append([at,at+len(data)])
    placed.append(dict(section=name,start=hex(h[3]),bytes=len(data),capacity=s['capacity'],inputs=s['inputs']))
hooks=[]
for pc,original,target in [(0xfffffff007ae00bc,display['lmi_fast_frame'],'lmi_preclean_frame'),
                           (0xfffffff0074d30e4,display['IOMallocAligned'],'lmi_preclean_allocate'),
                           (int(audit['cleanup_call'],16),display['lmi_fast_cleanup'],'lmi_preclean_cleanup')]:
    w=struct.unpack_from('<I',raw,off(pc))[0];assert w&0xfc000000==0x94000000 and dest(w,pc)==original
    if target=='lmi_preclean_allocate':
        assert struct.unpack_from('<II',raw,off(pc-8))==(0x52802300,0x52800201) # 280,16
        assert struct.unpack_from('<I',raw,off(pc+8))[0]==0x52802301 # native prefix bzero
    address=syms[target];assert address%4==0 and abs(address-pc)<1<<27
    struct.pack_into('<I',result,off(pc),0x94000000|(((address-pc)//4)&0x3ffffff));ranges.append([off(pc),off(pc)+4])
    hooks.append(dict(pc=hex(pc),original=hex(original),target=hex(address),symbol=target))
check=bytearray(result)
for a,z in ranges:check[a:z]=raw[a:z]
assert check==raw and len(result)==len(raw)
names=['lmi-display-preclean-v65.c','lmi-display-preclean-v65.h','build-lmi-display-preclean-v65.py',
       'lmi-display-fast-v62.h','lmi-display-dma.h','lmi-display-pipeline.h']
report=dict(result='HOST_BUILT_ONLY',sha256=hashlib.sha256(result).hexdigest(),base_sha256=sha(base),
    sources={n:sha(root/'tools'/n) for n in names},inputs={str(p.relative_to(root)):sha(p) for p in
        [base,prior/'build-audit.json',prior/'queue.elf',host_path,root/'out/lmi-display-fast-v62d/runtime-symbols.json']},
    compile_flags=flags,bindings={n:hex(v) for n,v in bindings.items()},tail_audits=tail_audits,sections=placed,hooks=hooks,
    allowed_file_ranges=ranges,outside_edits_exact=True,full_rx_segments_scanned=True,journal_prefix_bytes=280,
    gpu_queue_unchanged=True,dpu_fences_unchanged=True,source_retirement_unchanged=True,touch_unchanged=True,
    preclean_overlap=True,direct_surface_dma=False,wifi_integrated=False,hardware_tested=False,performance_verified=False)
(out/'mach.development.bcm2837').write_bytes(result);(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'runtime-symbols.json').write_text(json.dumps(syms,indent=2)+'\n')
subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
print(json.dumps(dict(sha256=report['sha256'],sections=placed,hooks=hooks),indent=2))
