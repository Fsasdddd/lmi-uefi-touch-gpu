"""Build a host-only Thumb ELF from pinned lmi GMU payloads for inspection.

No firmware is executed or transferred. Data pools also appear in the raw
disassembly; callers must resolve control flow before interpreting them as code.
"""
from pathlib import Path
import struct,hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-gpu-research/firmware-static';out.mkdir(exist_ok=True)
fw=(root/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes();assert hashlib.sha256(fw).hexdigest()=='df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c'
pos=0;asm=['.syntax unified','.cpu cortex-m3','.thumb'];ld=['SECTIONS {'];records=[]
while pos<len(fw):
 addr,size,typ,value=struct.unpack_from('<4I',fw,pos);pos+=16
 assert size<=len(fw)-pos
 if size:
  name=f'block_{addr:x}';p=out/(name+'.bin');p.write_bytes(fw[pos:pos+size])
  flags='aw' if addr>=0x10000000 else 'ax'
  asm += [f'.section .{name},"{flags}",%progbits',f'.incbin "{p}"']
  ld += [f'.{name} {addr:#x} : {{ *(.{name}) }}']
  values=[]
  for off in range(0,size-3,4):
   v=struct.unpack_from('<I',fw,pos+off)[0]
   if v==0x10108 or (0x44000000<=v<0x45000000):values.append({'at':hex(addr+off),'value':hex(v)})
  records.append({'address':hex(addr),'size':size,'aligned_word_candidates':values})
 pos+=size
ld+=['/DISCARD/ : { *(.ARM.attributes) *(.comment) }','}']
(out/'gmu.S').write_text('\n'.join(asm));(out/'gmu.ld').write_text('\n'.join(ld))
subprocess.run(['clang','--target=thumbv7m-none-eabi','-c',str(out/'gmu.S'),'-o',str(out/'gmu.o')],check=True)
subprocess.run(['ld.lld','-T',str(out/'gmu.ld'),str(out/'gmu.o'),'-o',str(out/'gmu.elf')],check=True)
(out/'gmu-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d','--triple=thumbv7m-none-eabi',str(out/'gmu.elf')]))
(out/'literals.json').write_text(json.dumps(records,indent=2))
cache=(out/'block_4000.bin').read_bytes()
# These pools have inspected PC-relative loads and reachable call/branch
# paths. Other word candidates above may simply be instructions or strings.
anchors={0x6ff0:0x10108,0x6ff4:0x440e0000,0x88cc:0x01010000,
         0x88e4:0x440e0fbc,0x88e8:0x440e0fb4,0x8968:0x440e0fd8,
         0x896c:0x440e1518,0x94c4:0x440e0fd4,0x94c8:0x440e1514}
for address,value in anchors.items():
 assert struct.unpack_from('<I',cache,address-0x4000)[0]==value
(out/'arc-slot-evidence.json').write_text(json.dumps(dict(
 firmware_sha256=hashlib.sha256(fw).hexdigest(),static_only=True,
 execution_verified=False,literals={hex(a):hex(v) for a,v in anchors.items()},
 slot1_command0_address_offset='0xfd4',slot1_control_offset='0xfb4',
 slot1_irq_mask='0x2',slot0_role='firmware bandwidth table path',
 slot1_role='firmware active ARC path',
 does_not_prove='slot0 cannot access ARC or slot1 request completion'),indent=2))
print(json.dumps(records,indent=2))
