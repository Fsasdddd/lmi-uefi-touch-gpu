"""Compile-proven stock speed-bin GPU request, with the complete v56 display.

Host only. Only the frequency-index MOV instruction may differ from v56f.
The original GMU ACK, voltage table, faults, OOB and RAM-run return remain.
"""
from pathlib import Path
import hashlib,json,re,struct,subprocess,runpy
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-display-probe-v57b';assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=root/'out/lmi-display-probe-v56f/mach.development.bcm2837'
assert sha(base)=='c5e262e6f0843ea78e9d5549f48c57f0165e11c454acaf19d9d6dc55abefb1b3'
assert sha(root/'tools/lmi-gpu-gx.c')=='4403c4c3711ce0f47972bddd633a75affb37b94130895ba718bbf1b414528adb'
assert sha(root/'tools/lmi-gpu-table-plan.c')=='1ecb66b621db485201d0f9e1dd33f615460a1c3b31923e6f12f66bc724081b6c'

def elf(path):
    raw=path.read_bytes();assert raw[:6]==b'\x7fELF\x02\x01'
    off=struct.unpack_from('<Q',raw,40)[0]
    size,count,names=struct.unpack_from('<HHH',raw,58)
    headers=[struct.unpack_from('<IIQQQQIIQQ',raw,off+n*size) for n in range(count)]
    sh=headers[names];strings=raw[sh[4]:sh[4]+sh[5]]
    return {strings[h[0]:strings.index(b'\0',h[0])].decode():(h,raw[h[4]:h[4]+h[5]]) for h in headers if h[0]}

flags=['--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-DLMI_GPU_CP_PLAN','-DLMI_GPU_CORE_MEMORY']
newobj=out/'gpu-gx-v57.o'
subprocess.run(['clang',*flags,'-c',str(root/'tools/lmi-gpu-gx-v57.c'),'-o',str(newobj)],check=True)
old=elf(root/'out/lmi-kernel-ios-continue/gpu-gx.o');new=elf(newobj)
assert old.keys()==new.keys()
for name in old:
    if name=='.rodata.cst16':
        assert old[name][1]==struct.pack('<4I',0x60041e,1,1,255)
        assert new[name][1]==struct.pack('<4I',0x60041e,1,7,255)
    elif name.startswith(('.rodata','.rela')):assert old[name][1]==new[name][1],name
# Clang also emits an unused constant array. No relocation may reference it.
cst_section=list(new).index('.rodata.cst16')+1
syms=new['.symtab'][1]
cst_symbols={i//24 for i in range(0,len(syms),24) if struct.unpack_from('<H',syms,i+6)[0]==cst_section}
assert cst_symbols
for name,(header,data) in new.items():
    if name.startswith('.rela'):
        assert all(struct.unpack_from('<Q',data,i+8)[0]>>32 not in cst_symbols for i in range(0,len(data),24))
a,b=old['.gpu_gx'][1],new['.gpu_gx'][1]
assert len(a)==len(b)
changed=[i for i in range(0,len(a),4) if a[i:i+4]!=b[i:i+4]]
assert changed==[0x70]
at=changed[0]
assert struct.unpack_from('<I',a,at)[0]==0xd2800028
assert struct.unpack_from('<I',b,at)[0]==0xd28000e8
linked=elf(root/'out/lmi-kernel-ios-continue/touch.elf')
h,boot=linked['.gpu_boot'];symbols=linked['.symtab'][1];strings=linked['.strtab'][1]
found=[]
for i in range(0,len(symbols),24):
    name,info,other,section,value,size=struct.unpack_from('<IBBHQQ',symbols,i)
    if strings[name:strings.index(b'\0',name)]==b'lmi_gpu_gx':found.append((value,size))
assert len(found)==1
address,length=found[0];assert length==len(a)
offset=address-h[3]
reference=boot[offset:offset+length]
raw=bytearray(base.read_bytes())
segments=runpy.run_path(str(root/'tools/build-lmi-source-runtime.py'))['segments'](raw)
span=[s[2]+address-s[0] for s in segments.values() if s[0]<=address and address+length<=s[0]+s[3]]
assert len(span)==1
start=span[0]
assert raw[start:start+length]==reference,'Linked GX function must match live candidate exactly'
assert raw[start+at:start+at+4]==a[at:at+4]
raw[start+at:start+at+4]=b[at:at+4]
check=bytearray(raw);check[start+at:start+at+4]=a[at:at+4]
assert check==base.read_bytes()
path=out/'mach.development.bcm2837';path.write_bytes(raw)
subprocess.run(['llvm-objdump','-d','--no-show-raw-insn',str(newobj)],stdout=(out/'gx-disassembly.txt').open('w'),check=True)
sources=['build-lmi-display-v57.py','lmi-gpu-gx-v57.c','lmi-gpu-gx.c','lmi-gpu-table-plan.c','lmi-gpu-boot-regs.h','lmi-gpu-hfi-transfer.h']
report=dict(result='HOST_BUILT_ONLY',sha256=sha(path),base_sha256=sha(base),sources={n:sha(root/'tools'/n) for n in sources},
    allowed_file_ranges=[[start+at,start+at+4]],address=hex(address+at),before='0xd2800028',after='0xd28000e8',
    compiled_function_bytes=len(a),relocations_unchanged=True,referenced_rodata_unchanged=True,unused_cst16_not_referenced=True,outside_patch_exact=True,
    stock_speed_bin=0,frequency_index=7,requested_khz=670000,bandwidth_index=255,frequency_measured=False,hardware_tested=False)
(out/'build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
