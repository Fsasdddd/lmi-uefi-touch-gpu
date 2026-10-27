"""Audit unused native GPU helper bodies in the exact v63c RX segments.

Scan entire executable segments, including injected padding, and preserve a
false-return entry stub. No current direct entry caller or loaded entry pointer
is admitted. Debug symbol table references are not executable callers.
"""
from pathlib import Path
import bisect,hashlib,json,runpy,struct
root=Path(__file__).resolve().parents[1]
base=root/'out/lmi-gpu-map-v63c/mach.development.bcm2837';raw=base.read_bytes()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(base)=='baa6d3ef46691f8fbeb8fe93ffbbf31e2ebf6450bb4684e57d90873147d52ccc'
helper=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))
syms=helper['symbols']((root/'out/lmi-display-probe-v56f/kernel-symbols.txt').read_text())
symbols={name:pc for pc,kind,name in syms};addresses=sorted(set(pc for pc,kind,name in syms))
segs=helper['segments'](raw)
sections=runpy.run_path(str(root/'tools/audit-lmi-gpu-normal-diag-region.py'))['sections'](raw)
rx=[s for s in sections if s[5]==5]
# __TEXT_EXEC is the only RX segment containing these bodies. Include all of
# its file bytes, including new code beyond declared section boundaries.
pos=32;segments=[]
for _ in range(struct.unpack_from('<I',raw,16)[0]):
    cmd,size=struct.unpack_from('<II',raw,pos)
    if cmd==25:
        va,vs,fo,fs=struct.unpack_from('<4Q',raw,pos+24);prot=struct.unpack_from('<I',raw,pos+60)[0]
        segments.append((va,fo,fs,prot,raw[pos+8:pos+24].split(b'\0')[0].decode()))
    pos+=size
def off(pc,n=4):
    hits=[fo+pc-va for va,fo,fs,prot,name in segments if va<=pc and pc+n<=va+fs]
    assert len(hits)==1;return hits[0]
def signed(v,b):return v-(1<<b) if v&(1<<(b-1)) else v
# Parse the exact native exception-vector unwind records, never assume empty.
eh=[s for s in sections if s[0]=='__eh_frame'];assert len(eh)==1
_,ehva,ehsize,ehfo,_,_=eh[0];ehraw=raw[ehfo:ehfo+ehsize]
assert struct.unpack_from('<II',ehraw)==(20,0) and ehraw[8:18]==b'\x01zRS\x00\x01\x78\x1e\x01\x10'
unwind=[];pos=24
while pos<len(ehraw):
    length,cie=struct.unpack_from('<II',ehraw,pos);assert length>=24 and cie==pos+4 and pos+length+4<=len(ehraw)
    pc=ehva+pos+8+struct.unpack_from('<q',ehraw,pos+8)[0];span=struct.unpack_from('<Q',ehraw,pos+16)[0]
    unwind.append((pc,pc+span));pos+=length+4
assert pos==len(ehraw) and len(unwind)==4
reports=[]
for name in ['_gpu_block_stop','_gpu_times','_space_faulted']:
    entry=symbols[name];lo=entry+8;hi=addresses[bisect.bisect_right(addresses,entry)]
    assert any(va<=entry<hi<=va+fs and prot==5 for va,fo,fs,prot,_ in segments)
    refs=[];page_refs=[];pointers=[]
    for va,fo,size,prot,segname in segments:
        if prot==5:
            for i in range(0,size-3,4):
                here=va+i
                if entry<=here<hi:continue
                w=struct.unpack_from('<I',raw,fo+i)[0];target=None
                if w&0x7c000000==0x14000000:target=here+signed(w&0x3ffffff,26)*4
                elif w&0xff000010==0x54000000 or w&0x7e000000==0x34000000:target=here+signed((w>>5)&0x7ffff,19)*4
                elif w&0x7e000000==0x36000000:target=here+signed((w>>5)&0x3fff,14)*4
                elif w&0x9f000000==0x10000000:target=here+signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)
                elif w&0x3b000000==0x18000000:target=here+signed((w>>5)&0x7ffff,19)*4
                if target is not None and entry<=target<hi:refs.append([hex(here),hex(target)])
                if w&0x9f000000!=0x90000000:continue
                page=(here&~4095)+(signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)<<12)
                if not (entry&~4095)<=page<((hi+4095)&~4095):continue
                reg=w&31
                for j in range(i+4,min(i+36,size-3),4):
                    c=struct.unpack_from('<I',raw,fo+j)[0];dest=None
                    if (c>>5)&31!=reg:continue
                    if c&0xff000000==0x91000000:dest=page+(((c>>10)&4095)<<(12 if c&(1<<22) else 0))
                    elif c&0x3b000000==0x39000000:dest=page+(((c>>10)&4095)<<(c>>30))
                    if dest is not None and entry<=dest<hi:page_refs.append([hex(va+j),hex(dest)])
        if segname!='__LINKEDIT':
            for i in range(0,size-7,4):
                here=va+i
                if entry<=here<hi:continue
                if entry<=struct.unpack_from('<Q',raw,fo+i)[0]<hi:pointers.append(hex(here))
    uw=[list(map(hex,(a,b))) for a,b in unwind if a<hi and entry<b]
    reports.append(dict(symbol=name,entry=hex(entry),start=hex(lo),end=hex(hi),bytes=hi-lo,
        original_entry_words=list(struct.unpack_from('<II',raw,off(entry))),
        file_offset=off(lo),body_sha256=hashlib.sha256(raw[off(lo):off(lo)+hi-lo]).hexdigest(),
        direct_references=refs,page_references=page_refs,loaded_pointers=pointers,unwind_references=uw,
        accepted=not(refs or page_refs or pointers or uw)))
out=root/'out/lmi-display-quiesce-space-v64';out.mkdir(exist_ok=True)
report=dict(result='READ_ONLY_AUDIT',base_sha256=sha(base),full_rx_segments_scanned=True,regions=reports,
    accepted_bytes=sum(r['bytes'] for r in reports if r['accepted']),hardware_tested=False,
    sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/'hackios/xnu/files/bsd/dev/redwood_adreno.c',root/'out/lmi-display-probe-v56f/kernel-symbols.txt']})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
