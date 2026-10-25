"""Audit the unreachable body of the replaced redwood initializer, read-only.

This is a candidate RX region, never a permission to reuse other GPU routines.
Pin a single kernel; reject external direct branches, ADRs and stored pointers
into its interior. The normal initializer entry itself is replaced separately.
"""
from pathlib import Path
import hashlib,json,struct

KERNEL_SHA='afb7ab6c0512d5199c5347c52b1748b5f1b4102ff5aede51f5429750e6a804d4'
ENTRY=0xfffffff0074d4c48
START=ENTRY+4
END=0xfffffff0074d59c4

def audit(data):
    assert hashlib.sha256(data).hexdigest()==KERNEL_SHA
    sections=[];pos=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,pos)
        if cmd==0x19:
            for n in range(struct.unpack_from('<I',data,pos+64)[0]):
                at=pos+72+n*80
                name=data[at:at+16].split(bytes([0]))[0].decode()
                va,length,off=struct.unpack_from('<QQI',data,at+32)
                flags=struct.unpack_from('<I',data,at+64)[0]
                if flags&0x80000400:sections.append((name,va,length,off))
        pos+=size
    branches=[];addresses=[]
    def signed(v,bits):return v-(1<<bits) if v&(1<<(bits-1)) else v
    for name,va,length,off in sections:
        for i in range(0,length-3,4):
            pc=va+i;word=struct.unpack_from('<I',data,off+i)[0]
            if ENTRY<=pc<END:continue
            dest=None
            if word&0x7c000000==0x14000000:dest=pc+(signed(word&0x3ffffff,26)<<2)
            elif word&0xff000010==0x54000000 or word&0x7e000000==0x34000000:dest=pc+(signed((word>>5)&0x7ffff,19)<<2)
            elif word&0x7e000000==0x36000000:dest=pc+(signed((word>>5)&0x3fff,14)<<2)
            if dest is not None and START<=dest<END:branches.append((hex(pc),hex(word),hex(dest)))
            if word&0x9f000000==0x10000000:
                dest=pc+signed((((word>>5)&0x7ffff)<<2)|((word>>29)&3),21)
                if START<=dest<END:addresses.append((hex(pc),hex(dest)))
    pointers=[]
    for off in range(0,len(data)-7,4):
        value=struct.unpack_from('<Q',data,off)[0]
        if START<=value<END:pointers.append((hex(off),hex(value)))
    report=dict(kernel_sha256=KERNEL_SHA,entry=hex(ENTRY),start=hex(START),end=hex(END),
        bytes=END-START,instruction_sections=len(sections),external_branches=branches,
        external_adr=addresses,stored_interior_pointers=pointers,
        limitation='Indirect dynamically computed targets require source audit; entry must branch away before any interior byte is reused')
    assert sections and not branches and not addresses and not pointers,report
    return report

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    source=root/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel/mach.development.bcm2837'
    report=audit(source.read_bytes())
    target=root/'out/lmi-gpu-research/init-region-audit.json'
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
