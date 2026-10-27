"""Recompile/relink effective v64 objects, then compare placed bytes and hooks."""
from pathlib import Path
import hashlib,json,runpy,struct,subprocess
root=Path(__file__).resolve().parents[1]
candidate=root/'out/lmi-gpu-queue-v64b';out=root/'out/lmi-gpu-queue-v64-link-review';out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
audit=json.loads((candidate/'build-audit.json').read_text())
for n,d in audit['sources'].items():assert sha(root/'tools'/n)==d
for n,d in audit['inputs'].items():assert sha(root/n)==d
objects=[]
for n,d in audit['effective_object_inputs'].items():
    assert sha(root/n)==d;objects.append(root/n)
obj=out/'gpu-desktop.o'
compile_command=['clang',*audit['compile_flags'],'-c',str(root/'tools/lmi-gpu-desktop-v64.c'),'-o',str(obj)]
subprocess.run(compile_command,check=True);assert sha(obj)==sha(candidate/'gpu-desktop.o')
helpers=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))
bindings=helpers['elf_absolutes']((root/'out/lmi-gpu-map-v63c/batch.elf').read_bytes())
abi=runpy.run_path(str(root/'tools/lmi-gpu-desktop-profile.py'))['ABI']
effective=[obj if p==candidate/'gpu-desktop.o' else p for p in objects]
linked=out/'queue.elf'
link_command=['ld.lld','-T',str(candidate/'queue.ld'),'--entry=lmi_touch_thread','--gc-sections',
    '--undefined=lmi_gpu_probe','--undefined=lmi_gpu_async_return',
    *['--undefined=lmi_desktop_'+n for n in sorted({v[2] for v in abi.values()})],
    *[f'--defsym={n}={a:#x}' for n,a in bindings.items()],*[str(p) for p in effective],'-o',str(linked)]
subprocess.run(link_command,check=True);assert sha(linked)==sha(candidate/'queue.elf')
# Parse allocated ELF sections independently of the builder.
b=linked.read_bytes();eoff=struct.unpack_from('<Q',b,40)[0]
esize,count,ni=struct.unpack_from('<HHH',b,58)
headers=[struct.unpack_from('<IIQQQQIIQQ',b,eoff+i*esize) for i in range(count)]
strings=b[headers[ni][4]:headers[ni][4]+headers[ni][5]]
sections={strings[h[0]:strings.index(b'\0',h[0])].decode():h for h in headers if h[0] and h[2]&2 and h[5]}
raw=(candidate/'mach.development.bcm2837').read_bytes()
base=(root/'out/lmi-gpu-map-v63c/mach.development.bcm2837').read_bytes()
assert hashlib.sha256(raw).hexdigest()==audit['sha256']
segs=helpers['segments'](raw)
def off(pc,n):
    hits=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(hits)==1;return hits[0]
for row in audit['sections']:
    h=sections[row['section']];pc=int(row['start'],16);n=row['bytes']
    assert h[3]==pc and h[5]==n<=row['capacity']
    assert raw[off(pc,n):off(pc,n)+n]==b[h[4]:h[4]+n]
    assert off(pc,n)+n<=len(raw)
for h in audit['hooks']:
    pc=int(h['pc'],16);w=struct.unpack_from('<I',raw,off(pc,4))[0]
    assert w&0xfc000000==(0x94000000 if h['symbol']=='lmi_gpu_async_return' else 0x14000000)
    imm=w&0x3ffffff;imm-=0x4000000 if imm&0x2000000 else 0
    assert pc+imm*4==int(h['target'],16)
for pc in [0xfffffff0074d22f0,0xfffffff0074d3330]:
    assert struct.unpack_from('<II',raw,off(pc,8))==(0x52800000,0xd65f03c0)
restored=bytearray(raw)
for a,z in audit['allowed_file_ranges']:restored[a:z]=base[a:z]
assert restored==base and len(raw)==len(base)
# Machine instruction for the NULL/zero path's full-system publication barrier.
h=sections['.gpu_handoff'];code=b[h[4]:h[4]+h[5]]
assert code.count(struct.pack('<I',0xd5033f9f))==1
report=dict(result='PASS',kernel_sha256=audit['sha256'],replacement_object_reproduced=True,
    actual_link_reproduced=True,placed_sections_verified=True,hooks_verified=True,
    outside_edits_exact=True,obsolete_entries_disabled=True,dsb_sy_present=True,
    hardware_tested=False,performance_verified=False,
    effective_object_inputs={str(p.relative_to(root)):sha(p) for p in effective},
    compile_command=compile_command,link_command=link_command,
    inputs={str(p.relative_to(root)):sha(p) for p in [Path(__file__),candidate/'build-audit.json',candidate/'queue.ld']},
    linked_elf_sha256=sha(linked),replacement_object_sha256=sha(obj))
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: v64 effective objects and ELF reproduced; all placed sections/hooks/barrier/stubs verified')
