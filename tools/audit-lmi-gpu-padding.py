"""Read-only audit of a small unused tail in the pinned kernel RX segment.

No existing function body or section is reused. The selected 3584 bytes are
zero file padding in the same minimum 4KiB page as the end of __hib_text.
Dynamic computed pointers still require source review and execution proof.
"""
from pathlib import Path
import hashlib,json,struct

KERNEL_SHA='afb7ab6c0512d5199c5347c52b1748b5f1b4102ff5aede51f5429750e6a804d4'
START=0xfffffff007adc200
END=0xfffffff007add000

def scan_references(data,sections,END=END):
    branches=[];addresses=[];pages=[]
    def signed(value,bits):return value-(1<<bits) if value&(1<<(bits-1)) else value
    for name,va,size,off,flags in sections:
        if not flags&0x80000400:continue
        for n in range(0,size-3,4):
            pc=va+n;word=struct.unpack_from('<I',data,off+n)[0];dest=None
            if word&0x7c000000==0x14000000:dest=pc+(signed(word&0x3ffffff,26)<<2)
            elif word&0xff000010==0x54000000 or word&0x7e000000==0x34000000:dest=pc+(signed((word>>5)&0x7ffff,19)<<2)
            elif word&0x7e000000==0x36000000:dest=pc+(signed((word>>5)&0x3fff,14)<<2)
            if dest is not None and START<=dest<END:branches.append([hex(pc),hex(dest)])
            if word&0x9f000000==0x10000000:
                dest=pc+signed((((word>>5)&0x7ffff)<<2)|((word>>29)&3),21)
                if START<=dest<END:addresses.append([hex(pc),hex(dest),'ADR'])
            if word&0x3b000000==0x18000000:
                dest=pc+(signed((word>>5)&0x7ffff,19)<<2)
                if START<=dest<END:addresses.append([hex(pc),hex(dest),'literal load'])
            if word&0x9f000000==0x90000000:
                page=(pc&~4095)+(signed((((word>>5)&0x7ffff)<<2)|((word>>29)&3),21)<<12)
                if not (START&~4095)<=page<END:continue
                reg=word&31;resolved=[]
                for j in range(n+4,min(n+36,size-3),4):
                    consumer=struct.unpack_from('<I',data,off+j)[0]
                    if consumer&0xff000000==0x91000000 and (consumer>>5)&31==reg:
                        dest=page+(((consumer>>10)&4095)<<(12 if consumer&(1<<22) else 0))
                        resolved.append(hex(dest))
                        if START<=dest<END:addresses.append([hex(va+j),hex(dest),'ADRP/ADD'])
                pages.append(dict(pc=hex(pc),page=hex(page),resolved_adds=resolved))
    return branches,addresses,pages

def audit(data,symbols='',END=END):
    assert END in (0xfffffff007add000,0xfffffff007ae0000)
    assert hashlib.sha256(data).hexdigest()==KERNEL_SHA, 'Unexpected base kernel'
    assert struct.unpack_from('<I',data)[0]==0xfeedfacf
    sections=[];segments=[];pos=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,pos)
        if cmd==0x19:
            name=data[pos+8:pos+24].split(bytes([0]))[0].decode()
            va,vs,off,fs,mp,ip,nsects,flags=struct.unpack_from('<4Q4I',data,pos+24)
            segments.append((name,va,vs,off,fs,ip))
            for n in range(nsects):
                at=pos+72+80*n;sn=data[at:at+16].split(bytes([0]))[0].decode()
                a,z,o=struct.unpack_from('<QQI',data,at+32);fl=struct.unpack_from('<I',data,at+64)[0]
                sections.append((sn,a,z,o,fl))
        pos+=size
    candidates=[v for v in segments if v[0]=='__TEXT_EXEC'];assert len(candidates)==1
    name,va,vs,off,fs,prot=candidates[0]
    assert prot==5 and va<=START<END<=va+min(vs,fs)
    assert END-START in (3584,15872) and START%16==0 and END%4096==0
    if END==0xfffffff007ae0000:
        root=Path(__file__).resolve().parents[1]
        arm=(root/'out/lmi-gpu-research/padding-arm-vm-init.c').read_bytes()
        assert hashlib.sha256(arm).hexdigest()=='3aef6df1e86fea3061ef4b5b83053502e2c50bf2e636d6949c4d55a58181e3f5'
        assert b'arm_vm_page_granular_ROX(segTEXTEXECB, segSizeTEXTEXEC,' in arm
        assert b'getsegdatafromheader(&_mh_execute_header, "__TEXT_EXEC", &segSizeTEXTEXEC)' in arm
        loader=(root/'hackios/xnuloader/loader.c').read_bytes()
        assert hashlib.sha256(loader).hexdigest()=='95ce0c52edb90d95c972a6cd865203e2b1d037289f5093c59196e6eb993578c6'
    assert all(not z or a+z<=START or a>=END for sn,a,z,o,fl in sections), 'Declared section overlap'
    hib=[v for v in sections if v[0]=='__hib_text'];assert len(hib)==1
    assert (hib[0][1]+hib[0][2]-1)//4096==START//4096, 'Not shared with existing executable page'
    file_offset=off+START-va
    assert data[file_offset:file_offset+END-START]==bytes(END-START), 'Padding is occupied'
    branches,addresses,pages=scan_references(data,sections,END)
    pointers=[]
    for n in range(0,len(data)-7,4):
        value=struct.unpack_from('<Q',data,n)[0]
        if START<=value<END:pointers.append([hex(n),hex(value)])
    named=[]
    for line in symbols.splitlines():
        fields=line.split(maxsplit=2)
        if len(fields)==3 and START<=int(fields[0],16)<END:named.append(line)
    report=dict(kernel_sha256=KERNEL_SHA,start=hex(START),end=hex(END),bytes=END-START,file_offset=hex(file_offset),
                segment=name,segment_initprot=prot,shares_minimum_executable_page=True,
                declared_section_overlap=False,all_zero_padding=True,external_branches=branches,
                external_addresses=addresses,stored_interior_pointers=pointers,named_symbols=named,
                adrp_page_materializations=pages,hardware_execution_verified=False,
                limitation='Static scan cannot rule out arbitrary dynamically computed pointers; source/loader ROX mapping review and actual execution proof required')
    assert not branches and not addresses and not pointers and not named, report
    return report

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    source=root/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel/mach.development.bcm2837'
    report=audit(source.read_bytes(),(root/'out/kernel-symbols.txt').read_text())
    (root/'out/lmi-gpu-research/exec-padding-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
