"""Checkpoint 61: PID 1 reaches SYS_exit from a saved EL0 SVC64 context."""
from pathlib import Path
import hashlib,json,struct,subprocess
root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-checkpoint-60-root-probe-test-fsnamefix/diagnostic-kernel/mach.development.bcm2837'
b=bytearray(src.read_bytes())
assert hashlib.sha256(b).hexdigest()=='429c6915b776bf70d3e3283f5553c12b718427f83efd4eb2d0071d372045f34f'
out=root/'out/lmi-kernel-user-probe';out.mkdir(exist_ok=True)
symbols={}
for line in (root/'out/kernel-symbols.txt').read_text().splitlines():
    v=line.split(maxsplit=2)
    if len(v)==3:symbols[v[2]]=int(v[0],16)
# The secondary vectors and their terminal WFI loop end below +0x800.
# Preserve the complete vector area; use only checked alignment padding.
base=0xfffffff007460840
asm='''.text
.global _start
_start:
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #61
    b.ne original
    stp x19, x20, [sp, #-64]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    stp x0, x1, [sp, #32]
    str x2, [sp, #48]
    bl proc_pid
    mov x19, x0
    cmp w19, #1
    b.ne restore
    adr x0, pid_marker
    bl log_line
    mov x0, x19
    bl log_hex
    bl current_thread
    bl user_regs
    mov x19, x0
    cbz x19, stop
'''
fields=[('flavor',0,'w','LMI_EL0_STATE_FLAVOR'),('pc',0x108,'x','LMI_EL0_PC'),('pstate',0x110,'w','LMI_EL0_PSTATE'),
        ('esr',0x120,'w','LMI_EL0_ESR'),('syscall',0x88,'x','LMI_EL0_X16')]
for label,offset,width,marker in fields:
    asm+=f'''    adr x0, {label}_marker
    bl log_line
    ldr {width}0, [x19, #{offset}]
    bl log_hex
'''
asm+='''stop:
    adr x0, status
    bl log_line
    adr x20, status
screen_loop:
    ldrb w0, [x20], #1
    cbz w0, screen_done
    bl console_char
    b screen_loop
screen_done:
    mov w0, #61
    bl checkpoint
restore:
    ldp x0, x1, [sp, #32]
    ldr x2, [sp, #48]
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #64
original:
    stp x29, x30, [sp, #-16]! // displaced native exit prologue
    b exit_resume
pid_marker: .asciz "LMI_EL0_PID\\n"
'''
for label,offset,width,marker in fields:asm+=f'{label}_marker: .asciz "{marker}\\n"\n'
asm+='status: .asciz "\\nHackiOS lmi - checkpoint 61\\nPID 1 SYS_exit intercepted; saved EL0 state in log\\nStatic Darwin test; full iOS not started\\nRAM-only test; Android retained\\n"\n.balign 4\n'
(out/'probe.S').write_text(asm)
targets=dict(stub_slot=symbols['_loader_stub_slot']+16,proc_pid=symbols['_proc_pid'],current_thread=symbols['_current_thread'],user_regs=symbols['_get_user_regs'],
    log_line=symbols['_loader_log_line'],log_hex=0xfffffff00745ebd0,console_char=symbols['_console_write_unbuffered'],checkpoint=symbols['_loader_checkpoint'],exit_resume=symbols['_exit']+4)
subprocess.run(['clang','--target=aarch64-none-elf','-c',str(out/'probe.S'),'-o',str(out/'probe.o')],check=True)
subprocess.run(['ld.lld',f'-Ttext={base:#x}','--entry=_start',*[f'--defsym={k}={v:#x}' for k,v in targets.items()],str(out/'probe.o'),'-o',str(out/'probe.elf')],check=True)
subprocess.run(['llvm-objcopy','-O','binary',str(out/'probe.elf'),str(out/'probe.bin')],check=True)
regions=[];pos=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,size=struct.unpack_from('<II',b,pos)
    if cmd==0x19:regions.append(struct.unpack_from('<QQQQ',b,pos+24))
    pos+=size
def offset(va,size=4):
    m=[fo+va-start for start,vs,fo,fs in regions if start<=va and va+size<=start+fs]
    assert len(m)==1
    return m[0]
code=(out/'probe.bin').read_bytes();co=offset(base,len(code))
assert base>=symbols['_LowSecondaryExceptionVectorBase']+0x800 and base+len(code)<symbols['_resume_idle_cpu']
assert b[co:co+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
b[co:co+len(code)]=code
pc=symbols['_exit'];off=offset(pc);old=0xa9bf7bfd
assert struct.unpack_from('<I',b,off)[0]==old
assert (base-pc)%4==0 and -(1<<27)<=base-pc<(1<<27)
new=0x14000000|(((base-pc)//4)&0x3ffffff);struct.pack_into('<I',b,off,new)
# Enable the upstream fatal user-exception trace by default in this derived
# diagnostic only. No boot-arg/peripheral settings or fault handling change.
trace_va=symbols['_user_exception_trace_enabled'];trace_off=offset(trace_va)
assert struct.unpack_from('<I',b,trace_off)[0]==0
struct.pack_into('<I',b,trace_off,1)
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
report=dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),sha256=hashlib.sha256(b).hexdigest(),patches=[dict(va=hex(pc),old=hex(old),new=hex(new)),dict(va=hex(trace_va),old=0,new=1,purpose='Enable upstream fatal-user trace')],
    thunk_va=hex(base),thunk_bytes=len(code),instrumented_checkpoints=[52,53,54,55,56,57,58,59,60,61],
    expected_platform_vtable=hex(symbols['__ZTV12GenericARMPE']+16),expected_cpu_vtable=hex(symbols['__ZTV13GenericARMCPU']+16),
    scope='Allow native devfs, inert peripheral initializers, first user task and executable load. At PID1 SYS_exit sample actual arm_saved_state before exit teardown. This is a static Darwin milestone, not Apple iOS userspace.',hardware_tested=False)
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
