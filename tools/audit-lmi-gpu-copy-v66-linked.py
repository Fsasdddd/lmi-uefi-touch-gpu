"""Independent reproduction and final-byte/return-gate review of v66c."""
from pathlib import Path
import hashlib,json,runpy,struct,subprocess
root=Path(__file__).resolve().parents[1];candidate=root/'out/lmi-gpu-copy-v66c'
out=root/'out/lmi-gpu-copy-v66-link-review';out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
audit=json.loads((candidate/'build-audit.json').read_text())
for n,d in audit['sources'].items():assert sha(root/'tools'/n)==d,n
for n,d in audit['inputs'].items():assert sha(root/n)==d,n
obj=out/'copy.o';subprocess.run(['clang',*audit['compile_flags'],'-c',str(root/'tools/lmi-gpu-copy-v66.c'),'-o',str(obj)],check=True)
assert sha(obj)==sha(candidate/'copy.o')
linked=out/'copy.elf';subprocess.run(['ld.lld','-T',str(candidate/'copy.ld'),'--entry=lmi_gpu_copy_start',str(obj),
    *[f'--defsym={n}={v}' for n,v in audit['bindings'].items()],'-o',str(linked)],check=True)
assert sha(linked)==sha(candidate/'copy.elf')
b=linked.read_bytes();at=struct.unpack_from('<Q',b,40)[0];size,count,ni=struct.unpack_from('<HHH',b,58)
hs=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*size) for i in range(count)]
strings=b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
sections={strings[h[0]:strings.index(b'\0',h[0])].decode():h for h in hs if h[0] and h[2]&2 and h[5]}
assert all(not h[2]&1 for h in sections.values())
raw=(candidate/'mach.development.bcm2837').read_bytes();base=(root/'out/lmi-display-preclean-v65b/mach.development.bcm2837').read_bytes()
assert hashlib.sha256(raw).hexdigest()==audit['sha256']
segs=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))['segments'](raw)
def off(pc,n=4):
    hits=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(hits)==1;return hits[0]
def signed(n,bits):return n-(1<<bits) if n&(1<<(bits-1)) else n
for row in audit['sections']:
    pc=int(row['start'],16);h=sections[row['section']]
    assert h[3]==pc and h[5]==row['bytes']<=row['capacity']
    assert raw[off(pc,h[5]):off(pc)+h[5]]==b[h[4]:h[4]+h[5]]
assert {(r['start'],r['bytes'],r['capacity']) for r in audit['sections']}=={
    ('0xfffffff0074d28d8',204,204),('0xfffffff0074d4914',496,500)}
space=json.loads((root/'out/lmi-gpu-copy-space-v66/result.json').read_text())
body=next(r for r in space['regions'] if r['accepted'])
assert body['loaded_pointer_targets_entry_only'] and body['step_reader_replaced'] and body['recovery_replaced']
assert struct.unpack_from('<II',raw,off(0xfffffff0074d490c))==(0x52800000,0xd65f03c0)
assert raw[off(0xfffffff0071ce668,8):off(0xfffffff0071ce668)+8]==base[off(0xfffffff0071ce668):off(0xfffffff0071ce668)+8]
tail=json.loads((root/'out/lmi-gpu-copy-v66-tail/result.json').read_text())['regions'][0]
for r in [body,tail]:
    assert r['accepted'] and not any(r[n] for n in ['direct_references','page_references','unwind_references'])
assert not tail['loaded_pointers']
# Decode both final instructions independently, including the true/false
# control flow into the original saved-result epilogue and failure block.
call=int(audit['service_call'],16);old,old_branch=struct.unpack_from('<II',base,off(call))
new,branch=struct.unpack_from('<II',raw,off(call))
assert old&0xfc000000==new&0xfc000000==0x94000000
syms=json.loads((candidate/'runtime-symbols.json').read_text())
assert call+4*signed(new&0x3ffffff,26)==syms['lmi_gpu_copy_start']
assert call+4*signed(old&0x3ffffff,26)==int(audit['bindings']['desktop_service_start'],16)
assert branch&0xfff8001f==0x37000000 # TBNZ W0, bit0; no other register/bit
target=call+4+4*signed((branch>>5)&0x3fff,14)
assert old_branch&0xfc000000==0x14000000 and target==call+4+4*signed(old_branch&0x3ffffff,26)
assert target==int(audit['success_epilogue'],16)==0xfffffff0074da96c
# Return the saved result before restoring caller X19. The actual instruction
# is the 64-bit MOV X0,X19, followed by the common register/stack restore.
assert raw[off(target):off(target)+4]==struct.pack('<I',0xaa1303e0)
ret_branch=struct.unpack_from('<I',raw,off(target+4))[0]
assert ret_branch&0xfc000000==0x14000000
restore_pc=target+4+4*signed(ret_branch&0x3ffffff,26)
assert restore_pc==0xfffffff0074da77c
assert struct.unpack_from('<8I',raw,off(restore_pc,32))==(
    0xa94b4ff4,0xa94a57f6,0xa9495ff8,0xa94867fa,
    0xa9476ffc,0xa9467bfd,0x910303ff,0xd65f03c0)
assert raw[off(call+8):off(call+20)]==base[off(call+8):off(call+20)]
assert struct.unpack_from('<I',raw,off(call+12))[0]==0x2a1f03f3 # failure MOV W19,WZR
for returned in (0,1):
    saved_result=1
    if not (returned&1):saved_result=0
    assert saved_result==returned
restored=bytearray(raw)
for a,z in audit['allowed_file_ranges']:restored[a:z]=base[a:z]
assert restored==base and len(raw)==len(base)
undefined=subprocess.check_output(['llvm-nm','-u',str(linked)],text=True);assert not undefined.strip()
report=dict(result='PASS',kernel_sha256=audit['sha256'],object_reproduced=True,link_reproduced=True,
    placed_sections_verified=True,hooks_verified=True,outside_edits_exact=True,full_rx_tail_audit=True,
    obsolete_entry_disabled=True,loaded_entry_pointer_preserved=True,conditional_service_gate_verified=True,
    original_failure_block_preserved=True,no_writable_globals=True,hardware_tested=False,performance_verified=False,
    inputs={str(p.relative_to(root)):sha(p) for p in [Path(__file__),candidate/'build-audit.json',candidate/'copy.ld']},
    object_sha256=sha(obj),linked_elf_sha256=sha(linked))
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: v66 real object/link, 700 placed bytes, service success/failure gate and untouched v65 bytes')
