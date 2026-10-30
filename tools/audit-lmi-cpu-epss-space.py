"""Read-only inventory of references into the legacy CPU/DDR helper unit."""
from pathlib import Path
import hashlib, json, struct
import capstone
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837'
SYMS=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v73-desktop-180/display-v56-candidate/kernel-symbols.txt'
START,END=0xfffffff0074d0a78,0xfffffff0074d1e74
ENTRY={0xfffffff0074d0a78,0xfffffff0074d0dfc}


def segments(raw):
    pos=32;out=[]
    for _ in range(struct.unpack_from('<I',raw,16)[0]):
        cmd,size=struct.unpack_from('<II',raw,pos)
        if cmd==25:
            name=raw[pos+8:pos+24].rstrip(b'\0').decode()
            va,vs,fo,fs=struct.unpack_from('<QQQQ',raw,pos+24)
            out.append((name,va,vs,fo,fs))
        pos+=size
    return out


def main():
    out=ROOT/'out/lmi-cpu-epss/space-a';assert not out.exists();out.mkdir()
    raw=BASE.read_bytes();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(BASE)=='68ec1820fea704e99ab1ccac5d70f19670faa9428378f75592f251ff5ede56c2'
    syms=[(int(v[0],16),v[2]) for l in SYMS.read_text().splitlines() if len(v:=l.split())==3]
    assert dict((n,a) for a,n in syms)['_ddr_rsc']==0xfffffff007e98850
    segs=segments(raw);cs=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM);cs.detail=True;cs.skipdata=True
    control=[];address=[];pages=[];state_pages=[];data=[]
    for name,va,vs,fo,fs in segs:
        if name=='__TEXT_EXEC':
            for ins in cs.disasm(raw[fo:fo+fs],va):
                if not ins.id:continue
                if START<=ins.address<END:continue
                imms=[op.imm for op in ins.operands if op.type==capstone.arm64.ARM64_OP_IMM]
                if not imms:continue
                target=imms[-1]&((1<<64)-1)
                row=dict(pc=hex(ins.address),mnemonic=ins.mnemonic,operands=ins.op_str,target=hex(target))
                if ins.mnemonic in ['adr','ldr'] and START<=target<END:address.append(row)
                elif ins.mnemonic=='adrp':
                    if START&~4095<=target<(END+4095)&~4095:
                        row['context']=[f'{v.address:#x}: {v.mnemonic} {v.op_str}' for v in cs.disasm(raw[fo+ins.address-va:fo+ins.address-va+36],ins.address)]
                        pages.append(row)
                    if target==0xfffffff007e98000:
                        row['context']=[f'{v.address:#x}: {v.mnemonic} {v.op_str}' for v in cs.disasm(raw[fo+ins.address-va:fo+ins.address-va+36],ins.address)]
                        state_pages.append(row)
                elif (ins.group(capstone.CS_GRP_JUMP) or ins.group(capstone.CS_GRP_CALL)) and START<=target<END:control.append(row)
        elif name not in ['__LINKEDIT','__LINKINFO']:
            for offset in range(0,fs-7,8):
                value=struct.unpack_from('<Q',raw,fo+offset)[0]
                if START<=value<END:data.append(dict(va=hex(va+offset),target=hex(value),segment=name))
    assert control and all(int(row['target'],16) in ENTRY for row in control),control
    assert not address and not data,(address,data)
    # ADRP pages also contain adjacent helpers. Keep this inventory for
    # independent instruction review; a page match alone is not a reference.
    (out/'reference-inventory.json').write_text(json.dumps(dict(
        result='REFERENCE_INVENTORY_NOT_YET_RELEASE_APPROVAL',range=[hex(START),hex(END)],bytes=END-START,
        external_direct_calls=control,external_exact_address_references=address,loaded_pointers=data,
        neighboring_code_page_references=pages,state_page_references=state_pages,
        original_functions=[dict(address=hex(a),name=n) for a,n in syms if START<=a<END],
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),BASE,SYMS]}),indent=2)+'\n')
    print('Direct calls:',len(control),'loaded pointers:',len(data),'neighbor code pages:',len(pages),'state pages:',len(state_pages))


if __name__=='__main__':main()
