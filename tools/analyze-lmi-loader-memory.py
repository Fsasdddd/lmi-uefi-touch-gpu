"""Inspect the captured UEFI map and the unmodified upstream kernel artifact."""
from pathlib import Path
import hashlib
import json
import re
import struct

root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-loader-test'
log=(out/'loader-before-download.log').read_text()
text=log.rsplit('memory map (',1)[1]
regions=[]
for m in re.finditer(r'^\s+([0-9a-f]+) - ([0-9a-f]+)\s+type (\d+)\s+',text,re.M):
    lo,hi,kind=int(m[1],16),int(m[2],16),int(m[3])
    assert lo<hi and lo%4096==hi%4096==0
    regions.append(dict(start=lo,end=hi,type=kind))
assert regions
ordered=sorted(regions,key=lambda x:x['start'])
assert all(a['end']<=b['start'] for a,b in zip(ordered,ordered[1:]))
allocation=re.search(r'lmi payload allocation status=0 base=([0-9a-f]+) size=([0-9a-f]+)',log)
assert allocation
base,size=int(allocation[1],16),int(allocation[2],16)
assert size==0x4000000
assert any(r['type']==2 and r['start']<=base and base+size<=r['end'] for r in regions)
free=[r for r in regions if r['type']==7]
largest=max(free,key=lambda r:r['end']-r['start'])
candidate_base=(largest['start']+0x1ffffff)&~0x1ffffff
candidate_size=min((largest['end']&~0x1ffffff)-candidate_base,0x180000000)
assert candidate_size>0 and not (candidate_base<base+size and base<candidate_base+candidate_size)
kernel=root/'hackios/prebuilt/mach.development.bcm2837'
b=kernel.read_bytes()
magic,cpu,subcpu,filetype,ncmds,cmdbytes,flags,reserved=struct.unpack_from('<8I',b)
assert magic==0xfeedfacf and cpu==0x100000c and filetype==2
pos=32;segments=[];entry=0
for _ in range(ncmds):
    cmd,cmdsize=struct.unpack_from('<II',b,pos)
    assert cmdsize>=8 and pos+cmdsize<=32+cmdbytes
    if cmd==0x19:
        name,va,vs,fo,fs=struct.unpack_from('<16s4Q',b,pos+8)
        assert fs<=vs and fo+fs<=len(b)
        if vs:segments.append(dict(name=name.rstrip(b'\0').decode(),va=va,size=vs,file_offset=fo,file_size=fs))
    elif cmd==5:
        entry=struct.unpack_from('<Q',b,pos+16+32*8)[0]
    pos+=cmdsize
assert pos==32+cmdbytes
assert any(s['va']<=entry<s['va']+s['size'] for s in segments)
assert b.count(b'XNULDRST')==1
report=dict(uefi_descriptors=len(regions),uefi_map_overlaps=False,
    payload=dict(base=hex(base),size=hex(size),uefi_memory_type=2,allocation_verified=True),
    largest_free_region=dict(start=hex(largest['start']),end=hex(largest['end']),bytes=largest['end']-largest['start']),
    kernel_window_candidate=dict(base=hex(candidate_base),size=hex(candidate_size),actual_allocation_tested=False),
    upstream_kernel=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),macho_arm64=True,
        entry_va=hex(entry),segments_valid=True,return_slot_count=1,hardware_started=False),
    limits=['Candidate kernel window is not yet allocated or tested',
        'Kernel drivers remain largely redwood-specific; earliest checkpoints must precede device bring-up'])
(out/'memory-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
