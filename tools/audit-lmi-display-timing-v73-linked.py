"""Reproduce object/link; independently decode hooks and the native wait ABI."""
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
import argparse,hashlib,json,re,runpy,struct,subprocess
ROOT=Path(__file__).resolve().parents[1]
candidate=ROOT/'out/lmi-display-timing-v73'
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v73b');args=p.parse_args()
assert re.fullmatch(r'v73[a-z]?',args.attempt)
out=ROOT/('out/lmi-display-timing-'+args.attempt+'-link-review')
assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
audit=json.loads((candidate/'build-audit.json').read_text())
base=ROOT/'out/lmi-touch-cadence-v72b/mach.development.bcm2837'
raw=(candidate/'mach.development.bcm2837').read_bytes();before=base.read_bytes()
assert sha(base)==audit['base_sha256']=='1e76f68263c0e9c02d47fd2528f7f589087726f1d59fb96154e9b5c928077a8b'
assert hashlib.sha256(raw).hexdigest()==audit['sha256'] and len(raw)==len(before)
for name,digest in audit['inputs'].items():assert sha(ROOT/name)==digest,name
host_path=ROOT/'out/lmi-display-timing-v73b-host/result.json'
host=json.loads(host_path.read_text());assert host['result']=='PASS' and host['scenarios']==16 and len(host['mutations_caught'])==6
for name,digest in host['inputs'].items():assert sha(ROOT/name)==digest,name
def linux(p):
    assert p.drive.lower()=='f:'
    return '/mnt/f/'+p.relative_to(Path('F:/')).as_posix()
def run(argv):
    return subprocess.check_output(['wsl','-d','Ubuntu-24.04','--',*argv],text=True,encoding='utf-8',errors='replace')
obj=out/'timing.o'
run(['clang',*audit['compile_flags'],'-c',linux(ROOT/'tools/lmi-display-timing-v73.c'),'-o',linux(obj)])
assert sha(obj)==sha(candidate/'timing.o')
linked=out/'timing.elf'
run(['ld.lld','-T',linux(candidate/'timing.ld'),'--entry=lmi_timing_frame',linux(obj),
     *[f'--defsym={n}={v}' for n,v in audit['bindings'].items()],'-o',linux(linked)])
assert sha(linked)==sha(candidate/'timing.elf')
# Independently read loaded ELF sections; no writable or orphaned allocation.
b=linked.read_bytes();at=struct.unpack_from('<Q',b,40)[0];size,count,ni=struct.unpack_from('<HHH',b,58)
hs=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*size) for i in range(count)]
names=b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
sections={names[h[0]:names.index(b'\0',h[0])].decode():h for h in hs if h[0] and h[2]&2 and h[5]}
assert set(sections)=={s['section'] for s in audit['sections']}
segs=runpy.run_path(str(ROOT/'tools/build-lmi-source-runtime.py'))['segments'](before)
def off(pc,n=4):
    hits=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(hits)==1
    return hits[0]
old=json.loads((ROOT/'out/lmi-gpu-deferred-cache-v71/build-audit.json').read_text())
space=json.loads((ROOT/'out/lmi-gpu-frame-space-v67/result.json').read_text())
free=[];stub_entries=set();ranges=[]
used={int(s['start'],16):s['bytes'] for s in old['sections']}
for r in space['regions']:
    if r['accepted']:
        lo,hi=int(r['start'],16),int(r['end'],16)
        free.append((lo+used.get(lo,0),hi,lo-8,used.get(lo,0)))
for row in audit['sections']:
    h=sections[row['section']];pc=int(row['start'],16);n=row['bytes']
    assert h[1]==1 and not h[2]&1 and h[3]==pc and h[5]==n
    match=[v for v in free if v[0]<=pc and pc+n<=v[1]];assert len(match)==1
    _,_,entry,old_n=match[0];assert int(row['entry'],16)==entry and row['prior_bytes']==old_n
    a=off(pc,n);assert raw[a:a+n]==b[h[4]:h[4]+n];ranges.append([a,a+n])
    assert struct.unpack_from('<II',raw,off(entry))==(0x52800000,0xd65f03c0)
    if not old_n:
        stub_entries.add(hex(entry));ranges.append([off(entry),off(entry)+8])
assert stub_entries==set(audit['new_entry_stubs'])
for row in old['sections']:
    a=off(int(row['start'],16),row['bytes'])
    assert raw[a:a+row['bytes']]==before[a:a+row['bytes']]
assert {r['symbol'] for r in audit['hooks']}=={'lmi_timing_frame','lmi_timing_allocate',
    'lmi_timing_cleanup','lmi_timing_submit','lmi_timing_source'} and len(audit['hooks'])==5
expected={0xfffffff007ae00bc:('lmi_timing_frame',0xfffffff0074d8b98),
          0xfffffff0074d30e4:('lmi_timing_allocate',0xfffffff0074d95c8),
          0xfffffff0074d24a0:('lmi_timing_cleanup',0xfffffff0074d94fc),
          0xfffffff007ae020c:('lmi_timing_submit',0xfffffff007ae0b74),
          0xfffffff007ae0420:('lmi_timing_source',None)}
decoder=Cs(CS_ARCH_ARM64,CS_MODE_ARM);decoded=[]
for hook in audit['hooks']:
    pc=int(hook['pc'],16);name,dest=expected[pc];assert name==hook['symbol']
    a=off(pc);original=list(decoder.disasm(before[a:a+4],pc));patched=list(decoder.disasm(raw[a:a+4],pc))
    assert len(original)==len(patched)==1 and patched[0].mnemonic=='bl'
    assert int(patched[0].op_str.removeprefix('#'),16)==int(hook['target'],16)
    if dest is None:assert original[0].mnemonic=='blr' and original[0].op_str=='x8'
    else:assert original[0].mnemonic=='bl' and int(original[0].op_str.removeprefix('#'),16)==dest
    decoded.append(dict(pc=hex(pc),before=original[0].mnemonic+' '+original[0].op_str,
                        after=patched[0].mnemonic+' '+patched[0].op_str))
    ranges.append([a,a+4])
# Full native source-ready function proves the exact surface + uint64 500ms ABI.
pc=0xfffffff007ae0408;a=off(pc,36)
native=list(decoder.disasm(before[a:a+36],pc))
assert [i.mnemonic for i in native]==['stp','mov','mov','movk','movk','mov','blr','ldp','ret']
assert native[1].op_str=='x0, x1' and native[2].op_str=='x8, #-0xa690'
assert native[3].op_str=='x8, #0x79e, lsl #16' and native[4].op_str=='x8, #0xfff0, lsl #32'
assert native[5].op_str=='w1, #0x1f4'
assert audit['bindings']['lmi_timing_original_source']=='0xfffffff0079e5970'
assert audit['bindings']['lmi_timing_original_submit']=='0xfffffff007ae0b74'
assert sorted(ranges)==sorted(audit['allowed_file_ranges'])
restored=bytearray(raw)
for a,z in ranges:restored[a:z]=before[a:z]
assert restored==before
# Disassembly also proves that wrappers call each required frozen implementation.
disassembly=run(['llvm-objdump','-d',linux(linked)])
(out/'disassembly.txt').write_text(disassembly)
assert not re.search(r'\bx18\b',disassembly)
calls=set()
for h in sections.values():
    for delta in range(0,h[5]-3,4):
        pc=h[3]+delta;word=struct.unpack_from('<I',b,h[4]+delta)[0]
        if word&0x7c000000==0x14000000:
            immediate=word&0x3ffffff
            calls.add(pc+4*(immediate-(1<<26) if immediate&(1<<25) else immediate))
for name in ['lmi_gpu_frame_frame','lmi_gpu_frame_cleanup','lmi_timing_original_source','lmi_timing_original_submit']:
    assert int(audit['bindings'][name],16) in calls,name
report=dict(result='PASS',kernel_sha256=audit['sha256'],object_reproduced=True,link_reproduced=True,
    independent_instruction_decode=True,hooks_verified=True,placed_sections_verified=True,
    free_tails_only=True,no_writable_globals=True,original_gpu_code_exact=True,
    outside_edits_exact=True,v72_touch_preserved=True,native_ready_abi_verified=True,
    original_source_implementation_bound=True,original_dpu_submit_bound=True,
    hot_path_logging=False,hardware_tested=False,performance_verified=False,decoded_hooks=decoded,
    inputs={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),candidate/'build-audit.json',
        candidate/'timing.o',candidate/'timing.elf',candidate/'timing.ld',base,host_path]})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: reproduced object/link; five Capstone-decoded hooks, native wait ABI, free tails and exact v72 touch/GPU preservation')
