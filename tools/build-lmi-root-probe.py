"""Checkpoint 60: mount a payload RAM disk and acquire its root vnode."""
from pathlib import Path
import hashlib,json,struct,subprocess
root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-checkpoint-59-bsd-probe-test/diagnostic-kernel/mach.development.bcm2837'
b=bytearray(src.read_bytes())
assert hashlib.sha256(b).hexdigest()=='4a6f74d990ba073f120761524b8211395c1c21e0ae915ba59d55eb925b030cd6'
out=root/'out/lmi-kernel-root-probe';out.mkdir(exist_ok=True)
symbols={}
for line in (root/'out/kernel-symbols.txt').read_text().splitlines():
    v=line.split(maxsplit=2)
    if len(v)==3:symbols[v[2]]=int(v[0],16)
base=0xfffffff00745fbe0
asm='''.text
.global _start, root_ready
_start:
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #59
    b.eq old_bsd_probe
    b native_time
root_ready:
    stp x19, x20, [sp, #-48]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    bl native_unlock
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #60
    b.ne done
    adr x0, root_marker
    bl log_line
    adrp x8, root_vnode
    ldr x0, [x8, :lo12:root_vnode]
    bl log_hex
    adr x0, mount_marker
    bl log_line
    adrp x8, mount_list
    ldr x19, [x8, :lo12:mount_list]
    mov x0, x19
    bl log_hex
    adr x0, device_marker
    bl log_line
    adrp x8, root_device
    ldr w0, [x8, :lo12:root_device]
    bl log_hex
    cbz x19, no_mount
    mov x0, x19
    add x1, sp, #32
    stp xzr, xzr, [sp, #32]
    bl vfs_name
    add x19, sp, #32
    adr x0, fs_marker
    bl log_line
    mov x0, x19
    bl log_line
    mov w0, #10
    bl log_char
no_mount:
    adr x0, status
    bl log_line
    adr x19, status
screen_loop:
    ldrb w0, [x19], #1
    cbz w0, screen_done
    bl console_char
    b screen_loop
screen_done:
    mov w0, #60
    bl checkpoint
done:
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #48
    ret
root_marker: .asciz "LMI_ROOT_VNODE\\n"
mount_marker: .asciz "LMI_ROOT_MOUNT\\n"
device_marker: .asciz "LMI_ROOT_DEVICE\\n"
fs_marker: .asciz "LMI_ROOT_FS_NAME\\n"
status: .asciz "\\nHackiOS lmi - checkpoint 60\\nRoot mount returned; root vnode recorded\\nRAM disk only; userspace not started\\n"
.balign 4
'''
(out/'probe.S').write_text(asm)
targets=dict(stub_slot=symbols['_loader_stub_slot']+16,old_bsd_probe=0xfffffff00745f840,native_time=symbols['_inittodr'],
    native_unlock=symbols['_lck_rw_unlock_exclusive'],root_vnode=symbols['_rootvnode'],mount_list=symbols['_mountlist'],root_device=symbols['_rootdev'],
    vfs_name=symbols['_vfs_name'],log_line=symbols['_loader_log_line'],log_char=symbols['_loader_log_putc'],log_hex=0xfffffff00745ebd0,
    console_char=symbols['_console_write_unbuffered'],checkpoint=symbols['_loader_checkpoint'])
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
    m=[fo+va-start for start,vs,fo,fs in regions if start<=va and va+size<=start+fs]
    assert len(m)==1
    return m[0]
def branch(pc,target):
    assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
    return 0x94000000|(((target-pc)//4)&0x3ffffff)
code=(out/'probe.bin').read_bytes();co=offset(base,len(code))
assert base+len(code)<symbols['_LowSecondaryExceptionVectorBase']
assert b[co:co+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
b[co:co+len(code)]=code
patches=[]
for pc,target,new_target in [(0xfffffff0077956a4,0xfffffff00745f840,base),(0xfffffff0077958ec,symbols['_lck_rw_unlock_exclusive'],labels['root_ready'])]:
    off=offset(pc);old=branch(pc,target);new=branch(pc,new_target)
    assert struct.unpack_from('<I',b,off)[0]==old
    struct.pack_into('<I',b,off,new);patches.append(dict(va=hex(pc),old=hex(old),new=hex(new)))
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
report=dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),sha256=hashlib.sha256(b).hexdigest(),patches=patches,thunk_va=hex(base),thunk_bytes=len(code),instrumented_checkpoints=[52,53,54,55,56,57,58,59,60],
    expected_platform_vtable=hex(symbols['__ZTV12GenericARMPE']+16),expected_cpu_vtable=hex(symbols['__ZTV13GenericARMCPU']+16),
    scope='Native RAM-root selection/mount and root vnode acquisition, stop after releasing rootvnode lock, before devfs/peripheral init or first user task.',hardware_tested=False)
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
