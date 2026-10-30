"""Independent ELF placement, hook decode and exact parent-code audit."""
from pathlib import Path
import hashlib,json,struct,subprocess
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN
ROOT=Path(__file__).resolve().parents[1];candidate=ROOT/'out/lmi-display-wait-v74'
out=ROOT/'out/lmi-display-wait-v74-link-review';assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
audit_path=candidate/'build-audit.json';audit=json.loads(audit_path.read_text())
host_path=ROOT/'out/lmi-display-wait-v74-host/result.json';host=json.loads(host_path.read_text())
assert host['result']=='PASS' and host['scenarios']==16 and len(host['mutations_caught'])==5
base=ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837'
before=base.read_bytes();raw=(candidate/'mach.development.bcm2837').read_bytes()
assert sha(base)==audit['base_sha256']=='68ec1820fea704e99ab1ccac5d70f19670faa9428378f75592f251ff5ede56c2'
assert hashlib.sha256(raw).hexdigest()==audit['sha256'] and len(raw)==len(before)
for report in [audit,host]:
    for name,digest in report['inputs'].items():assert sha(ROOT/name)==digest,name
def linux(p):return '/mnt/f/'+p.relative_to(Path('F:/')).as_posix()
def run(argv):return subprocess.check_output(['wsl','-d','Ubuntu-24.04','--',*argv],text=True,encoding='utf-8',errors='replace')
obj=out/'wait.o';linked=out/'wait.elf'
run(['clang',*audit['compile_flags'],'-c',linux(ROOT/'tools/lmi-display-wait-v74.c'),'-o',linux(obj)])
assert sha(obj)==sha(candidate/'wait.o')
run(['ld.lld','-T',linux(candidate/'wait.ld'),'--entry=lmi_wait_delay',linux(obj),
    *[f'--defsym={n}={v}' for n,v in audit['bindings'].items()],'-o',linux(linked)])
assert sha(linked)==sha(candidate/'wait.elf')
b=linked.read_bytes();at=struct.unpack_from('<Q',b,40)[0];size,count,ni=struct.unpack_from('<HHH',b,58)
hs=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*size) for i in range(count)]
names=b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
sections={names[h[0]:names.index(b'\0',h[0])].decode():h for h in hs if h[0] and h[2]&2 and h[5]}
assert set(sections)=={r['section'] for r in audit['sections']}
old_paths=[ROOT/'out/lmi-gpu-deferred-cache-v71/build-audit.json',ROOT/'out/lmi-display-timing-v73/build-audit.json']
old=[json.loads(p.read_text()) for p in old_paths]
space_path=ROOT/'out/lmi-gpu-frame-space-v67/result.json';space=json.loads(space_path.read_text())
def offset(pc,n=4):
    at=pc-0xfffffff007004000;assert 0<=at and at+n<=len(raw);return at
ranges=[]
for row in audit['sections']:
    h=sections[row['section']];pc=int(row['start'],16);n=row['bytes']
    assert h[1]==1 and not h[2]&1 and h[3]==pc and h[5]==n
    matches=[r for r in space['regions'] if r['accepted'] and int(r['start'],16)<=pc and pc+n<=int(r['end'],16)]
    assert len(matches)==1;r=matches[0];lo=int(r['start'],16);end=lo
    for prior in old:
        for s in prior['sections']:
            a=int(s['start'],16)
            if lo<=a<int(r['end'],16):end=max(end,a+s['bytes'])
    assert pc>=end and struct.unpack_from('<II',raw,offset(int(r['entry'],16)))==(0x52800000,0xd65f03c0)
    a=offset(pc,n);assert raw[a:a+n]==b[h[4]:h[4]+n];ranges.append([a,a+n])
assert not audit['new_entry_stubs']
for prior in old:
    for s in prior['sections']:
        a=offset(int(s['start'],16),s['bytes']);assert raw[a:a+s['bytes']]==before[a:a+s['bytes']]
decoder=Cs(CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN)
native=json.loads((ROOT/'out/lmi-display-timing-v73/runtime-symbols.json').read_text())
expected={0xfffffff007ae0100:('lmi_wait_delay',0xfffffff0072c9328),
    0xfffffff0074d30e4:('lmi_wait_allocate',native['lmi_timing_allocate']),
    0xfffffff0074d24a0:('lmi_wait_cleanup',native['lmi_timing_cleanup'])}
decoded=[]
assert len(audit['hooks'])==3
for hook in audit['hooks']:
    pc=int(hook['pc'],16);name,dest=expected[pc];assert name==hook['symbol']
    a=offset(pc);oldins=list(decoder.disasm(before[a:a+4],pc));ins=list(decoder.disasm(raw[a:a+4],pc))
    assert len(oldins)==len(ins)==1 and oldins[0].mnemonic==ins[0].mnemonic=='bl'
    assert int(oldins[0].op_str.removeprefix('#'),16)==dest
    assert int(ins[0].op_str.removeprefix('#'),16)==int(hook['target'],16)
    ranges.append([a,a+4]);decoded.append(dict(pc=hex(pc),before=oldins[0].op_str,after=ins[0].op_str))
# Every original poll/check/timeout/branch stays byte-exact; only the BL to
# delay changes. This includes the loop, stopping checks and submit wrapper.
start=offset(0xfffffff007ae00c0);end=offset(0xfffffff007ae0214)
restored=bytearray(raw)
for a,z in ranges:restored[a:z]=before[a:z]
assert restored==before and sorted(ranges)==sorted(audit['allowed_file_ranges'])
assert raw[offset(0xfffffff007ae00fc):offset(0xfffffff007ae0100)]==bytes.fromhex('40068052')
pollstart=offset(0xfffffff007ae0c90);pollend=offset(0xfffffff007ae0e30)
assert raw[pollstart:pollend]==before[pollstart:pollend]
# Audit the linked code as well as source: no interrupt mask, hidden lock,
# MMIO write or indirect call is introduced in the shim.
syms=json.loads((candidate/'runtime-symbols.json').read_text())
lo=syms['lmi_wait_delay'];hi=syms['lmi_wait_allocate'];a=offset(lo,hi-lo)
instructions=list(decoder.disasm(raw[a:a+hi-lo],lo))
assert not any(i.mnemonic in ['msr','blr','br','svc','hvc','smc'] for i in instructions)
calls={int(i.op_str.removeprefix('#'),16) for i in instructions if i.mnemonic in ['bl','b'] and i.op_str.startswith('#') and not lo<=int(i.op_str[1:],16)<hi}
assert calls=={native['lmi_frame_ticks'],0xfffffff0072c9328}
assert any(i.mnemonic=='cmp' and i.op_str=='x8, #0x3c0' for i in instructions)
assert any(i.mnemonic=='mov' and i.op_str=='w9, #0x6d40' for i in instructions)
assert any(i.mnemonic=='movk' and i.op_str=='w9, #2, lsl #16' for i in instructions)
assert audit['spin_step_ticks']==960 and audit['spin_budget_ticks']==160000
paths=[Path(__file__),audit_path,host_path,base,candidate/'wait.o',candidate/'wait.elf',candidate/'wait.ld',*old_paths,space_path]
report=dict(result='PASS',kernel_sha256=audit['sha256'],object_reproduced=True,link_reproduced=True,
    independent_instruction_decode=True,hooks_verified=True,free_tails_only=True,no_writable_globals=True,
    v73_timing_code_exact=True,original_gpu_code_exact=True,v72_touch_preserved=True,
    outside_edits_exact=True,dpu_poll_loop_and_timeout_exact=True,original_delay_bound=True,
    no_new_irq_masking_or_locks=True,spin_constants_decoded=True,hooks=decoded,
    hardware_tested=False,performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix():sha(p) for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS: reproduced v74 object/link; exact native DPU poll and all parent GPU/touch code')
