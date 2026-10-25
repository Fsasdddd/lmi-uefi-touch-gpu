"""Pinned XNU: observable, bounded kernel bootstrap. Run with Linux LLVM tools."""
from pathlib import Path
import hashlib,json,struct,subprocess
root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-kernel-preirq-probe/mach.development.bcm2837'
b=bytearray(src.read_bytes())
assert hashlib.sha256(b).hexdigest()=='4f748498967135ce8ea12d428391c6703b42926581b15b356f6203bf4fc90f35'
out=root/'out/lmi-kernel-bootstrap-probe';out.mkdir(exist_ok=True)
symbols={}
for line in (root/'out/kernel-symbols.txt').read_text().splitlines():
    parts=line.split(maxsplit=2)
    if len(parts)==3:symbols[parts[2]]=int(parts[0],16)
base=0xfffffff00745e700
asm='''.text
.global _start, vm_done, oslog_done, thread_created, thread_entered, iokit_done
_start:
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    mov x19, x0
    mov x20, x0
trace_loop:
    sub x8, x19, x20
    cmp x8, #32
    b.hs trace_done
    ldrb w0, [x19], #1
    cbz w0, trace_done
    bl log_char
    b trace_loop
trace_done:
    mov w0, #10
    bl log_char
    mov x0, x20
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    sub sp, sp, #64 // displaced original prologue; preserve native trace too
    b debug_resume
vm_done:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    bl vm_bootstrap
    mov w0, #52
    bl checkpoint
    ldp x29, x30, [sp], #16
    ret
oslog_done:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    bl startup_upto
    mov w0, #53
    bl checkpoint
    ldp x29, x30, [sp], #16
    ret
thread_created:
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    mov x19, x0
    adr x0, created_marker
    bl log_line
    mov x0, x19
    bl log_hex
    mov w0, #54
    bl checkpoint
    mov x0, x19
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    b load_context
thread_entered:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    adr x0, entered_marker
    bl log_line
    mrs x0, tpidr_el1
    bl log_hex
    adr x0, stack_marker
    bl log_line
    add x0, sp, #16
    bl log_hex
    mov w0, #55
    bl checkpoint
    ldp x29, x30, [sp], #16
    sub sp, sp, #80 // displaced native bootstrap-thread prologue
    b thread_resume
iokit_done:
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    bl iokit_init
    adr x0, iokit_marker
    bl log_line
    adrp x8, root_nub
    ldr x0, [x8, :lo12:root_nub]
    bl log_hex
    adr x0, free_marker
    bl log_line
    adrp x8, free_pages
    ldr w0, [x8, :lo12:free_pages]
    bl log_hex
    mov x0, xzr
    mov w1, #4
    bl pe_console
    adr x0, screen_message
    bl log_line
    adr x19, screen_message
screen_loop:
    ldrb w0, [x19], #1
    cbz w0, screen_done
    bl console_char
    b screen_loop
screen_done:
    mov w0, #56
    bl checkpoint
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    ret
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
created_marker: .asciz "LMI_BOOTSTRAP_THREAD_CREATED\\n"
entered_marker: .asciz "LMI_BOOTSTRAP_THREAD_ENTERED\\n"
stack_marker: .asciz "LMI_BOOTSTRAP_THREAD_STACK\\n"
iokit_marker: .asciz "LMI_IOKIT_ROOT_NUB\\n"
free_marker: .asciz "LMI_VM_FREE_PAGES\\n"
screen_message: .asciz "HackiOS lmi kernel bring-up\\nVM + kernel heap: initialized\\nMach IPC + bootstrap thread: initialized\\nIOKit core: initialized\\nCheckpoint 56 - RAM-only test\\niOS userspace has not started\\n"
digits: .ascii "0123456789abcdef"
.balign 4
'''
(out/'probe.S').write_text(asm)
targets=dict(log_char=symbols['_loader_log_putc'],log_line=symbols['_loader_log_line'],debug_resume=symbols['_kernel_debug_string_early']+4,
             vm_bootstrap=symbols['_vm_mem_bootstrap'],checkpoint=symbols['_loader_checkpoint'],startup_upto=symbols['_kernel_startup_initialize_upto'],
             load_context=symbols['_load_context'],thread_resume=symbols['_kernel_bootstrap_thread']+4,
             iokit_init=symbols['_PE_init_iokit'],root_nub=symbols['_gRootNub'],free_pages=symbols['_vm_page_free_count'],
             pe_console=symbols['_PE_initialize_console'],console_char=symbols['_console_write_unbuffered'])
subprocess.run(['clang','--target=aarch64-none-elf','-c',str(out/'probe.S'),'-o',str(out/'probe.o')],check=True)
subprocess.run(['ld.lld',f'-Ttext={base:#x}','--entry=_start',*[f'--defsym={k}={v:#x}' for k,v in targets.items()],str(out/'probe.o'),'-o',str(out/'probe.elf')],check=True)
subprocess.run(['llvm-objcopy','-O','binary',str(out/'probe.elf'),str(out/'probe.bin')],check=True)
labels={}
for line in subprocess.check_output(['llvm-nm','--defined-only',str(out/'probe.elf')],text=True).splitlines():
    fields=line.split()
    if len(fields)==3:labels[fields[2]]=int(fields[0],16)
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
code=(out/'probe.bin').read_bytes()
co=offset(base,len(code))
assert b[co:co+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
b[co:co+len(code)]=code
patches=[]
for pc,old,new in [(symbols['_kernel_debug_string_early'],0xd10103ff,branch(symbols['_kernel_debug_string_early'],base)),
                   (0xfffffff007312558,branch(0xfffffff007312558,symbols['_vm_mem_bootstrap'],True),branch(0xfffffff007312558,labels['vm_done'],True)),
                   (0xfffffff0073125e0,branch(0xfffffff0073125e0,symbols['_kernel_startup_initialize_upto'],True),branch(0xfffffff0073125e0,labels['oslog_done'],True)),
                   (0xfffffff007312c00,branch(0xfffffff007312c00,symbols['_load_context'],True),branch(0xfffffff007312c00,labels['thread_created'],True)),
                   (symbols['_kernel_bootstrap_thread'],0xd10143ff,branch(symbols['_kernel_bootstrap_thread'],labels['thread_entered'])),
                   (0xfffffff007313024,branch(0xfffffff007313024,symbols['_PE_init_iokit'],True),branch(0xfffffff007313024,labels['iokit_done'],True))]:
    off=offset(pc)
    assert struct.unpack_from('<I',b,off)[0]==old
    struct.pack_into('<I',b,off,new)
    patches.append(dict(va=hex(pc),old=hex(old),new=hex(new)))
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
report=dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),sha256=hashlib.sha256(b).hexdigest(),patches=patches,instrumented_checkpoints=[52,53,54,55,56],
    thunk_va=hex(base),thunk_bytes=len(code),scope='Native traces copied into RAM; checkpoints 52 VM, 53 OSLOG, 54 thread created, 55 bootstrap-thread entry, 56 IOKit core/root nub and native console status. No original call skipped; stops before IRQ enable.',hardware_tested=False)
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
