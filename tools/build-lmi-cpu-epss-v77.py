"""Build independent, restorable CPU requests on the successful v73 image."""
from pathlib import Path
from importlib.machinery import SourceFileLoader
import argparse,hashlib,json,re,struct,subprocess
ROOT=Path(__file__).resolve().parents[1]
helper=SourceFileLoader('v73_build',str(ROOT/'tools/build-lmi-display-timing-v73.py')).load_module()
sha=helper.sha;elf=helper.elf
BASE=ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837'
BASE_SHA='68ec1820fea704e99ab1ccac5d70f19670faa9428378f75592f251ff5ede56c2'
NATIVE=0xfffffff007004000
START,END=0xfffffff0074d0a78,0xfffffff0074d1e74
INIT=0xfffffff0074d0dfc
SYMBOLS=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v73-desktop-180/display-v56-candidate/kernel-symbols.txt'


def build(attempt):
    assert re.fullmatch('v77[a-z]?',attempt)
    out=ROOT/('out/lmi-cpu-epss-'+attempt);assert not out.exists();out.mkdir()
    assert sha(BASE)==BASE_SHA;original=BASE.read_bytes()
    symbols={v[2]:int(v[0],16) for line in SYMBOLS.read_text().splitlines() if len(v:=line.split())==3}
    assert symbols['_redwood_cpufreq_init']==INIT and symbols['_redwood_ddr_quiesce']==START
    assert symbols['_redwood_adreno_quiesce']==END and symbols['_ddr_rsc']==0xfffffff007e98850
    flags=['--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
           '-mgeneral-regs-only','-fno-stack-protector','-fno-omit-frame-pointer','-Wall','-Wextra','-Werror']
    objects=[]
    for name in ['lmi-cpu-epss','lmi-cpu-epss-native']:
        obj=out/(name+'.o');subprocess.run(['clang',*flags,'-c',str(ROOT/'tools'/(name+'.c')),'-o',str(obj)],check=True);objects.append(obj)
    slots=[dict(start=START+4,capacity=INIT-START-4,used=0,inputs=[]),
           dict(start=INIT+4,capacity=END-INIT-4,used=0,inputs=[])]
    sections=[]
    for obj in objects:
        for name,(h,data) in elf(obj).items():
            assert h[1]==1 and not h[2]&1 and name.startswith(('.text.','.rodata.')),name
            sections.append((obj,name,h,data))
    for obj,name,h,data in sorted(sections,key=lambda r:-len(r[3])):
        fits=[]
        for i,s in enumerate(slots):
            at=((s['start']+s['used']+h[8]-1)&-h[8])-s['start']
            if at+len(data)<=s['capacity']:fits.append((s['capacity']-at-len(data),i,at))
        assert fits,('legacy CPU helper space exhausted',name,len(data))
        _,i,at=min(fits);slots[i]['used']=at+len(data);slots[i]['inputs'].append((obj.name,name))
    script='SECTIONS {\n'+''.join(f".slot{i} {s['start']:#x} : {{ "+' '.join(f'KEEP({obj}({n}))' for obj,n in s['inputs'])+' }\n'
        for i,s in enumerate(slots) if s['inputs'])+' /DISCARD/ : { *(.comment .note* .llvm_addrsig) }\n}\n'
    (out/'epss.ld').write_text(script)
    display=json.loads((ROOT/'out/lmi-display-timing-v73/runtime-symbols.json').read_text())
    bindings={n:symbols['_'+n] for n in ['PE_parse_boot_argn','ml_io_map','IOMallocAligned','bzero','memcpy']}
    bindings.update(lmi_epss_native_state=symbols['_ddr_rsc'],lmi_frame_emit=display['lmi_frame_emit'],lmi_timing_cleanup=display['lmi_timing_cleanup'])
    linked=out/'epss.elf'
    subprocess.run(['ld.lld','-T','epss.ld','--entry=lmi_epss_native_init',*[obj.name for obj in objects],
        *[f'--defsym={n}={v:#x}' for n,v in bindings.items()],'-o',linked.name],cwd=out,check=True)
    assert not subprocess.check_output(['llvm-nm','-u',str(linked)],text=True).strip()
    syms={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(linked)],text=True).splitlines() if len(v:=line.split())==3}
    raw=bytearray(original);ranges=[];placed=[]
    for name,(h,data) in elf(linked).items():
        assert name.startswith('.slot');s=slots[int(name[5:])]
        assert h[3]==s['start'] and len(data)<=s['capacity']
        at=h[3]-NATIVE;raw[at:at+len(data)]=data;ranges.append([at,at+len(data)])
        placed.append(dict(section=name,start=hex(h[3]),bytes=len(data),capacity=s['capacity'],inputs=s['inputs']))
    hooks=[]
    for pc,sym in [(START,'lmi_epss_native_quiesce'),(INIT,'lmi_epss_native_init')]:
        at=pc-NATIVE;target=syms[sym];delta=target-pc
        assert not delta&3 and -(1<<27)<=delta<(1<<27)
        before=struct.unpack_from('<I',original,at)[0]
        after=0x14000000|((delta//4)&0x3ffffff);struct.pack_into('<I',raw,at,after);ranges.append([at,at+4])
        hooks.append(dict(pc=hex(pc),symbol=sym,target=hex(target),old_word=hex(before),new_word=hex(after)))
    pc=0xfffffff0074d24a0;at=pc-NATIVE;before=struct.unpack_from('<I',original,at)[0]
    delta=before&0x3ffffff
    assert before&0xfc000000==0x94000000 and pc+4*(delta-(1<<26) if delta&(1<<25) else delta)==display['lmi_timing_cleanup']
    target=syms['lmi_epss_native_cleanup'];delta=target-pc
    assert not delta&3 and -(1<<27)<=delta<(1<<27)
    after=0x94000000|((delta//4)&0x3ffffff);struct.pack_into('<I',raw,at,after);ranges.append([at,at+4])
    hooks.append(dict(pc=hex(pc),symbol='lmi_epss_native_cleanup',target=hex(target),old_word=hex(before),new_word=hex(after)))
    restored=bytearray(raw)
    for a,z in ranges:restored[a:z]=original[a:z]
    assert restored==original and len(raw)==len(original)
    assert raw[0xfffffff0079e59e4-NATIVE:0xfffffff0079e5b00-NATIVE]==original[0xfffffff0079e59e4-NATIVE:0xfffffff0079e5b00-NATIVE]
    (out/'mach.development.bcm2837').write_bytes(raw)
    (out/'runtime-symbols.json').write_text(json.dumps(syms,indent=2)+'\n')
    inputs=[Path(__file__),Path(helper.__file__),BASE,SYMBOLS,ROOT/'tools/lmi-cpu-epss.c',ROOT/'tools/lmi-cpu-epss.h',
            ROOT/'tools/lmi-cpu-epss-native.c',ROOT/'out/lmi-display-timing-v73/runtime-symbols.json',
            ROOT/'out/lmi-cpu-epss/board-profile-b/profile.json',ROOT/'out/lmi-cpu-epss/host-c/result.json']
    report=dict(result='HOST_BUILT_ONLY_REQUIRES_LINK_REVIEW',base_sha256=BASE_SHA,sha256=hashlib.sha256(raw).hexdigest(),
        sections=placed,hooks=hooks,bindings={n:hex(v) for n,v in bindings.items()},compile_flags=flags,
        replaced_unit=[hex(START),hex(END)],state_pointer=hex(bindings['lmi_epss_native_state']),
        allowed_file_ranges=ranges,outside_edits_exact=True,native_gpu_poll_us=200,v72_touch_preserved=True,
        original_gpu_and_dpu_bodies_exact=True,display_cleanup_wrapped_after_original_stop=True,
        loader_return_and_psci_code_exact=True,ddr_disabled=True,
        independent_boot_arg='lmi_cpu=2',read_only_boot_arg='lmi_cpu=1',
        request_caps_khz=[1804800,2419200,2841600],max_cores_parameter=[4,4,4],
        hardware_tested=False,measured_cpu_frequency=None,performance_verified=False,wifi_integrated=False,
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in inputs})
    (out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
    print(json.dumps(dict(result=report['result'],sha256=report['sha256'],placed_bytes=sum(r['bytes'] for r in placed)),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--attempt',default='v77');build(p.parse_args().attempt)
