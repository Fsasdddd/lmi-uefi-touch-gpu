"""Audit three obsolete board-init bodies for the opt-in lmi desktop backend.

The sole step-table reader is replaced by the lmi probe. All three table slots
are redirected to the first body's false-return stub, outside the new payload.
Every other stored pointer must be the exact Mach-O nlist value for an entry.
"""
from pathlib import Path
import hashlib,json,re,runpy,struct

KERNEL_SHA='afb7ab6c0512d5199c5347c52b1748b5f1b4102ff5aede51f5429750e6a804d4'
ENTRY=0xfffffff0074d9c80
START=ENTRY+8
END=0xfffffff0074db04c
ENTRIES={'_step_gmu_start':ENTRY,'_step_gmu_queues':0xfffffff0074da2e8,'_step_core_power':0xfffffff0074da79c}

def audit(data,symbols,source):
    assert hashlib.sha256(data).hexdigest()==KERNEL_SHA
    syms=[(int(p[0],16),p[2]) for line in symbols.splitlines() if len(p:=line.split(maxsplit=2))==3]
    assert [(a,n) for a,n in syms if ENTRY<=a<END]==[(a,n) for n,a in ENTRIES.items()]
    assert (END,'_step_core_space') in syms
    clean=re.sub(r'/\*.*?\*/','',source,flags=re.S)
    for name in ENTRIES:
        assert len(re.findall(r'\b'+name[1:]+r'\b',clean))==2,'Additional source caller: '+name
    assert len(re.findall(r'\bsteps\s*\[',clean))==3
    assert 'if (!steps[step - 1]())' in source.split('void\nredwood_adreno_init(void)',1)[1]
    sects=runpy.run_path(str(Path(__file__).with_name('audit-lmi-gpu-normal-diag-region.py')))['sections'](data)
    cover=[s for s in sects if s[1]<=ENTRY<END<=s[1]+s[2]];assert len(cover)==1
    section=cover[0];assert section[5]==5 and section[4]&0x80000400
    def off(va,n=1):
        s=next(s for s in sects if s[1]<=va and va+n<=s[1]+s[2]);return s[3]+va-s[1]
    def signed(v,b):return v-(1<<b) if v&(1<<(b-1)) else v
    refs=[];pages=[]
    for name,va,length,fo,flags,prot in sects:
        if not flags&0x80000400:continue
        for i in range(0,length-3,4):
            pc=va+i;w=struct.unpack_from('<I',data,fo+i)[0]
            if ENTRY<=pc<END:continue
            target=None
            if w&0x7c000000==0x14000000:target=pc+(signed(w&0x3ffffff,26)<<2)
            elif w&0xff000010==0x54000000 or w&0x7e000000==0x34000000:target=pc+(signed((w>>5)&0x7ffff,19)<<2)
            elif w&0x7e000000==0x36000000:target=pc+(signed((w>>5)&0x3fff,14)<<2)
            if target is not None and ENTRY<=target<END:refs.append([hex(pc),hex(target),'branch'])
            if w&0x9f000000==0x10000000:
                target=pc+signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)
                if ENTRY<=target<END:refs.append([hex(pc),hex(target),'ADR'])
            if w&0x3b000000==0x18000000:
                target=pc+(signed((w>>5)&0x7ffff,19)<<2)
                if ENTRY<=target<END:refs.append([hex(pc),hex(target),'literal'])
            if w&0x9f000000!=0x90000000:continue
            page=(pc&~4095)+(signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)<<12)
            if not (ENTRY&~4095)<=page<(END+4095)&~4095:continue
            reg=w&31;resolved=[]
            for j in range(i+4,min(i+36,length-3),4):
                c=struct.unpack_from('<I',data,fo+j)[0]
                if c&0xff000000==0x91000000 and (c>>5)&31==reg:
                    target=page+(((c>>10)&4095)<<(12 if c&(1<<22) else 0));resolved.append(hex(target))
                    if ENTRY<=target<END:refs.append([hex(va+j),hex(target),'ADRP/ADD'])
            pages.append(dict(pc=hex(pc),page=hex(page),resolved=resolved))
    assert not refs,refs
    table_va=next(a for a,n in syms if n=='_steps');table_off=off(table_va,22*8)
    slots=[table_off+i*8 for i in [14,15,16]]
    assert [struct.unpack_from('<Q',data,p)[0] for p in slots]==list(ENTRIES.values())
    table_section=next(s for s in sects if s[1]<=table_va<table_va+22*8<=s[1]+s[2]);assert not table_section[5]&2
    metadata=[];pos=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,pos)
        if cmd==2:
            so,n,strings,_=struct.unpack_from('<4I',data,pos+8)
            for k in range(n):
                at=so+16*k;value=struct.unpack_from('<Q',data,at+8)[0]
                if not ENTRY<=value<END:continue
                ns=strings+struct.unpack_from('<I',data,at)[0];name=data[ns:data.index(b'\0',ns)].decode()
                assert name in ENTRIES and value==ENTRIES[name]
                metadata.append(at+8)
        pos+=size
    assert len(metadata)==3
    pointers=[i for i in range(0,len(data)-7,4) if ENTRY<=struct.unpack_from('<Q',data,i)[0]<END]
    assert sorted(pointers)==sorted(slots+metadata),[hex(p) for p in pointers]
    return dict(result='PASS',kernel_sha256=KERNEL_SHA,entry=hex(ENTRY),start=hex(START),end=hex(END),bytes=END-START,
        segment_initprot=5,original_entry_words=[hex(v) for v in struct.unpack_from('<2I',data,off(ENTRY,8))],
        original_entries={n:hex(v) for n,v in ENTRIES.items()},table_slots=[hex(p) for p in slots],
        table_redirect_value=hex(ENTRY),nlist_metadata=[hex(p) for p in metadata],external_references=refs,
        adrp_pages=pages,source_sha256=hashlib.sha256(source.encode()).hexdigest(),hardware_verified=False,
        limitation='Require replaced initializer, false entry stub, all3 table redirects, RX bounds, and real canary')

if __name__=='__main__':
    r=Path(__file__).resolve().parents[1]
    result=audit((r/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel/mach.development.bcm2837').read_bytes(),
        (r/'out/kernel-symbols.txt').read_text(),(r/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text())
    (r/'out/lmi-gpu-research/desktop-region-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
