"""Integrate the audited source extension and relinked runtime. Host only.

The old source adapter intentionally rejects this layout; this separate builder
checks the new layout, exact old runtime, new binding proofs and hook preimage.
"""
from pathlib import Path
import argparse, hashlib, json, runpy, struct, subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--resume-audit',action='store_true')
parser.add_argument('--output',choices=['v41','v41b'],default='v41b')
args=parser.parse_args()

repo=Path(__file__).resolve().parents[1]
out=repo/('out/lmi-kernel-display-runtime-'+args.output)
if args.resume_audit:
    assert (out/'patch-conflicts.json').is_file() and not (out/'mach.development.bcm2837').exists()
else:
    assert not out.exists(), 'Preserve previous integration evidence'
    out.mkdir()
module=runpy.run_path(str(repo/'tools/build-lmi-source-runtime.py'))
base=repo/'out/lmi-kernel-source-build-v36/reconstruct-base'
old=base.joinpath('mach.development.bcm2837').read_bytes()
runtime=repo.joinpath('out/lmi-kernel-source-runtime-v36/mach.development.bcm2837').read_bytes()
source=Path('/root/hackios-lmi/out/lmi-display-extension-v41/extension').read_bytes()
def sha(raw):return hashlib.sha256(raw).hexdigest()
assert sha(old)=='0a8e5f2be56ed8538d361cf570799b49792270f51383f8b71c584c96fca8e0d5'
assert sha(runtime)=='98ef20d5c5bf4a902982840ee0529f36c0594995e7d2ed6c1caed93e4798b8fc'
assert sha(source)=='304e630feb466e1de19789f8b7c9fd7a539a7cd00e9bb0a8ecca650e3f5c2108'
oldseg,newseg=module['segments'](old),module['segments'](source)
oldsyms=module['symbols']((base/'kernel-symbols.txt').read_text())
newtext=(repo/'out/lmi-display-extension-v41/extension-symbols.txt').read_text()
newsyms=module['symbols'](newtext)
a,b=oldseg['__TEXT_EXEC'],newseg['__TEXT_EXEC']
assert a[0]==b[0] and a[2]==b[2] and b[1]==b[3]==a[1]+0x4000
oldcode=sorted((va,name) for va,kind,name in oldsyms if a[0]<=va<a[0]+a[1])
newcode=sorted((va,name) for va,kind,name in newsyms if a[0]<=va<a[0]+a[1])
assert oldcode==newcode, 'Original executable symbols moved'
assert oldseg['__DATA_CONST']==newseg['__DATA_CONST']
assert oldseg['__TEXT']==newseg['__TEXT']
for name in ['__KLD','__LASTDATA_CONST','__KLDDATA','__DATA','__BOOTDATA']:
    original,candidate=oldseg[name],newseg[name]
    assert candidate[0]==original[0]+0x4000 and candidate[2]==original[2]+0x4000

def at(segments,address,length=1):
    candidates=[s for s in segments.values() if s[0]<=address and address+length<=s[0]+s[3]]
    assert len(candidates)==1,(hex(address),length)
    s=candidates[0];return s[2]+address-s[0]

def allocated(raw):
    pos=struct.unpack_from('<Q',raw,40)[0]
    size,count,strings=struct.unpack_from('<HHH',raw,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,pos+i*size) for i in range(count)]
    names=sections[strings];names=raw[names[4]:names[4]+names[5]]
    return {names[s[0]:names.index(b'\0',s[0])].decode():(s[3],raw[s[4]:s[4]+s[5]])
        for s in sections if s[2]&2 and s[5]}

relocation=json.loads((repo/'out/lmi-display-runtime-v41/result.json').read_text())
assert relocation['result']=='RELINKED_UNINTEGRATED' and relocation['extension_sha256']==sha(source)
sections=[]
for name,proof in relocation['runtime'].items():
    frozen=(repo/('out/lmi-kernel-ios-continue/'+name+'.elf')).read_bytes()
    linked=Path('/root/hackios-lmi/out/lmi-display-runtime-v41/'+name+'-relocated.elf').read_bytes()
    assert sha(frozen)==proof['original_elf_sha256'] and sha(linked)==proof['relocated_elf_sha256']
    assert proof['baseline_allocated_bytes_exact']
    original,updated=allocated(frozen),allocated(linked)
    assert original.keys()==updated.keys()
    for section,(address,data) in original.items():
        assert updated[section][0]==address and len(updated[section][1])==len(data)
        assert runtime[at(oldseg,address,len(data)):at(oldseg,address,len(data))+len(data)]==data, (name,section,'Frozen runtime differs from linked allocation')
        sections.append((address,address+len(data),updated[section][1]))
early=json.loads((repo/'out/lmi-display-early-v41/result.json').read_text())
assert early['result']=='RELINKED_UNINTEGRATED' and len(early['thunks'])==7
for index,proof in early['thunks'].items():
    frozen=Path(proof['original_elf']).read_bytes()
    linked=Path('/root/hackios-lmi/out/lmi-display-early-v41/'+index+'-relocated.elf').read_bytes()
    assert sha(frozen)==proof['original_sha256'] and sha(linked)==proof['relocated_sha256']
    assert proof['baseline_allocated_bytes_exact']
    before,after=allocated(frozen),allocated(linked)
    assert before.keys()==after.keys()
    for section,(address,data) in before.items():
        assert after[section][0]==address and len(after[section][1])==len(data)
        assert runtime[at(oldseg,address,len(data)):at(oldseg,address,len(data))+len(data)]==data
        sections.append((address,address+len(data),after[section][1]))
profile=runpy.run_path(str(repo/'tools/lmi-gpu-desktop-profile.py'))
abi={pc:(name,original,entry) for name,(pc,original,entry) in profile['ABI'].items()}
elfsymbols={name:int(value,16) for line in subprocess.check_output(
    ['llvm-nm',str(repo/'out/lmi-kernel-ios-continue/touch.elf')],text=True).splitlines()
    if len(row:=line.split())==3 for value,kind,name in [row]}
def adrp_page(word,pc):
    assert word&0x9f000000==0x90000000
    immediate=((word>>29)&3)|(((word>>5)&0x7ffff)<<2)
    if immediate&(1<<20):immediate-=1<<21
    return (pc&~0xfff)+(immediate<<12)

conflicts=[];accepted=[];edits=[];result=bytearray(source)
for name,(va,vs,fo,fs) in oldseg.items():
    if not fs or name in ('__LINKINFO','__LINKEDIT'):continue
    step=4 if name=='__TEXT_EXEC' else 8
    for offset in range(0,fs,step):
        before,after=old[fo+offset:fo+offset+step],runtime[fo+offset:fo+offset+step]
        if before==after:continue
        address=va+offset;target=at(newseg,address,step)
        covered=any(begin<=address and address+step<=end for begin,end,data in sections)
        if source[target:target+step]!=before and not covered:
            record=dict(va=hex(address),original=before.hex(),extended=source[target:target+step].hex(),runtime=after.hex())
            # Six old desktop ABI entries begin with ADRP to moved writable
            # data. Their whole first instruction is replaced by the same
            # verified unconditional branch. Admit only those pinned entries,
            # exact original words, unchanged register/opcode and +16KiB page.
            approved=False
            if step==4 and address in abi:
                name,expected,entry=abi[address]
                first,new,branch=struct.unpack('<I',before)[0],struct.unpack_from('<I',source,target)[0],struct.unpack('<I',after)[0]
                imm=branch&0x3ffffff;imm=imm-(1<<26) if imm&(1<<25) else imm
                approved=(first==expected and first&0x9f000000==new&0x9f000000==0x90000000 and
                    (first^new)&~0x60ffffe0==0 and adrp_page(new,address)-adrp_page(first,address)==0x4000 and
                    branch&0xfc000000==0x14000000 and address+imm*4==elfsymbols['lmi_desktop_'+entry])
                if approved:record.update(symbol=name,source_data_page_delta='0x4000',branch_target_unchanged=True)
            (accepted if approved else conflicts).append(record)
        result[target:target+step]=after
        edits.append(dict(va=hex(address),bytes=step,relinked_section=covered))
if not args.resume_audit:
    (out/'patch-conflicts.json').write_text(json.dumps(conflicts,indent=2)+'\n')
(out/'accepted-abi-relocations.json').write_text(json.dumps(accepted,indent=2)+'\n')
assert not conflicts, f'{len(conflicts)} old runtime patches overlap relocated source instructions; audit before integration'
for begin,end,data in sections:
    target=at(newseg,begin,len(data));result[target:target+len(data)]=data
symbols={name:va for va,kind,name in newsyms}
show=symbols['__ZN19IOMobileFramebuffer4showEPKhPP13MiniIOSurface']
assert show==0xfffffff0079e39f0
target=at(newseg,show,4)
assert struct.unpack_from('<I',result,target)[0]==0xd10703ff
observer=symbols['_lmi_dpu_observe_show'];trampoline=symbols['_lmi_dpu_original_show']
assert 0xfffffff007ae0000<=observer<0xfffffff007ae4000
assert (observer-show)%4==0 and -(1<<27)<=observer-show<(1<<27)
struct.pack_into('<I',result,target,0x14000000|(((observer-show)//4)&0x3ffffff))
entry=at(newseg,trampoline,8)
displaced,branch=struct.unpack_from('<2I',result,entry)
assert displaced==0xd10703ff and branch&0xfc000000==0x14000000
imm=branch&0x3ffffff;imm=imm-(1<<26) if imm&(1<<25) else imm
assert trampoline+4+imm*4==show+4, 'Trampoline continuation mismatch'
assert len(result)==len(source)
(out/'mach.development.bcm2837').write_bytes(result)
(out/'kernel-symbols.txt').write_text(newtext)
report=dict(result='INTEGRATED_HOST_ONLY',sha256=sha(result),source_sha256=sha(source),
    runtime_sha256=sha(runtime),executable_symbol_addresses_unchanged=True,
    runtime_bindings_relinked=True,edits=edits,accepted_abi_relocations=accepted,
    show_hook=dict(va=hex(show),target=hex(observer),trampoline=hex(trampoline),register_writes=False),
    hardware_ready=False,device_access=False)
(out/'integration-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='edits'},indent=2))
