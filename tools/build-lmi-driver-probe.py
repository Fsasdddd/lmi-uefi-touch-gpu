"""Pinned checkpoint 58: normal IRQ return and IOKit matching, before BSD init."""
from pathlib import Path
import hashlib,json,struct,subprocess
root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-checkpoint-57-irq-probe-test/diagnostic-kernel/mach.development.bcm2837'
b=bytearray(src.read_bytes())
assert hashlib.sha256(b).hexdigest()=='387fb03617cebcd6c9987c3679c732580b8ab8e0e67b2562b96cf02bad6cfb1e'
out=root/'out/lmi-kernel-driver-probe';out.mkdir(exist_ok=True)
symbols={}
for line in (root/'out/kernel-symbols.txt').read_text().splitlines():
    v=line.split(maxsplit=2)
    if len(v)==3:symbols[v[2]]=int(v[0],16)
base=0xfffffff00745ed00
asm='''.text
.global _start
_start:
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #58
    b.ne native_tail
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    adr x0, boundary
    bl log_line
    mrs x19, cntvct_el0
    mrs x20, cntfrq_el0
    lsl x20, x20, #1
wait_tick:
    bl current_thread
    ldr x8, [x0, #0x1c8]
    ldr x0, [x8, #0x238]
    cbnz x0, tick_done
    mrs x8, cntvct_el0
    sub x8, x8, x19
    cmp x8, x20
    b.lo wait_tick
tick_done:
    mov x19, x0
    adr x0, tick_marker
    bl log_line
    mov x0, x19
    bl log_hex
    adr x0, iar_marker
    bl log_line
    adrp x8, active_iar
    ldr x0, [x8, :lo12:active_iar]
    bl log_hex
    adr x0, unknown_marker
    bl log_line
    adrp x8, unhandled
    ldr x0, [x8, :lo12:unhandled]
    bl log_hex
    bl get_platform
    mov x19, x0
    adr x0, platform_marker
    bl log_line
    mov x0, x19
    bl log_hex
    mov x0, xzr
    cbz x19, platform_null
    ldr x0, [x19]
platform_null:
    mov x19, x0
    adr x0, platform_vtable_marker
    bl log_line
    mov x0, x19
    bl log_hex
    adrp x8, cpu_array
    ldr x19, [x8, :lo12:cpu_array]
    adr x0, cpu_marker
    bl log_line
    mov x0, x19
    bl log_hex
    mov x0, xzr
    cbz x19, cpu_null
    ldr x0, [x19]
cpu_null:
    mov x19, x0
    adr x0, cpu_vtable_marker
    bl log_line
    mov x0, x19
    bl log_hex
    adr x0, processor_marker
    bl log_line
    adrp x8, processors
    ldr w0, [x8, :lo12:processors]
    bl log_hex
    adr x0, status
    bl log_line
    adr x19, status
screen_loop:
    ldrb w0, [x19], #1
    cbz w0, screen_done
    bl console_char
    b screen_loop
screen_done:
    mov w0, #58
    bl checkpoint
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
native_tail:
    b native_bsd
boundary: .asciz "LMI_BSD_INIT_BOUNDARY\\n"
tick_marker: .asciz "LMI_NORMAL_IRQ_TIMER_COUNT\\n"
iar_marker: .asciz "LMI_THREAD_CONTEXT_IAR\\n"
unknown_marker: .asciz "LMI_THREAD_CONTEXT_UNHANDLED\\n"
platform_marker: .asciz "LMI_PLATFORM_OBJECT\\n"
platform_vtable_marker: .asciz "LMI_PLATFORM_VTABLE\\n"
cpu_marker: .asciz "LMI_CPU_OBJECT\\n"
cpu_vtable_marker: .asciz "LMI_CPU_VTABLE\\n"
processor_marker: .asciz "LMI_PROCESSOR_COUNT\\n"
status: .asciz "\\nHackiOS lmi - checkpoint 58\\nIOKit matching returned; BSD init boundary\\nIRQ and driver objects recorded in RAM log\\niOS userspace has not started\\nRAM-only test; Android retained\\n"
.balign 4
'''
(out/'probe.S').write_text(asm)
targets=dict(stub_slot=symbols['_loader_stub_slot']+16,native_bsd=symbols['_bsd_init'],
    current_thread=symbols['_current_thread'],active_iar=symbols['_gic_active_iar'],unhandled=symbols['_gic_unhandled_count'],
    log_line=symbols['_loader_log_line'],log_hex=0xfffffff00745ebd0,
    get_platform=symbols['__ZN9IOService11getPlatformEv'],cpu_array=symbols['__ZZN12GenericARMPE5startEP9IOServiceE4cpus'],
    processors=symbols['_processor_avail_count'],console_char=symbols['_console_write_unbuffered'],checkpoint=symbols['_loader_checkpoint'])
subprocess.run(['clang','--target=aarch64-none-elf','-c',str(out/'probe.S'),'-o',str(out/'probe.o')],check=True)
subprocess.run(['ld.lld',f'-Ttext={base:#x}','--entry=_start',*[f'--defsym={k}={v:#x}' for k,v in targets.items()],str(out/'probe.o'),'-o',str(out/'probe.elf')],check=True)
subprocess.run(['llvm-objcopy','-O','binary',str(out/'probe.elf'),str(out/'probe.bin')],check=True)
regions=[];pos=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,size=struct.unpack_from('<II',b,pos)
    if cmd==0x19:regions.append(struct.unpack_from('<QQQQ',b,pos+24))
    pos+=size
def offset(va,size=4):
    matches=[fo+va-start for start,vs,fo,fs in regions if start<=va and va+size<=start+fs]
    assert len(matches)==1
    return matches[0]
def branch(pc,target):
    assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
    return 0x94000000|(((target-pc)//4)&0x3ffffff)
code=(out/'probe.bin').read_bytes();co=offset(base,len(code))
assert base+len(code)<symbols['_loader_stub_slot']
assert b[co:co+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
b[co:co+len(code)]=code
pc=0xfffffff00731325c;off=offset(pc);old=branch(pc,symbols['_bsd_init']);new=branch(pc,base)
assert struct.unpack_from('<I',b,off)[0]==old
struct.pack_into('<I',b,off,new)
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
report=dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),sha256=hashlib.sha256(b).hexdigest(),
    patches=[dict(va=hex(pc),old=hex(old),new=hex(new))],thunk_va=hex(base),thunk_bytes=len(code),instrumented_checkpoints=[52,53,54,55,56,57,58],
    expected_platform_vtable=hex(symbols['__ZTV12GenericARMPE']+16),expected_cpu_vtable=hex(symbols['__ZTV13GenericARMCPU']+16),
    scope='Native IRQ return and IOKit matching retained. Stop before bsd_init; sample live platform/CPU objects and a bounded normal timer IRQ. No root mount or userspace.',hardware_tested=False)
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
