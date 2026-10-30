"""Place the asynchronous DPU worker in the unused, audited CPU helper tail."""
from pathlib import Path
from importlib.machinery import SourceFileLoader
import hashlib,json,struct,subprocess

ROOT=Path(__file__).resolve().parents[1]
helper=SourceFileLoader('v73_build',str(ROOT/'tools/build-lmi-display-timing-v73.py')).load_module()
BASE=ROOT/'out/lmi-render-cpu-v79/mach.development.bcm2837'
BASE_SHA='e6f380af6a12a286caf5fbfdfa5cc62e040fd0a672107900ab17582a6cbc8ff4'
KBASE=0xfffffff007004000
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


if __name__=='__main__':
    out=ROOT/'out/lmi-display-async-v80a';out.mkdir(exist_ok=False)
    assert sha(BASE)==BASE_SHA;original=BASE.read_bytes()
    audit_path=ROOT/'out/lmi-cpu-epss-v77e/build-audit.json'
    assert sha(audit_path)=='5c4fe95c22be501bedd6b9469f9cff4af1a1bbc9b137239628cc07c7a3a963cf'
    audit=json.loads(audit_path.read_text())
    last=audit['sections'][1]
    start=(int(last['start'],16)+last['bytes']+3)&~3
    end=int(last['start'],16)+last['capacity']
    assert (start,end)==(0xfffffff0074d138c,0xfffffff0074d1e74)
    obj=out/'async.o'
    flags=['--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections',
           '-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector',
           '-fno-omit-frame-pointer','-Wall','-Wextra','-Werror']
    subprocess.run(['clang',*flags,'-c',str(ROOT/'tools/lmi-display-async-v80.c'),'-o',str(obj)],check=True)
    symbols={v[2]:int(v[0],16) for line in (ROOT/'out/kernel-symbols.txt').read_text().splitlines() if len(v:=line.split())==3}
    timing=json.loads((ROOT/'out/lmi-display-timing-v73/runtime-symbols.json').read_text())
    epss=json.loads((ROOT/'out/lmi-cpu-epss-v77e/runtime-symbols.json').read_text())
    fence=json.loads((ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v79-short45/display-v62-candidate/runtime-symbols.json').read_text())
    bindings={name:symbols['_'+name] for name in ['IOMallocAligned','IOLockAlloc','IOLockLock','IOLockUnlock',
        'IOLockWakeup','IOLockSleep','bzero','delay','IOSleep','kernel_thread_start','thread_deallocate']}
    bindings.update(lmi_async_native_state=0xfffffff007b46fe0,lmi_fast_state=fence['lmi_fast_state'],
        lmi_async_original_show=fence['lmi_fence_original_show'],
        lmi_async_original_cleanup=epss['lmi_epss_native_cleanup'],
        lmi_frame_ticks=timing['lmi_frame_ticks'],lmi_frame_emit=timing['lmi_frame_emit'],
        lmi_timing_frame=timing['lmi_timing_frame'],lmi_timing_submit=timing['lmi_timing_submit'],
        lmi_pipeline_poll=0xfffffff007ae0c90)
    script=f'SECTIONS {{ .async {start:#x} : {{ *(.text*) *(.rodata*) }} /DISCARD/ : {{ *(.comment .note* .llvm_addrsig) }} }}\n'
    (out/'async.ld').write_text(script)
    linked=out/'async.elf'
    subprocess.run(['ld.lld','-T',str(out/'async.ld'),'--entry=lmi_async_show',str(obj),
        *[f'--defsym={n}={v:#x}' for n,v in bindings.items()],'-o',str(linked)],check=True)
    sections=helper.elf(linked);assert list(sections)==['.async']
    header,data=sections['.async'];assert header[3]==start and len(data)<=end-start,(len(data),end-start)
    assert not subprocess.check_output(['llvm-nm','-u',str(linked)],text=True).strip()
    syms={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(linked)],text=True).splitlines() if len(v:=line.split())==3}
    # Find the sole call/tailcall from the unchanged source-retirement wrapper.
    first=fence['lmi_fence_show'];last_pc=fence['pending']
    show_calls=[]
    for pc in range(first,last_pc,4):
        word=struct.unpack_from('<I',original,pc-KBASE)[0]
        if word&0x7c000000!=0x14000000:continue
        delta=word&0x3ffffff
        target=pc+4*(delta-(1<<26) if delta&(1<<25) else delta)
        if target==bindings['lmi_async_original_show']:show_calls.append((pc,target,'lmi_async_show'))
    assert len(show_calls)==1,show_calls
    hooks=show_calls+[(0xfffffff0074d30e4,timing['lmi_timing_allocate'],'lmi_async_allocate'),
                      (0xfffffff0074d24a0,epss['lmi_epss_native_cleanup'],'lmi_async_cleanup')]
    raw=bytearray(original);at=start-KBASE;raw[at:at+len(data)]=data
    ranges=[[at,at+len(data)]];patches=[]
    for pc,expected,name in hooks:
        at=pc-KBASE;old=struct.unpack_from('<I',original,at)[0]
        delta=old&0x3ffffff
        assert old&0x7c000000==0x14000000
        assert pc+4*(delta-(1<<26) if delta&(1<<25) else delta)==expected
        target=syms[name];delta=target-pc
        assert not delta&3 and -(1<<27)<=delta<(1<<27)
        new=(old&0xfc000000)|((delta//4)&0x3ffffff)
        struct.pack_into('<I',raw,at,new);ranges.append([at,at+4])
        patches.append(dict(pc=hex(pc),old_word=hex(old),new_word=hex(new),symbol=name,target=hex(target)))
    restored=bytearray(raw)
    for a,z in ranges:restored[a:z]=original[a:z]
    assert restored==original and len(raw)==len(original)
    (out/'mach.development.bcm2837').write_bytes(raw)
    (out/'runtime-symbols.json').write_text(json.dumps(syms,indent=2)+'\n')
    subprocess.run(['llvm-objdump','-d',str(linked)],stdout=(out/'disassembly.txt').open('w'),check=True)
    paths=[Path(__file__),BASE,audit_path,ROOT/'tools/lmi-display-async-v80.c',ROOT/'tools/lmi-display-async-v80.h',
           ROOT/'tools/lmi-display-timing-v73.h',ROOT/'tools/lmi-display-probe.h']
    report=dict(result='HOST_BUILT_ONLY_REQUIRES_CONCURRENCY_REVIEW',base_sha256=BASE_SHA,
        sha256=hashlib.sha256(raw).hexdigest(),section_start=hex(start),section_bytes=len(data),section_capacity=end-start,
        hooks=patches,bindings={n:hex(v) for n,v in bindings.items()},allowed_file_ranges=ranges,outside_edits_exact=True,
        original_gpu_fences_and_copy_exact=True,original_source_drop_and_retirement_exact=True,
        original_dpu_poll_and_submit_exact=True,original_cpu_request_restore_and_psci_exact=True,
        native_gpu_poll_us=50,hardware_tested=False,performance_verified=False,wifi_integrated=False,
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in paths})
    (out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['result','sha256','section_bytes','section_capacity']},indent=2))
