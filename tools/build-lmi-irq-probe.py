"""Pinned checkpoint 57: native virtual-timer IRQ service, with bounded wait."""
from pathlib import Path
import hashlib,json,struct,subprocess
root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-checkpoint-56-bootstrap-probe-test/diagnostic-kernel/mach.development.bcm2837'
b=bytearray(src.read_bytes())
assert hashlib.sha256(b).hexdigest()=='555b7dc86baeb5d78ba9e2534977c12a7ded85962ae5a3ece7db9b163653985d'
out=root/'out/lmi-kernel-irq-probe';out.mkdir(exist_ok=True)
symbols={}
for line in (root/'out/kernel-symbols.txt').read_text().splitlines():
    v=line.split(maxsplit=2)
    if len(v)==3:symbols[v[2]]=int(v[0],16)
base=0xfffffff00745eb00
asm='''.text
.global _start, irq_enable
_start:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    bl irq_native
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #57
    b.ne irq_done
    adr x0, serviced
    bl log_line
    bl current_thread
    ldr x8, [x0, #0x1c8]
    ldr x0, [x8, #0x238] // native cpu_stat timer interrupt counter
    bl log_hex
    adr x0, iar_marker
    bl log_line
    adrp x8, active_iar
    ldr x0, [x8, :lo12:active_iar]
    bl log_hex
    adr x0, unhandled_marker
    bl log_line
    adrp x8, unhandled
    ldr x0, [x8, :lo12:unhandled]
    bl log_hex
    mov w0, #57
    bl checkpoint
irq_done:
    ldp x29, x30, [sp], #16
    ret
irq_native:
    sub sp, sp, #64 // displaced original rtclock_intr prologue
    b irq_resume
irq_enable:
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #57
    b.ne enable_tail
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    mrs x19, cntvct_el0
    mrs x20, cntfrq_el0
    lsl x20, x20, #1
    bl native_enable
wait_irq:
    mrs x8, cntvct_el0
    sub x8, x8, x19
    cmp x8, x20
    b.lo wait_irq
    adr x0, timeout
    bl log_line
    mov w0, #57
    bl checkpoint
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    ret
enable_tail:
    b native_enable
log_hex:
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    mov x19, x0
    mov x20, #60
hex_loop:
    lsr x8, x19, x20
    and x8, x8, #15
    adr x9, digits
    ldrb w0, [x9, x8]
    bl log_char
    subs x20, x20, #4
    b.ge hex_loop
    mov w0, #10
    bl log_char
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    ret
serviced: .asciz "LMI_VTIMER_IRQ_SERVICED\\n"
iar_marker: .asciz "LMI_ACTIVE_IRQ_IAR\\n"
unhandled_marker: .asciz "LMI_UNHANDLED_IRQS\\n"
timeout: .asciz "LMI_VTIMER_TIMEOUT\\n"
digits: .ascii "0123456789abcdef"
.balign 4
'''
(out/'probe.S').write_text(asm)
targets=dict(stub_slot=symbols['_loader_stub_slot']+16,irq_resume=symbols['_rtclock_intr']+4,
             native_enable=symbols['_ml_set_interrupts_enabled'],log_line=symbols['_loader_log_line'],log_char=symbols['_loader_log_putc'],
             checkpoint=symbols['_loader_checkpoint'],current_thread=symbols['_current_thread'],active_iar=symbols['_gic_active_iar'],unhandled=symbols['_gic_unhandled_count'])
subprocess.run(['clang','--target=aarch64-none-elf','-c',str(out/'probe.S'),'-o',str(out/'probe.o')],check=True)
subprocess.run(['ld.lld',f'-Ttext={base:#x}','--entry=_start',*[f'--defsym={k}={v:#x}' for k,v in targets.items()],str(out/'probe.o'),'-o',str(out/'probe.elf')],check=True)
subprocess.run(['llvm-objcopy','-O','binary',str(out/'probe.elf'),str(out/'probe.bin')],check=True)
labels={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm','--defined-only',str(out/'probe.elf')],text=True).splitlines() if len(v:=line.split())==3}
regions=[];pos=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,size=struct.unpack_from('<II',b,pos)
    if cmd==0x19:regions.append(struct.unpack_from('<QQQQ',b,pos+24))
    pos+=size
def offset(va,size=4):
    matches=[fo+va-start for start,vs,fo,fs in regions if start<=va and va+size<=start+fs]
    assert len(matches)==1
    return matches[0]
def branch(pc,target,link=False):
    assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
    return (0x94000000 if link else 0x14000000)|(((target-pc)//4)&0x3ffffff)
code=(out/'probe.bin').read_bytes();co=offset(base,len(code))
assert b[co:co+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
b[co:co+len(code)]=code
patches=[]
for pc,old,new in [(symbols['_rtclock_intr'],0xd10103ff,branch(symbols['_rtclock_intr'],base)),
                   (0xfffffff00731303c,branch(0xfffffff00731303c,symbols['_ml_set_interrupts_enabled'],True),branch(0xfffffff00731303c,labels['irq_enable'],True))]:
    off=offset(pc);assert struct.unpack_from('<I',b,off)[0]==old
    struct.pack_into('<I',b,off,new);patches.append(dict(va=hex(pc),old=hex(old),new=hex(new)))
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
report=dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),sha256=hashlib.sha256(b).hexdigest(),patches=patches,thunk_va=hex(base),thunk_bytes=len(code),instrumented_checkpoints=[52,53,54,55,56,57],
    scope='Native rtclock_intr retained; checkpoint 57 returns after a serviced GIC timer IRQ or a bounded 2-second timeout. No progress beyond the IRQ-enable site in this stage.',hardware_tested=False)
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
