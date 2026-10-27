"""Reproduce the real object/link and independently check final kernel hooks."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v70');args=p.parse_args()
root=Path(__file__).resolve().parents[1];candidate=root/('out/lmi-gpu-overlap-'+args.attempt)
out=root/('out/lmi-gpu-overlap-'+args.attempt+'-link-review');assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
audit=json.loads((candidate/'build-audit.json').read_text())
for n,d in audit['sources'].items():assert sha(root/'tools'/n)==d,n
for n,d in audit['inputs'].items():assert sha(root/n)==d,n
obj=out/'frame.o';subprocess.run(['clang',*audit['compile_flags'],'-c',str(root/'tools/lmi-gpu-overlap-v70.c'),'-o',str(obj)],check=True)
assert sha(obj)==sha(candidate/'frame.o')
linked=out/'frame.elf';subprocess.run(['ld.lld','-T',str(candidate/'frame.ld'),'--entry=lmi_gpu_frame_frame',str(obj),
    *[f'--defsym={n}={v}' for n,v in audit['bindings'].items()],'-o',str(linked)],check=True)
assert sha(linked)==sha(candidate/'frame.elf')
b=linked.read_bytes();at=struct.unpack_from('<Q',b,40)[0];size,count,ni=struct.unpack_from('<HHH',b,58)
hs=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*size) for i in range(count)]
strings=b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
sections={strings[h[0]:strings.index(b'\0',h[0])].decode():h for h in hs if h[0] and h[2]&2 and h[5]}
assert all(not h[2]&1 for h in sections.values())
raw=(candidate/'mach.development.bcm2837').read_bytes();base=(root/'out/lmi-gpu-copy-v66c/mach.development.bcm2837').read_bytes()
assert hashlib.sha256(raw).hexdigest()==audit['sha256']
segs=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))['segments'](raw)
def off(pc,n=4):
    hits=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(hits)==1;return hits[0]
def target(w,pc):
    assert w&0xfc000000==0x94000000
    n=w&0x3ffffff;return pc+4*(n-(1<<26) if n&(1<<25) else n)
space=json.loads((root/'out/lmi-gpu-frame-space-v67/result.json').read_text())
for row in audit['sections']:
    pc=int(row['start'],16);h=sections[row['section']]
    assert h[3]==pc and h[5]==row['bytes']<=row['capacity']
    assert raw[off(pc,h[5]):off(pc)+h[5]]==b[h[4]:h[4]+h[5]]
    r,=[r for r in space['regions'] if r['start']==row['start'] and r['accepted']]
    assert r['loaded_pointer_targets_entry_only'] and not any(r[n] for n in ['direct_references','page_references','unwind_references'])
    assert raw[off(pc-8,8):off(pc)]==struct.pack('<II',0x52800000,0xd65f03c0)
    for ptr in r['loaded_pointers']:
        q=int(ptr,16);assert raw[off(q,8):off(q)+8]==base[off(q):off(q)+8]
syms=json.loads((candidate/'runtime-symbols.json').read_text())
assert len(audit['hooks'])==5
for r in audit['hooks']:
    pc=int(r['pc'],16)
    assert target(struct.unpack_from('<I',raw,off(pc))[0],pc)==syms[r['symbol']]==int(r['target'],16)
    assert target(struct.unpack_from('<I',base,off(pc))[0],pc)==int(r['original'],16)
# The source-layout kernel's lock is different from the old prebuilt BSS.
assert int(audit['bindings']['lmi_frame_gpu_lock'],16)==0xfffffff007f269e8
gpu=json.loads((root/'out/lmi-gpu-queue-v64b/runtime-symbols.json').read_text())
assert int(audit['bindings']['lmi_frame_done'],16)==gpu['lmi_desktop_done']
assert int(audit['bindings']['lmi_frame_pause'],16)==gpu['delay']
assert 'lmi_frame_drain' not in audit['bindings']
calls=[target(struct.unpack_from('<I',raw,off(pc))[0],pc)
       for row in audit['sections'] for pc in range(int(row['start'],16),int(row['start'],16)+row['bytes']-3,4)
       if struct.unpack_from('<I',raw,off(pc))[0]&0xfc000000==0x94000000]
assert gpu['lmi_desktop_done'] in calls and gpu['delay'] in calls
assert gpu['drain'] not in calls
# Frozen service gate, real GPU backend, DPU state machine and touch bytes are
# preserved by reconstructing the entire original image outside allowed edits.
restored=bytearray(raw)
for a,z in audit['allowed_file_ranges']:
    assert 0<=a<z<=len(raw);restored[a:z]=base[a:z]
assert restored==base and len(raw)==len(base)
assert not subprocess.check_output(['llvm-nm','-u',str(linked)],text=True).strip()
text=subprocess.check_output(['llvm-objdump','-d',str(linked)],text=True)
assert not re.search(r'\bx18\b',text)
assert 'dc\t' not in text # Calls use the existing, audited PoC helper.
(out/'disassembly.txt').write_text(text)
report=dict(result='PASS',kernel_sha256=audit['sha256'],object_reproduced=True,link_reproduced=True,
    placed_sections_verified=True,hooks_verified=True,outside_edits_exact=True,full_rx_space_audit=True,
    obsolete_entries_disabled=True,loaded_entry_pointers_preserved=True,no_writable_globals=True,
    correct_native_gpu_lock=True,real_copy_fence_binding=True,unlocked_delay_binding=True,no_direct_queue_drain=True,frozen_backend_and_dpu_preserved=True,hardware_tested=False,performance_verified=False,
    inputs={str(q.relative_to(root)):sha(q) for q in [Path(__file__),candidate/'build-audit.json',candidate/'frame.ld']},
    object_sha256=sha(obj),linked_elf_sha256=sha(linked))
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: actual v70 object/link, five final hooks, native lock, obsolete entry guards and untouched baseline bytes')
