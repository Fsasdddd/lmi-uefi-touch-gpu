"""Pinned checkpoint 59: BSD process/VFS/network initialization before root selection."""
from pathlib import Path
import hashlib,json,struct,subprocess
root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-checkpoint-58-driver-probe-test/diagnostic-kernel/mach.development.bcm2837'
b=bytearray(src.read_bytes())
assert hashlib.sha256(b).hexdigest()=='c6da0734104d5e30d309b455b4c55e381dc2d42cec78231622a009c5488dfded'
out=root/'out/lmi-kernel-bsd-probe';out.mkdir(exist_ok=True)
symbols={}
for line in (root/'out/kernel-symbols.txt').read_text().splitlines():
    v=line.split(maxsplit=2)
    if len(v)==3:symbols[v[2]]=int(v[0],16)
# Use padding AFTER the low exception table and its 32-byte loader slot.
# The 0x45f000..0x45f800 range is live exception-vector code, never probe space.
base=0xfffffff00745f840
targets=dict(log_line=symbols['_loader_log_line'],log_hex=0xfffffff00745ebd0,
    checkpoint=symbols['_loader_checkpoint'],current_proc=symbols['_current_proc_EXTERNAL'],proc_pid=symbols['_proc_pid'],
    console_char=symbols['_console_write_unbuffered'],native_time=symbols['_inittodr'])
asm='''.text
.global _start
_start:
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    bl native_time
    adr x0, boundary
    bl log_line
    bl current_proc
    mov x19, x0
    adr x0, current_marker
    bl log_line
    mov x0, x19
    bl log_hex
    cbz x19, proc_null
    mov x0, x19
    bl proc_pid
    b pid_ready
proc_null:
    mov x0, #-1
pid_ready:
    mov x19, x0
    adr x0, pid_marker
    bl log_line
    mov x0, x19
    bl log_hex
'''
samples=[('kernproc','_kernproc','x','LMI_BSD_KERNPROC'),('bsd_map','_bsd_pageable_map','x','LMI_BSD_PAGEABLE_MAP'),
    ('vfs_ops','_vfs_opv_numops','w','LMI_BSD_VFS_OPS'),('loopback','_lo_ifp','x','LMI_BSD_LOOPBACK'),
    ('root_vnode','_rootvnode','x','LMI_BSD_ROOT_VNODE'),('mount_list','_mountlist','x','LMI_BSD_FIRST_MOUNT')]
for label,sym,width,marker in samples:
    targets[label]=symbols[sym]
    asm+=f'''    adr x0, {label}_marker
    bl log_line
    adrp x8, {label}
    ldr {width}0, [x8, :lo12:{label}]
    bl log_hex
'''
asm+='''    adr x0, status
    bl log_line
    adr x19, status
screen_loop:
    ldrb w0, [x19], #1
    cbz w0, screen_done
    bl console_char
    b screen_loop
screen_done:
    mov w0, #59
    bl checkpoint
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    ret
'''
# Trace each completed native subsystem, preserving its return value.
hooks=[('buffer',0xfffffff0077954c4,'_bsd_bufferinit','LMI_BSD_BUFFER_INIT_RETURNED'),
    ('vfs',0xfffffff0077954e4,'_vfsinit','LMI_BSD_VFS_INIT_RETURNED'),
    ('iobsd',0xfffffff00779563c,'_IOKitBSDInit','LMI_BSD_IOKIT_INIT_RETURNED'),
    ('network',0xfffffff007795690,'_net_init_run','LMI_BSD_NETWORK_INIT_RETURNED')]
for label,pc,sym,marker in hooks:
    targets['native_'+label]=symbols[sym]
    asm+=f'''{label}_done:
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    bl native_{label}
    mov x19, x0
    adr x0, {label}_marker
    bl log_line
    mov x0, x19
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    ret
'''
asm+='boundary: .asciz "LMI_BSD_BEFORE_ROOT_SELECTION\\n"\ncurrent_marker: .asciz "LMI_BSD_CURRENT_PROC\\n"\npid_marker: .asciz "LMI_BSD_PID\\n"\n'
for label,sym,width,marker in samples:asm+=f'{label}_marker: .asciz "{marker}\\n"\n'
for label,pc,sym,marker in hooks:asm+=f'{label}_marker: .asciz "{marker}\\n"\n'
asm+='status: .asciz "\\nHackiOS lmi - checkpoint 59\\nNative BSD process / VFS / network init returned\\nStopped BEFORE root selection or mount\\niOS userspace has not started\\nRAM-only test; Android retained\\n"\n.balign 4\n'
(out/'probe.S').write_text(asm)
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
def branch(pc,target):
    assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
    return 0x94000000|(((target-pc)//4)&0x3ffffff)
code=(out/'probe.bin').read_bytes();co=offset(base,len(code))
assert base>=symbols['_loader_stub_slot']+32
assert base+len(code)<symbols['_LowSecondaryExceptionVectorBase']
assert b[co:co+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
b[co:co+len(code)]=code
patches=[]
for label,pc,sym,marker in [*hooks,('_start',0xfffffff0077956a4,'_inittodr','')]:
    old=branch(pc,symbols[sym]);new=branch(pc,labels[label+'_done'] if label!='_start' else base)
    off=offset(pc);assert struct.unpack_from('<I',b,off)[0]==old
    struct.pack_into('<I',b,off,new);patches.append(dict(va=hex(pc),old=hex(old),new=hex(new)))
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
report=dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),sha256=hashlib.sha256(b).hexdigest(),patches=patches,
    thunk_va=hex(base),thunk_bytes=len(code),instrumented_checkpoints=[52,53,54,55,56,57,58,59],
    expected_platform_vtable=hex(symbols['__ZTV12GenericARMPE']+16),expected_cpu_vtable=hex(symbols['__ZTV13GenericARMCPU']+16),
    scope='Native BSD setup through inittodr. Retain buffer/VFS/IOBSD/network calls and record return. Stop before inlined setconf/IOFindBSDRoot; no root selection/mount or userspace.',hardware_tested=False)
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
