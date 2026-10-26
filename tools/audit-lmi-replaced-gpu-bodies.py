"""Find bounded RX space behind the current GPU ABI branches; read-only.

Never admit a whole old function and its following private helpers together.
Preserve every public entry branch and reject external interior references.
"""
from pathlib import Path
import bisect,hashlib,json,runpy,struct
root=Path(__file__).resolve().parents[1]
base=root/'out/lmi-gpu-async-v58h/mach.development.bcm2837';raw=base.read_bytes()
sha=hashlib.sha256(raw).hexdigest()
assert sha=='52068a7d3c30af9cbbaea89cf906f61848c607f82d3e3bc7a7a35bdc1f14c0ea'
module=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))
syms=module['symbols']((root/'out/lmi-display-probe-v56f/kernel-symbols.txt').read_text())
symbols={n:a for a,k,n in syms};addresses=sorted(set(a for a,k,n in syms))
runtime=json.loads((root/'out/lmi-gpu-async-v58h/runtime-symbols.json').read_text())
abi=runpy.run_path(str(root/'tools/lmi-gpu-desktop-profile.py'))['ABI']
sections=runpy.run_path(str(root/'tools/audit-lmi-gpu-normal-diag-region.py'))['sections'](raw)
assert not any(s[0] in ('__unwind_info','__compact_unwind') for s in sections)
# This image has four exception-vector FDEs, not an empty unwind section.
# Parse its exact CIE encoding rather than ignoring encoded PC references.
eh=[s for s in sections if s[0]=='__eh_frame'];assert len(eh)==1
_,ehva,ehsize,ehfo,_,_=eh[0];ehraw=raw[ehfo:ehfo+ehsize]
assert struct.unpack_from('<II',ehraw)==(20,0) and ehraw[8:18]==b'\x01zRS\x00\x01\x78\x1e\x01\x10'
unwind=[];pos=24
while pos<len(ehraw):
    length,cie=struct.unpack_from('<II',ehraw,pos)
    assert length>=24 and pos+4+length<=len(ehraw) and cie==pos+4
    pc=ehva+pos+8+struct.unpack_from('<q',ehraw,pos+8)[0]
    span=struct.unpack_from('<Q',ehraw,pos+16)[0];assert span
    unwind.append((pc,pc+span));pos+=length+4
assert pos==len(ehraw) and len(unwind)==4
def off(pc,n=4):
    found=[s[3]+pc-s[1] for s in sections if s[1]<=pc and pc+n<=s[1]+s[2]]
    assert len(found)==1;return found[0]
def signed(v,b):return v-(1<<b) if v&(1<<(b-1)) else v
def branch(w,pc):return pc+signed(w&0x3ffffff,26)*4
names=['_redwood_gpu_parameter','_redwood_gpu_mapped','_redwood_gpu_unmap',
    '_redwood_gpu_to_memory','_redwood_gpu_worked','_redwood_gpu_submit','_redwood_gpu_report','_redwood_gpu_recover']
reports=[]
for name in names:
    pc,old,entry=abi[name];assert symbols[name]==pc
    first=struct.unpack_from('<I',raw,off(pc))[0]
    assert first&0xfc000000==0x14000000 and branch(first,pc)==runtime['lmi_desktop_'+entry]
    lo=pc+4;hi=addresses[bisect.bisect_right(addresses,pc)]
    assert 4<=hi-lo<=4096
    cover=[s for s in sections if s[1]<=lo<hi<=s[1]+s[2]]
    assert len(cover)==1 and cover[0][5]==5 and cover[0][4]&0x80000400
    refs=[];page_refs=[]
    for section,va,size,fo,flags,prot in sections:
        if not flags&0x80000400:continue
        for i in range(0,size-3,4):
            here=va+i
            if lo<=here<hi:continue
            w=struct.unpack_from('<I',raw,fo+i)[0];target=None
            if w&0x7c000000==0x14000000:target=branch(w,here)
            elif w&0xff000010==0x54000000 or w&0x7e000000==0x34000000:target=here+signed((w>>5)&0x7ffff,19)*4
            elif w&0x7e000000==0x36000000:target=here+signed((w>>5)&0x3fff,14)*4
            elif w&0x9f000000==0x10000000:target=here+signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)
            elif w&0x3b000000==0x18000000:target=here+signed((w>>5)&0x7ffff,19)*4
            if target is not None and lo<=target<hi:refs.append([hex(here),hex(target),'direct/PC-relative'])
            if w&0x9f000000!=0x90000000:continue
            page=(here&~4095)+(signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)<<12)
            if not (lo&~4095)<=page<((hi+4095)&~4095):continue
            reg=w&31
            for j in range(i+4,min(i+36,size-3),4):
                c=struct.unpack_from('<I',raw,fo+j)[0];dest=None
                if (c>>5)&31!=reg:continue
                if c&0xff000000==0x91000000:dest=page+(((c>>10)&4095)<<(12 if c&(1<<22) else 0))
                elif c&0x3b000000==0x39000000:dest=page+(((c>>10)&4095)<<(c>>30))
                if dest is not None and lo<=dest<hi:page_refs.append([hex(va+j),hex(dest)])
    pointers=[i for i in range(0,len(raw)-7,4) if lo<=struct.unpack_from('<Q',raw,i)[0]<hi]
    unwind_refs=[(hex(a),hex(b)) for a,b in unwind if a<hi and lo<b]
    accepted=not(refs or page_refs or pointers or unwind_refs)
    reports.append(dict(symbol=name,entry=hex(pc),entry_branch=hex(first),target=hex(branch(first,pc)),
        start=hex(lo),end=hex(hi),bytes=hi-lo,file_offset=off(lo,hi-lo),accepted=accepted,
        body_sha256=hashlib.sha256(raw[off(lo):off(lo)+hi-lo]).hexdigest(),
        external_references=refs,interior_page_references=page_refs,interior_pointers=[hex(v) for v in pointers],unwind_references=unwind_refs))
out=root/'out/lmi-replaced-gpu-body-audit';out.mkdir(exist_ok=True)
report=dict(result='READ_ONLY_AUDIT',base_sha256=sha,regions=reports,accepted_bytes=sum(r['bytes'] for r in reports if r['accepted']),
    hardware_tested=False,kernel_emitted=False,limitation='A future builder must pin this report, preserve each ABI entry, recheck current preimages and bound every code section.')
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
