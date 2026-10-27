"""Build a boot-only GPU copy qualification probe on the exact v65b image."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v66');args=p.parse_args()
assert re.fullmatch(r'v66[a-z]?',args.attempt)
root=Path(__file__).resolve().parents[1];out=root/('out/lmi-gpu-copy-'+args.attempt)
assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
prior=root/'out/lmi-display-preclean-v65b';base=prior/'mach.development.bcm2837';raw=base.read_bytes()
assert sha(base)=='0c61da0dda94a0280495d96af94c85edb8b28dea8f068e26b34f96fa885f44e6'
helpers=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'));segs=helpers['segments'](raw)
def off(pc,n=4):
    hits=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(hits)==1;return hits[0]
def dest(w,pc):
    assert w&0x7c000000==0x14000000
    n=w&0x3ffffff;return pc+4*(n-(1<<26) if n&(1<<25) else n)
def elf(path):
    b=path.read_bytes();assert b[:6]==b'\x7fELF\x02\x01'
    at=struct.unpack_from('<Q',b,40)[0];size,count,ni=struct.unpack_from('<HHH',b,58)
    hs=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*size) for i in range(count)]
    strings=b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
    return {strings[h[0]:strings.index(b'\0',h[0])].decode():(h,b[h[4]:h[4]+h[5]]) for h in hs if h[0] and h[2]&2 and h[5]}
spaces=[root/'out/lmi-gpu-copy-space-v66/result.json',root/'out/lmi-gpu-copy-v66-tail/result.json']
slots=[]
for path in spaces:
    report=json.loads(path.read_text());assert report['base_sha256']==sha(base) and report['full_rx_segments_scanned']
    for name,digest in report['sources'].items():assert sha(root/name)==digest,name
    r,=[r for r in report['regions'] if r['accepted']]
    lo,hi=int(r['start'],16),int(r['end'],16)
    assert not any(r[k] for k in ['direct_references','page_references','unwind_references'])
    assert hashlib.sha256(raw[off(lo):off(lo)+hi-lo]).hexdigest()==r['body_sha256']
    if r['symbol']=='_step_core_commands':
        assert r['loaded_pointers']==['0xfffffff0071ce668'] and r['step_reader_replaced'] and r['recovery_replaced']
        assert r['entry_stub_required']==[0x52800000,0xd65f03c0]
    else:assert not r['loaded_pointers']
    slots.append(dict(start=lo,capacity=hi-lo,used=0,inputs=[],audit=str(path.relative_to(root))))
assert [(s['start'],s['capacity']) for s in slots]==[(0xfffffff0074d4914,500),(0xfffffff0074d28d8,204)]
host_path=root/'out/lmi-gpu-copy-v66-host/result.json';host=json.loads(host_path.read_text())
assert host['result']=='PASS' and host['scenarios']==25 and host['asan_ubsan'] and len(host['mutations_caught'])==8
assert host['actual_v64_backend'] and host['independent_packet_decode'] and host['post_probe_jobs']==80
for name,digest in host['sources'].items():assert sha(root/'tools'/name)==digest,name
pm4=root/'out/lmi-gpu-research/rsc-register-source/mesa-24.3.0-adreno_pm4.xml'
assert sha(pm4)=='3d96f39a6beef90e74325c827e41e0e165ee3eaf9737f94fcbdb75a2e4011f1c'
flags=['--target=aarch64-none-elf','-Oz','-mllvm','-enable-machine-outliner=always','-ffunction-sections',
       '-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-Wall','-Wextra','-Werror']
obj=out/'copy.o';subprocess.run(['clang',*flags,'-c',str(root/'tools/lmi-gpu-copy-v66.c'),'-o',str(obj)],check=True)
for name,(h,data) in sorted(elf(obj).items(),key=lambda row:-len(row[1][1])):
    assert h[1]==1 and not h[2]&1 and name.startswith(('.text.','.rodata.'))
    fit=[(s['capacity']-((s['used']+h[8]-1)&-h[8])-len(data),i) for i,s in enumerate(slots)
         if ((s['used']+h[8]-1)&-h[8])+len(data)<=s['capacity']]
    assert fit,('Code-space overflow',name,len(data));_,i=min(fit);s=slots[i]
    s['used']=((s['used']+h[8]-1)&-h[8])+len(data);s['inputs'].append(name)
script='SECTIONS {\n'+''.join(f".slot{i} {s['start']:#x} : {{ "+' '.join(f'KEEP(*({n}))' for n in s['inputs'])+' }\n' for i,s in sorted(enumerate(slots),key=lambda row:row[1]['start']))
script+=' /DISCARD/ : { *(.comment .note* .llvm_addrsig) }\n}\n';(out/'copy.ld').write_text(script)
old=json.loads((root/'out/lmi-gpu-queue-v64b/runtime-symbols.json').read_text())
display=json.loads((root/'out/lmi-display-fast-v62d/runtime-symbols.json').read_text())
bindings={k:old[k] for k in ['cache_sync','rsc_write','desktop_service_start']}
bindings.update({f'lmi_v66_{n}':old['lmi_gpu_counter' if n=='counter' else n] for n in ['state','drain','hold','counter']})
bindings['lmi_v66_emit']=display['emit']
linked=out/'copy.elf'
with (out/'link.log').open('w') as log:
    subprocess.run(['ld.lld','-T',str(out/'copy.ld'),'--entry=lmi_gpu_copy_start',str(obj),
        *[f'--defsym={n}={v:#x}' for n,v in bindings.items()],'-o',str(linked)],stdout=log,stderr=subprocess.STDOUT,check=True)
syms={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(linked)],text=True).splitlines() if len(v:=line.split())==3}
result=bytearray(raw);ranges=[];placed=[]
for name,(h,data) in elf(linked).items():
    s=slots[int(name[5:])];assert h[3]==s['start'] and len(data)<=s['capacity']
    at=off(h[3],len(data));result[at:at+len(data)]=data;ranges.append([at,at+len(data)])
    placed.append(dict(section=name,start=hex(h[3]),bytes=len(data),capacity=s['capacity'],inputs=s['inputs']))
stub=0xfffffff0074d490c
space=json.loads(spaces[0].read_text());r=next(r for r in space['regions'] if r['accepted'])
assert list(struct.unpack_from('<II',raw,off(stub)))==r['original_entry_words']
struct.pack_into('<II',result,off(stub),0x52800000,0xd65f03c0);ranges.append([off(stub),off(stub)+8])
calls=[]
for pc in range(old['lmi_gpu_desktop'],old['lmi_gpu_tile_opt'],4):
    w=struct.unpack_from('<I',raw,off(pc))[0]
    if w&0xfc000000==0x94000000 and dest(w,pc)==old['desktop_service_start']:calls.append(pc)
call,=calls;original_branch=struct.unpack_from('<I',raw,off(call+4))[0]
assert original_branch&0xfc000000==0x14000000
epilogue=dest(original_branch,call+4);assert epilogue==0xfffffff0074da96c
target=syms['lmi_gpu_copy_start'];assert abs(target-call)<1<<27 and (target-call)%4==0
delta=(epilogue-call-4)//4;assert -(1<<13)<=delta<1<<13
# Success keeps the original saved true value and branches to its epilogue.
# Zero falls through the unmodified native bind-failure block (no service).
struct.pack_into('<II',result,off(call),0x94000000|(((target-call)//4)&0x3ffffff),
                 0x37000000|((delta&0x3fff)<<5)) # tbnz w0,#0,original epilogue
ranges.append([off(call),off(call)+8])
restored=bytearray(result)
for a,z in ranges:restored[a:z]=raw[a:z]
assert restored==raw and len(result)==len(raw)
names=['build-lmi-gpu-copy-v66.py','lmi-gpu-copy-v66.c','lmi-gpu-copy-v66.h']
inputs=[base,*spaces,host_path,pm4,root/'out/lmi-gpu-queue-v64b/runtime-symbols.json',
        root/'out/lmi-display-fast-v62d/runtime-symbols.json']
report=dict(result='HOST_BUILT_ONLY',sha256=hashlib.sha256(result).hexdigest(),base_sha256=sha(base),
    sources={n:sha(root/'tools'/n) for n in names},inputs={str(q.relative_to(root)):sha(q) for q in inputs},
    compile_flags=flags,bindings={n:hex(v) for n,v in bindings.items()},sections=placed,allowed_file_ranges=ranges,
    entry_stub=hex(stub),service_call=hex(call),probe_result_branch=hex(call+4),
    success_epilogue=hex(epilogue),original_failure_block_preserved=True,
    outside_edits_exact=True,full_rx_segments_scanned=True,boot_only_copy_probe=True,
    scratch_iova='0x01010000',source_offset='0x800',target_offset='0xc00',copy_bytes=1020,
    hardware_tested=False,performance_verified=False,desktop_gpu_copy=False,direct_surface_dma=False,
    wifi_integrated=False,display_copy_unchanged=True,source_retirement_unchanged=True,touch_unchanged=True)
(out/'mach.development.bcm2837').write_bytes(result)
(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'runtime-symbols.json').write_text(json.dumps(syms,indent=2)+'\n')
subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
print(json.dumps(dict(sha256=report['sha256'],sections=placed,service_call=hex(call)),indent=2))
