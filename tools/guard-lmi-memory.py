"""Audit lmi RAM ownership and protect three live firmware carveouts in Mu.

Run after staging, before building. This is a conservative software map, not
proof of safe bootloader relocation or runtime hardware behavior.
"""
from pathlib import Path
import json
import re
import struct
import sys

root = Path(__file__).resolve().parents[1]
mu = Path.home() / 'hackios-lmi/mu-silicium'
path = mu / 'Platforms/Xiaomi/lmiPkg/Library/MemoryMapLib/MemoryMapLib.c'
text = path.read_text()
regions = json.loads((root / 'device-info/memory-regions.json').read_text())['regions']
required = [('/reserved-memory/xbl_aop_region', 0x80600000, 0x260000),
            ('/reserved-memory/res_xbl_uefi_log_region', 0x80880000, 0x14000),
            ('/reserved-memory/disp_rdump_region@9c000000', 0xb0400000, 0x1000000)]
for name, base, size in required:
    assert any(r['path']==name and int(r['start'],16)==base and int(r['size'],16)==size for r in regions)
edits = []
for base, size, new_name in ((0x80600000,0x260000,'XBL AOP Reserved'),
                              (0x80880000,0x4000,'XBL Log Reserved')):
    pattern = re.compile(r'\{"RAM Partition",\s*0x0*'+f'{base:x}'+r',\s*0x0*'+f'{size:x}'+r',\s*AddMem,\s*SYS_MEM,\s*SYS_MEM_CAP,\s*Conv,\s*WRITE_BACK_XN\}',re.I)
    replacement = f'{{"{new_name}", 0x{base:08X}, 0x{size:08X}, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, WRITE_BACK_XN}}'
    text, count = pattern.subn(lambda _:replacement, text)
    assert count==1 or (count==0 and replacement in text),(hex(base),count)
    edits.append(dict(base=hex(base),size=hex(size),change='ConventionalMemory -> ReservedMemory'))
marker='\n};'
assert text.count(marker)==1
if '"Display Dump Reserved"' not in text:
    text=text.replace(marker, '\n  {"Display Dump Reserved", 0xB0400000, 0x01000000, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, WRITE_BACK_XN},\n};')
edits.append(dict(base='0xb0400000',size='0x1000000',change='Added fixed display-dump reservation'))
descriptors=[]
for m in re.finditer(r'\{"([^"]+)",\s*(0x[0-9a-f]+),\s*(0x[0-9a-f]+),\s*([^}]+)\}',text,re.I):
    fields=[s.strip() for s in m[4].split(',')]
    descriptors.append(dict(name=m[1],base=int(m[2],16),end=int(m[2],16)+int(m[3],16),memory_type=fields[3]))
conflicts=[]
for d in descriptors:
    if d['memory_type'] not in ('Conv','BsData','RtData'):
        continue
    for r in regions:
        if r['kind']=='reserved' and r['status']=='okay' and d['base']<int(r['end_exclusive'],16) and int(r['start'],16)<d['end']:
            conflicts.append(dict(descriptor=d['name'],dt_reservation=r['path']))
assert not conflicts,conflicts
# FDT header reservation entries are distinct from /reserved-memory nodes.
dtb=(root/'device-info/live.dtb').read_bytes()
pos=struct.unpack_from('>I',dtb,16)[0]
header_reserved=[]
while True:
    base,size=struct.unpack_from('>QQ',dtb,pos);pos+=16
    if base==size==0:break
    header_reserved.append(dict(base=hex(base),size=hex(size)))
iomem=(root/'device-info/bringup-current/iomem.txt').read_text()
candidate_checks={}
for name,base,size in [('uefi_fd',0x9fc00000,0x300000),('uefi_stack',0x9ff90000,0x40000),('upstream_payload',0xf0000000,0x4000000)]:
    overlaps=[]
    for line in iomem.splitlines():
        m=re.match(r'\s*([0-9a-f]+)-([0-9a-f]+) : (.*)',line)
        if m and m[3]!='System RAM' and base<=int(m[2],16) and int(m[1],16)<base+size:
            overlaps.append(line.strip())
    candidate_checks[name]=dict(base=hex(base),size=hex(size),android_iomem_overlaps=overlaps,
        hardware_boot_safe=False, used_by_current_diagnostic=(name!='upstream_payload'))
path.write_text(text)
report=dict(edits=edits,descriptors=len(descriptors),fixed_dt_allocatable_conflicts=conflicts,
    fdt_header_reservations=header_reserved,candidate_checks=candidate_checks,
    limitations=['Android memory ownership does not prove pre-OS firmware ownership',
        'This static audit does not establish the embedded loader command policy; consult its manifest'])
(root/'out/lmi-memory-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
