"""Bound native DPU short waits on exact v73; preserve all earlier code."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess
from importlib.machinery import SourceFileLoader
ROOT=Path(__file__).resolve().parents[1]
helper=SourceFileLoader('v73_builder',str(ROOT/'tools/build-lmi-display-timing-v73.py')).load_module()
elf=helper.elf;sha=helper.sha
BASE=ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837'
BASE_SHA='68ec1820fea704e99ab1ccac5d70f19670faa9428378f75592f251ff5ede56c2'

def build(attempt):
    assert re.fullmatch(r'v74[a-z]?',attempt)
    out=ROOT/('out/lmi-display-wait-'+attempt);assert not out.exists();out.mkdir()
    assert sha(BASE)==BASE_SHA;raw=BASE.read_bytes()
    space_path=ROOT/'out/lmi-gpu-frame-space-v67/result.json'
    assert sha(space_path)=='5d51ad76d63f38e1edbfe741f210be922e826336d2b2a36275a2fc4928cc01c6'
    space=json.loads(space_path.read_text());assert space['full_rx_segments_scanned']
    previous=[ROOT/'out/lmi-gpu-deferred-cache-v71/build-audit.json',
              ROOT/'out/lmi-display-timing-v73/build-audit.json']
    reports=[json.loads(p.read_text()) for p in previous]
    assert sha(previous[0])=='b26b2fac99ac1d62fd03c16bf2845b23ad07a16ddf0683322a8037211b5d81fc'
    assert sha(previous[1])=='28be76910c0a461c790c06b82dbc0e020a925b37f9b25ba21cb8b01e60f53f5c'
    slots=[]
    for region in space['regions']:
        if not region['accepted']:continue
        lo,hi=int(region['start'],16),int(region['end'],16)
        assert not any(region[k] for k in ['direct_references','page_references','unwind_references'])
        assert region['loaded_pointer_targets_entry_only'] and region['step_reader_replaced'] and region['recovery_replaced']
        end=lo
        for report in reports:
            for row in report['sections']:
                a=int(row['start'],16);z=a+row['bytes']
                if lo<=a<hi:assert z<=hi;end=max(end,z)
        if end<hi:slots.append(dict(start=end,capacity=hi-end,used=0,inputs=[],entry=lo-8))
    flags=reports[1]['compile_flags'];obj=out/'wait.o'
    subprocess.run(['clang',*flags,'-c',str(ROOT/'tools/lmi-display-wait-v74.c'),'-o',str(obj)],check=True)
    for name,(h,data) in sorted(elf(obj).items(),key=lambda r:-len(r[1][1])):
        assert h[1]==1 and not h[2]&1 and name.startswith(('.text.','.rodata.'))
        fits=[]
        for i,s in enumerate(slots):
            a=((s['start']+s['used']+h[8]-1)&-h[8])-s['start']
            if a+len(data)<=s['capacity']:fits.append((s['capacity']-a-len(data),i,a))
        assert fits,('free code space exhausted',name,len(data))
        _,i,a=min(fits);s=slots[i];s['used']=a+len(data);s['inputs'].append(name)
    script='SECTIONS {\n'+''.join(f".slot{i} {s['start']:#x} : {{ "+' '.join(f'KEEP(*({n}))' for n in s['inputs'])+' }\n'
        for i,s in enumerate(slots) if s['inputs'])+' /DISCARD/ : { *(.comment .note* .llvm_addrsig) }\n}\n'
    (out/'wait.ld').write_text(script)
    symbols_path=ROOT/'out/lmi-display-timing-v73/runtime-symbols.json'
    native=json.loads(symbols_path.read_text())
    bindings={n:native[n] for n in ['lmi_fast_state','IOMallocAligned','bzero','lmi_frame_ticks','lmi_frame_emit','lmi_timing_cleanup']}
    bindings['lmi_wait_original_delay']=0xfffffff0072c9328
    linked=out/'wait.elf'
    subprocess.run(['ld.lld','-T',str(out/'wait.ld'),'--entry=lmi_wait_delay',str(obj),
        *[f'--defsym={n}={v:#x}' for n,v in bindings.items()],'-o',str(linked)],check=True)
    syms={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(linked)],text=True).splitlines() if len(v:=line.split())==3}
    assert not subprocess.check_output(['llvm-nm','-u',str(linked)],text=True).strip()
    result=bytearray(raw);ranges=[];placed=[];stubs=[]
    def off(pc,n=4):
        at=pc-0xfffffff007004000;assert 0<=at and at+n<=len(raw);return at
    for name,(h,data) in elf(linked).items():
        s=slots[int(name[5:])];assert h[3]==s['start'] and len(data)<=s['capacity']
        at=off(h[3],len(data));result[at:at+len(data)]=data;ranges.append([at,at+len(data)])
        entry=off(s['entry']);words=struct.unpack_from('<II',raw,entry)
        if words!=(0x52800000,0xd65f03c0):
            region=next(r for r in space['regions'] if int(r['entry'],16)==s['entry'])
            assert list(words)==region['original_entry_words']
            struct.pack_into('<II',result,entry,0x52800000,0xd65f03c0)
            ranges.append([entry,entry+8]);stubs.append(hex(s['entry']))
        placed.append(dict(section=name,start=hex(h[3]),bytes=len(data),capacity=s['capacity'],entry=hex(s['entry']),inputs=s['inputs']))
    hooks=[]
    for pc,original,name in [(0xfffffff007ae0100,bindings['lmi_wait_original_delay'],'lmi_wait_delay'),
        (0xfffffff0074d30e4,native['lmi_timing_allocate'],'lmi_wait_allocate'),
        (0xfffffff0074d24a0,native['lmi_timing_cleanup'],'lmi_wait_cleanup')]:
        at=off(pc);w=struct.unpack_from('<I',raw,at)[0];d=w&0x3ffffff
        assert w&0xfc000000==0x94000000 and pc+4*(d-(1<<26) if d&(1<<25) else d)==original
        dest=syms[name];delta=dest-pc;assert not delta&3 and -(1<<27)<=delta<(1<<27)
        new=0x94000000|((delta//4)&0x3ffffff);struct.pack_into('<I',result,at,new);ranges.append([at,at+4])
        hooks.append(dict(pc=hex(pc),old_word=hex(w),new_word=hex(new),original=hex(original),target=hex(dest),symbol=name))
    restored=bytearray(result)
    for a,z in ranges:restored[a:z]=raw[a:z]
    assert restored==raw and len(result)==len(raw)
    (out/'mach.development.bcm2837').write_bytes(result)
    (out/'runtime-symbols.json').write_text(json.dumps(syms,indent=2)+'\n')
    inputs=[Path(__file__),Path(helper.__file__),BASE,space_path,*previous,symbols_path,
        ROOT/'tools/lmi-display-wait-v74.c',ROOT/'tools/lmi-display-wait-v74.h',ROOT/'tools/lmi-display-timing-v73.h']
    report=dict(result='HOST_BUILT_ONLY',base_sha256=BASE_SHA,sha256=hashlib.sha256(result).hexdigest(),
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},compile_flags=flags,
        bindings={n:hex(v) for n,v in bindings.items()},sections=placed,hooks=hooks,new_entry_stubs=stubs,
        allowed_file_ranges=ranges,outside_edits_exact=True,append_only_journal=True,
        spin_step_ticks=960,spin_budget_ticks=160000,original_dpu_poll_exact=True,
        v73_timing_code_preserved=True,v72_touch_preserved=True,original_gpu_code_preserved=True,
        original_fences_and_timeout_preserved=True,hot_path_logging=False,
        hardware_tested=False,performance_verified=False,wifi_integrated=False)
    (out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
    print(json.dumps(dict(result=report['result'],sha256=report['sha256'],placed_bytes=sum(r['bytes'] for r in placed),hooks=hooks),indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--attempt',default='v74');build(p.parse_args().attempt)
