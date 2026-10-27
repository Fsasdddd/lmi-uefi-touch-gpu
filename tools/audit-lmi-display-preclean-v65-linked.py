"""Reproduce the real arm64 object/link and check every final placed byte."""
from pathlib import Path
import hashlib,json,runpy,struct,subprocess
root=Path(__file__).resolve().parents[1];candidate=root/'out/lmi-display-preclean-v65b'
out=root/'out/lmi-display-preclean-v65-link-review';out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
audit=json.loads((candidate/'build-audit.json').read_text())
for n,d in audit['sources'].items():assert sha(root/'tools'/n)==d
for n,d in audit['inputs'].items():assert sha(root/n)==d
obj=out/'preclean.o'
subprocess.run(['clang',*audit['compile_flags'],'-c',str(root/'tools/lmi-display-preclean-v65.c'),'-o',str(obj)],check=True)
assert sha(obj)==sha(candidate/'preclean.o')
linked=out/'preclean.elf'
subprocess.run(['ld.lld','-T',str(candidate/'preclean.ld'),'--entry=lmi_preclean_frame',str(obj),
    *[f'--defsym={n}={v}' for n,v in audit['bindings'].items()],'-o',str(linked)],check=True)
assert sha(linked)==sha(candidate/'preclean.elf')
b=linked.read_bytes();offset=struct.unpack_from('<Q',b,40)[0];size,count,ni=struct.unpack_from('<HHH',b,58)
hs=[struct.unpack_from('<IIQQQQIIQQ',b,offset+i*size) for i in range(count)]
strings=b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
sections={strings[h[0]:strings.index(b'\0',h[0])].decode():h for h in hs if h[0] and h[2]&2 and h[5]}
raw=(candidate/'mach.development.bcm2837').read_bytes()
base=(root/'out/lmi-gpu-queue-v64b/mach.development.bcm2837').read_bytes()
assert hashlib.sha256(raw).hexdigest()==audit['sha256']
segs=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))['segments'](raw)
def off(pc,n=4):
    found=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(found)==1;return found[0]
for row in audit['sections']:
    pc=int(row['start'],16);h=sections[row['section']]
    assert h[3]==pc and h[5]==row['bytes']<=row['capacity']
    assert raw[off(pc,h[5]):off(pc)+h[5]]==b[h[4]:h[4]+h[5]]
    tails=[t for t in audit['tail_audits'] if t['start']<=pc and pc+h[5]<=t['start']+t['capacity']]
    assert len(tails)==1 and tails[0]['accepted']
    assert not any(tails[0][n] for n in ['direct_references','page_references','loaded_pointers','unwind_references'])
for row in audit['hooks']:
    pc=int(row['pc'],16);w=struct.unpack_from('<I',raw,off(pc))[0]
    assert w&0xfc000000==0x94000000
    displacement=w&0x3ffffff;displacement-=1<<26 if displacement&(1<<25) else 0
    assert pc+4*displacement==int(row['target'],16)
restored=bytearray(raw)
for a,z in audit['allowed_file_ranges']:restored[a:z]=base[a:z]
assert restored==base and len(raw)==len(base)
# The allocator hook remains specific to journal(280,16), with the old prefix
# zeroed by the original native code. No other source-drop/draw/wait BL changes.
pc=0xfffffff0074d30e4
assert raw[off(pc-8):off(pc)]==struct.pack('<II',0x52802300,0x52800201)
assert raw[off(pc+8):off(pc+12)]==struct.pack('<I',0x52802301)
undefined=subprocess.check_output(['llvm-nm','-u',str(linked)],text=True);assert not undefined.strip()
report=dict(result='PASS',kernel_sha256=audit['sha256'],object_reproduced=True,link_reproduced=True,
    placed_sections_verified=True,hooks_verified=True,outside_edits_exact=True,full_rx_tail_audit=True,
    journal_prefix_preserved=True,hardware_tested=False,performance_verified=False,
    inputs={str(p.relative_to(root)):sha(p) for p in [Path(__file__),candidate/'build-audit.json',candidate/'preclean.ld']},
    object_sha256=sha(obj),linked_elf_sha256=sha(linked))
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: v65 real object/link, final bytes, three hooks and journal allocation reproduced')
