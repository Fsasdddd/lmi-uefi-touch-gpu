"""Place timing wrappers only in audited free tails of the exact v72b image."""
from pathlib import Path
import argparse, hashlib, json, re, struct, subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'out/lmi-touch-cadence-v72b/mach.development.bcm2837'
BASE_SHA = '1e76f68263c0e9c02d47fd2528f7f589087726f1d59fb96154e9b5c928077a8b'
NATIVE_BASE = 0xfffffff007004000


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def elf(p):
    b = p.read_bytes()
    assert b[:6] == b'\x7fELF\x02\x01'
    at = struct.unpack_from('<Q', b, 40)[0]
    size, count, ni = struct.unpack_from('<HHH', b, 58)
    hs = [struct.unpack_from('<IIQQQQIIQQ', b, at+i*size) for i in range(count)]
    names = b[hs[ni][4]:hs[ni][4]+hs[ni][5]]
    return {names[h[0]:names.index(b'\0', h[0])].decode(): (h, b[h[4]:h[4]+h[5]])
            for h in hs if h[0] and h[2]&2 and h[5]}


def build(attempt):
    assert re.fullmatch(r'v73[a-z]?', attempt)
    out = ROOT/('out/lmi-display-timing-'+attempt)
    assert not out.exists(), 'Preserve old attempts'
    out.mkdir()
    assert sha(BASE) == BASE_SHA
    raw = BASE.read_bytes()
    space_path = ROOT/'out/lmi-gpu-frame-space-v67/result.json'
    assert sha(space_path) == '5d51ad76d63f38e1edbfe741f210be922e826336d2b2a36275a2fc4928cc01c6'
    space = json.loads(space_path.read_text())
    prior_path = ROOT/'out/lmi-gpu-deferred-cache-v71/build-audit.json'
    prior = json.loads(prior_path.read_text())
    assert sha(prior_path) == 'b26b2fac99ac1d62fd03c16bf2845b23ad07a16ddf0683322a8037211b5d81fc'
    assert space['accepted_bytes'] == 9828 and space['full_rx_segments_scanned']
    used = {int(s['start'],16): s['bytes'] for s in prior['sections']}
    slots = []
    for region in space['regions']:
        if not region['accepted']:
            continue
        lo, hi = int(region['start'],16), int(region['end'],16)
        assert lo == int(region['entry'],16)+8 and hi-lo == region['bytes']
        assert not any(region[k] for k in ['direct_references','page_references','unwind_references'])
        assert region['loaded_pointer_targets_entry_only'] and region['step_reader_replaced'] and region['recovery_replaced']
        n = used.get(lo, 0)
        slots.append(dict(start=lo+n, capacity=hi-lo-n, used=0, inputs=[], entry=lo-8,
                          prior_bytes=n, region=region))
    flags = ['--target=aarch64-none-elf','-Oz','-mllvm','-enable-machine-outliner=always',
             '-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
             '-mgeneral-regs-only','-fno-stack-protector','-Wall','-Wextra','-Werror']
    obj = out/'timing.o'
    subprocess.run(['clang',*flags,'-c',str(ROOT/'tools/lmi-display-timing-v73.c'),'-o',str(obj)],check=True)
    for name, (h, data) in sorted(elf(obj).items(),key=lambda row:-len(row[1][1])):
        assert h[1] == 1 and not h[2]&1 and name.startswith(('.text.','.rodata.'))
        fit = []
        for i, s in enumerate(slots):
            aligned = ((s['start']+s['used']+h[8]-1)&-h[8])-s['start']
            if aligned+len(data)<=s['capacity']:
                fit.append((s['capacity']-aligned-len(data),i,aligned))
        assert fit, ('free code space exhausted',name,len(data))
        _, i, aligned = min(fit)
        s = slots[i];s['used']=aligned+len(data);s['inputs'].append(name)
    script = 'SECTIONS {\n'+''.join(
        f".slot{i} {s['start']:#x} : {{ "+' '.join(f'KEEP(*({n}))' for n in s['inputs'])+' }\n'
        for i,s in enumerate(slots) if s['inputs'])
    script += ' /DISCARD/ : { *(.comment .note* .llvm_addrsig) }\n}\n'
    (out/'timing.ld').write_text(script)
    gpu_path = ROOT/'out/lmi-gpu-deferred-cache-v71/runtime-symbols.json'
    gpu = json.loads(gpu_path.read_text())
    bindings = {n:gpu[n] for n in ['lmi_fast_state','IOMallocAligned','bzero','lmi_frame_ticks','lmi_frame_emit',
        'lmi_gpu_frame_frame','lmi_gpu_frame_cleanup']}
    bindings.update(lmi_timing_original_submit=0xfffffff007ae0b74,
                    lmi_timing_original_source=0xfffffff0079e5970)
    linked = out/'timing.elf'
    subprocess.run(['ld.lld','-T',str(out/'timing.ld'),'--entry=lmi_timing_frame',str(obj),
        *[f'--defsym={n}={v:#x}' for n,v in bindings.items()],'-o',str(linked)],check=True)
    syms = {v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(linked)],text=True).splitlines()
            if len(v:=line.split())==3}
    result = bytearray(raw);ranges=[];placed=[];stubs=[]
    def off(pc,n=4):
        at=pc-NATIVE_BASE
        assert 0<=at and at+n<=len(raw)
        return at
    for name,(h,data) in elf(linked).items():
        s=slots[int(name[5:])]
        assert h[3]==s['start'] and len(data)<=s['capacity']
        at=off(h[3],len(data));result[at:at+len(data)]=data;ranges.append([at,at+len(data)])
        entry=off(s['entry'])
        if s['prior_bytes']:
            assert struct.unpack_from('<II',raw,entry)==(0x52800000,0xd65f03c0)
        else:
            assert list(struct.unpack_from('<II',raw,entry))==s['region']['original_entry_words']
            struct.pack_into('<II',result,entry,0x52800000,0xd65f03c0)
            ranges.append([entry,entry+8]);stubs.append(hex(s['entry']))
        placed.append(dict(section=name,start=hex(h[3]),bytes=len(data),capacity=s['capacity'],
                           prior_bytes=s['prior_bytes'],entry=hex(s['entry']),inputs=s['inputs']))
    hooks=[]
    for pc, old, symbol in [
        (0xfffffff007ae00bc, gpu['lmi_gpu_frame_frame'], 'lmi_timing_frame'),
        (0xfffffff0074d30e4, gpu['lmi_gpu_frame_allocate'], 'lmi_timing_allocate'),
        (0xfffffff0074d24a0, gpu['lmi_gpu_frame_cleanup'], 'lmi_timing_cleanup'),
        (0xfffffff007ae020c, bindings['lmi_timing_original_submit'], 'lmi_timing_submit'),
        (0xfffffff007ae0420, None, 'lmi_timing_source')]:
        at=off(pc);w=struct.unpack_from('<I',raw,at)[0]
        if old is None:
            assert w==0xd63f0100 # BLR x8 in the unchanged native ready callback.
        else:
            assert w&0xfc000000==0x94000000
            delta=w&0x3ffffff
            assert pc+4*(delta-(1<<26) if delta&(1<<25) else delta)==old
        target=syms[symbol];delta=target-pc
        assert not delta&3 and -(1<<27)<=delta<(1<<27)
        new=0x94000000|((delta//4)&0x3ffffff)
        struct.pack_into('<I',result,at,new);ranges.append([at,at+4])
        hooks.append(dict(pc=hex(pc),old_word=hex(w),new_word=hex(new),target=hex(target),symbol=symbol))
    restored=bytearray(result)
    for a,z in ranges:restored[a:z]=raw[a:z]
    assert restored==raw and len(raw)==len(result)
    assert not subprocess.check_output(['llvm-nm','-u',str(linked)],text=True).strip()
    (out/'mach.development.bcm2837').write_bytes(result)
    (out/'runtime-symbols.json').write_text(json.dumps(syms,indent=2)+'\n')
    inputs=[Path(__file__),BASE,space_path,prior_path,gpu_path,ROOT/'tools/lmi-display-timing-v73.c',
        ROOT/'tools/lmi-display-timing-v73.h',ROOT/'tools/lmi-gpu-deferred-cache-v71.h',
        ROOT/'tools/lmi-display-preclean-v65.h',ROOT/'tools/lmi-display-fast-v62.h',
        ROOT/'tools/lmi-display-pipeline.h',ROOT/'tools/lmi-display-native-v56.c']
    report=dict(result='HOST_BUILT_ONLY',base_sha256=BASE_SHA,sha256=hashlib.sha256(result).hexdigest(),
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},compile_flags=flags,
        bindings={n:hex(v) for n,v in bindings.items()},sections=placed,hooks=hooks,
        new_entry_stubs=stubs,allowed_file_ranges=ranges,outside_edits_exact=True,
        append_only_journal=True,v71_gpu_code_preserved=True,v72_touch_preserved=True,
        original_source_wait_timeout_preserved=True,original_submit_timestamp_preserved=True,
        original_fences_and_dpu_poll_preserved=True,hot_path_logging=False,
        hardware_tested=False,performance_verified=False,wifi_integrated=False)
    (out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
    print(json.dumps(dict(result=report['result'],sha256=report['sha256'],
                          placed_bytes=sum(p['bytes'] for p in placed),hooks=hooks),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--attempt',default='v73')
    build(p.parse_args().attempt)
