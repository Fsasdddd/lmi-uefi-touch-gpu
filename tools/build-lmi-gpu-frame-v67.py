"""Place real desktop GPU-copy hooks in audited obsolete GPU-step bodies."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v67');args=p.parse_args()
assert re.fullmatch(r'v67[a-z]?',args.attempt)
root=Path(__file__).resolve().parents[1];out=root/('out/lmi-gpu-frame-'+args.attempt)
assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=root/'out/lmi-gpu-copy-v66c/mach.development.bcm2837';raw=base.read_bytes()
assert sha(base)=='64ff409c50ca8deccef195ac787227c4dce7f0720934b64f35fa9f7f372f84c1'
helper=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'));segs=helper['segments'](raw)
native={n:a for a,k,n in helper['symbols']((root/'out/lmi-display-probe-v56f/kernel-symbols.txt').read_text())}
def off(pc,n=4):
    hits=[s[2]+pc-s[0] for s in segs.values() if s[0]<=pc and pc+n<=s[0]+s[3]]
    assert len(hits)==1;return hits[0]
def dest(w,pc):
    assert w&0xfc000000==0x94000000
    n=w&0x3ffffff;return pc+4*(n-(1<<26) if n&(1<<25) else n)
def elf(path):
    b=path.read_bytes();assert b[:6]==b'\x7fELF\x02\x01'
    at=struct.unpack_from('<Q',b,40)[0];size,count,ni=struct.unpack_from('<HHH',b,58)
    hs=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*size) for i in range(count)]
    strings=b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
    return {strings[h[0]:strings.index(b'\0',h[0])].decode():(h,b[h[4]:h[4]+h[5]]) for h in hs if h[0] and h[2]&2 and h[5]}
space_path=root/'out/lmi-gpu-frame-space-v67/result.json';space=json.loads(space_path.read_text())
assert space['base_sha256']==sha(base) and space['full_rx_segments_scanned'] and space['accepted_bytes']==9828
for n,d in space['sources'].items():assert sha(root/n)==d,n
slots=[]
for r in space['regions']:
    if not r['accepted']:continue
    lo,hi=int(r['start'],16),int(r['end'],16)
    assert lo==int(r['entry'],16)+8 and hi-lo==r['bytes']
    assert not any(r[n] for n in ['direct_references','page_references','unwind_references'])
    assert r['loaded_pointer_targets_entry_only'] and r['step_reader_replaced'] and r['recovery_replaced']
    assert hashlib.sha256(raw[off(lo):off(lo)+hi-lo]).hexdigest()==r['body_sha256']
    slots.append(dict(start=lo,capacity=hi-lo,used=0,inputs=[],region=r))
host_path=root/'out/lmi-gpu-frame-v67-host/result.json';host=json.loads(host_path.read_text())
assert host['result']=='PASS' and host['scenarios']>=21 and len(host['mutations_caught'])==11
for flag in ['asan_ubsan','actual_v64_backend','original_compositor_pipeline','separate_cpu_dma_views','independent_packet_decode','static_analysis']:assert host[flag]
for n,d in host['sources'].items():assert sha(root/'tools'/n)==d,n
for n,d in host['generated_sources'].items():assert sha(host_path.parent/n)==d,n
flags=['--target=aarch64-none-elf','-Oz','-mllvm','-enable-machine-outliner=always','-ffunction-sections',
       '-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-Wall','-Wextra','-Werror']
obj=out/'frame.o';subprocess.run(['clang',*flags,'-c',str(root/'tools/lmi-gpu-frame-v67.c'),'-o',str(obj)],check=True)
for name,(h,data) in sorted(elf(obj).items(),key=lambda row:-len(row[1][1])):
    assert h[1]==1 and not h[2]&1 and name.startswith(('.text.','.rodata.'))
    fit=[(s['capacity']-((s['used']+h[8]-1)&-h[8])-len(data),i) for i,s in enumerate(slots)
         if ((s['used']+h[8]-1)&-h[8])+len(data)<=s['capacity']]
    assert fit,('code-space overflow',name,len(data));_,i=min(fit);s=slots[i]
    s['used']=((s['used']+h[8]-1)&-h[8])+len(data);s['inputs'].append(name)
script='SECTIONS {\n'+''.join(f".slot{i} {s['start']:#x} : {{ "+' '.join(f'KEEP(*({n}))' for n in s['inputs'])+' }\n'
    for i,s in sorted(enumerate(slots),key=lambda row:row[1]['start']) if s['inputs'])
script+=' /DISCARD/ : { *(.comment .note* .llvm_addrsig) }\n}\n';(out/'frame.ld').write_text(script)
display_path=root/'out/lmi-display-fast-v62d/runtime-symbols.json'
pre_path=root/'out/lmi-display-preclean-v65b/runtime-symbols.json'
gpu_path=root/'out/lmi-gpu-queue-v64b/runtime-symbols.json'
display=json.loads(display_path.read_text());pre=json.loads(pre_path.read_text());gpu=json.loads(gpu_path.read_text())
bindings={n:display[n] for n in ['lmi_fast_state','lmi_fast_draw','IOMallocAligned','bzero','IOLockLock','IOLockUnlock']}
bindings.update({n:pre[n] for n in ['lmi_preclean_frame','lmi_preclean_cleanup','lmi_preclean_original_clean']})
bindings.update({n:gpu[n] for n in ['lmi_desktop_map','lmi_desktop_mapped','lmi_desktop_unmap',
                                'lmi_desktop_to_memory','lmi_desktop_submit','cache_sync']})
bindings.update(lmi_frame_backend=gpu['state'],lmi_frame_drain=gpu['drain'],lmi_frame_hold=gpu['hold'],
    lmi_frame_ticks=gpu['lmi_gpu_counter'],lmi_frame_physical=native['_kvtophys'],
    lmi_frame_gpu_lock=native['__ZL8gGPULock'],lmi_frame_retain=native['__ZNK8OSObject6retainEv'],
    lmi_frame_release=native['__ZNK8OSObject7releaseEv'],lmi_frame_preclean_ready=pre['ready'],lmi_frame_emit=display['emit'],
    redwood_gpu_address=native['_redwood_gpu_address'],redwood_gpu_address_free=native['_redwood_gpu_address_free'])
assert bindings['lmi_frame_gpu_lock']==0xfffffff007f269e8
linked=out/'frame.elf'
with (out/'link.log').open('w') as log:
    subprocess.run(['ld.lld','-T',str(out/'frame.ld'),'--entry=lmi_gpu_frame_frame',str(obj),
        *[f'--defsym={n}={v:#x}' for n,v in bindings.items()],'-o',str(linked)],check=True,stdout=log,stderr=subprocess.STDOUT)
syms={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(linked)],text=True).splitlines() if len(v:=line.split())==3}
result=bytearray(raw);ranges=[];placed=[];stubs=[]
for name,(h,data) in elf(linked).items():
    s=slots[int(name[5:])];assert h[3]==s['start'] and len(data)<=s['capacity']
    at=off(h[3],len(data));result[at:at+len(data)]=data;ranges.append([at,at+len(data)])
    entry=s['start']-8;r=s['region']
    assert list(struct.unpack_from('<II',raw,off(entry)))==r['original_entry_words']
    struct.pack_into('<II',result,off(entry),0x52800000,0xd65f03c0);ranges.append([off(entry),off(entry)+8]);stubs.append(hex(entry))
    placed.append(dict(section=name,start=hex(h[3]),bytes=len(data),capacity=s['capacity'],inputs=s['inputs']))
# Only the early clean() call inside the exact linked v65 frame function.
old_obj=elf(root/'out/lmi-display-preclean-v65b/preclean.o')
frame_size=old_obj['.text.lmi_preclean_frame'][0][5]
early=[pc for pc in range(pre['lmi_preclean_frame'],pre['lmi_preclean_frame']+frame_size,4)
       if (w:=struct.unpack_from('<I',raw,off(pc))[0])&0xfc000000==0x94000000 and dest(w,pc)==pre['lmi_preclean_original_clean']]
early_call,=early
hooks=[]
for pc,old,name in [(0xfffffff007ae00bc,pre['lmi_preclean_frame'],'lmi_gpu_frame_frame'),
    (0xfffffff0074d30e4,pre['lmi_preclean_allocate'],'lmi_gpu_frame_allocate'),
    (0xfffffff0074d24a0,pre['lmi_preclean_cleanup'],'lmi_gpu_frame_cleanup'),
    (0xfffffff0079e3d80,display['lmi_fast_draw'],'lmi_gpu_frame_draw'),
    (early_call,pre['lmi_preclean_original_clean'],'lmi_gpu_frame_clean')]:
    w=struct.unpack_from('<I',raw,off(pc))[0];assert dest(w,pc)==old
    target=syms[name];assert abs(target-pc)<1<<27 and not((target-pc)&3)
    struct.pack_into('<I',result,off(pc),0x94000000|(((target-pc)//4)&0x3ffffff));ranges.append([off(pc),off(pc)+4])
    hooks.append(dict(pc=hex(pc),original=hex(old),target=hex(target),symbol=name))
restored=bytearray(result)
for a,z in ranges:restored[a:z]=raw[a:z]
assert restored==raw and len(raw)==len(result)
names=['build-lmi-gpu-frame-v67.py','lmi-gpu-frame-v67.c','lmi-gpu-frame-v67.h','lmi-display-preclean-v65.h',
       'lmi-display-fast-v62.h','lmi-display-pipeline.h','lmi-display-dma.h','lmi-display-compositor-abi.h',
       'lmi-display-surface-abi.h','lmi-gpu-copy-v66.h']
inputs=[base,space_path,host_path,display_path,pre_path,gpu_path,root/'out/lmi-display-preclean-v65b/preclean.o',
        root/'out/lmi-display-probe-v56f/kernel-symbols.txt',root/'tools/lmi-gpu-hfi-io.c']
report=dict(result='HOST_BUILT_ONLY',sha256=hashlib.sha256(result).hexdigest(),base_sha256=sha(base),
    sources={n:sha(root/'tools'/n) for n in names},inputs={str(q.relative_to(root)):sha(q) for q in inputs},
    compile_flags=flags,bindings={n:hex(v) for n,v in bindings.items()},sections=placed,hooks=hooks,entry_stubs=stubs,
    early_clean_function_bytes=frame_size,allowed_file_ranges=ranges,outside_edits_exact=True,full_rx_space_audit=True,
    journal_prefix_preserved=True,persistent_source_limit=8,desktop_gpu_copy=True,partial_cpu_compositor_preserved=True,
    source_retirement_unchanged=True,touch_unchanged=True,dpu_pipeline_unchanged=True,
    allocations_retained_until_ram_return=True,direct_surface_scanout=False,wifi_integrated=False,
    hardware_tested=False,performance_verified=False)
(out/'mach.development.bcm2837').write_bytes(result);(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'runtime-symbols.json').write_text(json.dumps(syms,indent=2)+'\n')
subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
print(json.dumps(dict(sha256=report['sha256'],sections=placed,hooks=hooks),indent=2))
