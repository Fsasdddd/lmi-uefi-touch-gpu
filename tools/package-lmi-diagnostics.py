"""Package a temporary lmi diagnostic boot image; never accesses the phone.

Uses AOSP mkbootimg, the captured boot image's v2 layout and original DTB set.
There is no ramdisk, XNU payload, partition logging or payload-copy code.
"""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import argparse

parser=argparse.ArgumentParser()
parser.add_argument('--usb-probe',action='store_true')
parser.add_argument('--full-loader',action='store_true')
args=parser.parse_args()

root = Path(__file__).resolve().parents[1]
mu = Path.home() / 'hackios-lmi/mu-silicium'
out = root / ('out/lmi-loader-test' if args.full_loader else 'out/lmi-usb-test' if args.usb_probe else 'out/lmi-diagnostics')
out.mkdir(parents=True, exist_ok=True)
boot = (root/'device-info/boot.img').read_bytes()
assert boot[:8] == b'ANDROID!'
kernel_size,kernel_addr,ramdisk_size,ramdisk_addr,second_size,second_addr,tags,page,version,os = struct.unpack_from('<10I',boot,8)
assert version==2 and page==4096 and second_size==0
assert struct.unpack_from('<I',boot,1632)[0]==0
header_size,dtb_size,dtb_addr=struct.unpack_from('<IIQ',boot,1644)
assert header_size==1660
align=lambda n:(n+page-1)//page*page
dtb_offset=page+align(kernel_size)+align(ramdisk_size)
dtbs=boot[dtb_offset:dtb_offset+dtb_size]
assert len(dtbs)==dtb_size and dtb_size>0
trees=[]
cursor=0
while cursor<len(dtbs):
    assert dtbs[cursor:cursor+4]==b'\xd0\x0d\xfe\xed',hex(cursor)
    size=struct.unpack_from('>I',dtbs,cursor+4)[0]
    assert size>=40 and cursor+size<=len(dtbs)
    trees.append(dict(offset=cursor,bytes=size,sha256=hashlib.sha256(dtbs[cursor:cursor+size]).hexdigest()))
    cursor+=size
(out/'original-dtb-set.bin').write_bytes(dtbs)

fd_folder=root/('out/lmi-uefi-loader-test' if args.full_loader else 'out/lmi-uefi-usb-test' if args.usb_probe else 'out/lmi-uefi-patched')
manifest=json.loads((fd_folder/'manifest.json').read_text())
fd=(fd_folder/'SILICIUM_UEFI.fd').read_bytes()
assert len(fd)==0x300000 and hashlib.sha256(fd).hexdigest()==manifest['fd_sha256']
# Build the shim without PAYLOAD_BASE; its payload-copy branch is compiled out.
subprocess.run(['clang','--target=aarch64-linux-gnu','-c',str(mu/'BootShim/BootShim.S'),
    '-o',str(out/'BootShim.elf'),'-DREQUIRES_KERNEL_HEADER=1','-DFD_BASE=0x9fc00000','-DFD_SIZE=0x300000'],check=True)
subprocess.run(['llvm-objcopy','-O','binary',str(out/'BootShim.elf'),str(out/'BootShim.bin')],check=True)
symbols=subprocess.check_output(['llvm-nm','--defined-only',str(out/'BootShim.elf')],text=True)
assert '_PayloadLoop' not in symbols and '_NoPayload' not in symbols
payload_symbol=next(line for line in symbols.splitlines() if line.endswith(' _Payload'))
shim=(out/'BootShim.bin').read_bytes()
assert int(payload_symbol.split()[0],16)==len(shim)
assert shim[56:60]==b'ARM\x64' and struct.unpack_from('<QQ',shim,8)==(0x9fc00000,0x300000)
(out/'kernel.bin').write_bytes(shim+fd)
(out/'BootShim.disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-dr',str(out/'BootShim.elf')]))
cmdline=(boot[64:576].split(b'\0')[0]+boot[608:1632].split(b'\0')[0]).decode('ascii')
board=boot[48:64].split(b'\0')[0].decode('ascii')
ver=os>>11
patch=os&0x7ff
os_version=f'{(ver>>14)&127}.{(ver>>7)&127}.{ver&127}'
patch_level=f'{2000+(patch>>4):04d}-{patch&15:02d}'
image=out/'lmi-diagnostics.img'
command=[sys.executable,str(mu/'Resources/Scripts/mkbootimg.py'),
    '--header_version','2','--pagesize',str(page),'--base','0',
    '--kernel_offset',hex(kernel_addr),'--ramdisk_offset',hex(ramdisk_addr),
    '--tags_offset',hex(tags),'--dtb_offset',hex(dtb_addr),
    '--os_version',os_version,'--os_patch_level',patch_level,
    '--board',board,'--cmdline',cmdline,'--kernel',str(out/'kernel.bin'),
    '--dtb',str(out/'original-dtb-set.bin'),'--output',str(image)]
subprocess.run(command,check=True)
b=image.read_bytes()
ks=struct.unpack_from('<I',b,8)[0]
assert b[:8]==b'ANDROID!' and struct.unpack_from('<I',b,40)[0]==2
assert struct.unpack_from('<I',b,16)[0]==0
assert ks==len(shim)+len(fd) and b[page:page+ks]==shim+fd
assert struct.unpack_from('<I',b,1648)[0]==len(dtbs)
assert b[page+align(ks):page+align(ks)+len(dtbs)]==dtbs
assert len(b)<len(boot)
report=dict(image=str(image),bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),
    header_version=2,page_size=page,shim_bytes=len(shim),uefi_fd_sha256=manifest['fd_sha256'],
    dtb_set_sha256=hashlib.sha256(dtbs).hexdigest(),dtbs=trees,
    ramdisk=False,xnu_payload=False,payload_copy_code=False,raw_log_partition_writes=False,
    intended_use='temporary fastboot boot for guarded lmi bring-up',
    usb_transport_probe=args.usb_probe,
    full_source_loader=args.full_loader,
    hardware_tested=False,bootloader_relocation_measured=False,
    validated='Container offsets, ARM64 shim header/symbol position, FD hash and original DTB set preservation')
if args.full_loader:
    profile=json.loads((root/'out/lmi-loader/manifest.json').read_text())
    report['loader_sha256']=profile['sha256']
    report['kernel_execution_enabled']=profile['kernel_execution_enabled']
    report['permitted_checkpoints']=profile['permitted_checkpoints']
    report['kernel_memory_floor']=profile.get('kernel_memory_floor','0x0')
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
