"""Audit the obsolete core-start body for read-only normal-mode diagnostics, read-only.

The old core-start entry must become `mov w0,0; ret`, so its function-table pointer
cannot accidentally invoke the new helper. Only ENTRY+8..END may be reused.
The lmi profile also replaces the sole reader of that diagnostic step table.
No other GPU helper or section is covered by this audit.
"""
from pathlib import Path
import hashlib,json,re,struct
KERNEL_SHA='afb7ab6c0512d5199c5347c52b1748b5f1b4102ff5aede51f5429750e6a804d4'
ENTRY=0xfffffff0074d3f54
START=ENTRY+8
END=0xfffffff0074d490c
INIT=0xfffffff0074d4c48
INIT_END=0xfffffff0074d59c4

def sections(data):
    result=[];pos=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,pos)
        if cmd==0x19:
            prot=struct.unpack_from('<I',data,pos+60)[0]
            for n in range(struct.unpack_from('<I',data,pos+64)[0]):
                at=pos+72+n*80;name=data[at:at+16].split(b'\0')[0].decode()
                va,length,off=struct.unpack_from('<QQI',data,at+32);flags=struct.unpack_from('<I',data,at+64)[0]
                result.append((name,va,length,off,flags,prot))
        pos+=size
    return result

def scan(data,sects):
    branches=[];addresses=[];pages=[];pointers=[]
    def signed(v,b):return v-(1<<b) if v&(1<<(b-1)) else v
    for name,va,length,off,flags,prot in sects:
        if not flags&0x80000400:continue
        for i in range(0,length-3,4):
            pc=va+i;w=struct.unpack_from('<I',data,off+i)[0]
            if ENTRY<=pc<END:continue
            target=None
            if w&0x7c000000==0x14000000:target=pc+(signed(w&0x3ffffff,26)<<2)
            elif w&0xff000010==0x54000000 or w&0x7e000000==0x34000000:target=pc+(signed((w>>5)&0x7ffff,19)<<2)
            elif w&0x7e000000==0x36000000:target=pc+(signed((w>>5)&0x3fff,14)<<2)
            if target is not None and ENTRY<target<END:branches.append([hex(pc),hex(target)])
            if w&0x9f000000==0x10000000:
                target=pc+signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)
                if ENTRY<target<END:addresses.append([hex(pc),hex(target),'ADR'])
            if w&0x3b000000==0x18000000:
                target=pc+(signed((w>>5)&0x7ffff,19)<<2)
                if ENTRY<target<END:addresses.append([hex(pc),hex(target),'literal'])
            if w&0x9f000000==0x90000000:
                page=(pc&~4095)+(signed((((w>>5)&0x7ffff)<<2)|((w>>29)&3),21)<<12)
                if page!=ENTRY&~4095:continue
                reg=w&31;resolved=[]
                for j in range(i+4,min(i+36,length-3),4):
                    c=struct.unpack_from('<I',data,off+j)[0]
                    if c&0xff000000==0x91000000 and (c>>5)&31==reg:
                        target=page+(((c>>10)&4095)<<(12 if c&(1<<22) else 0));resolved.append(hex(target))
                        if ENTRY<target<END:addresses.append([hex(va+j),hex(target),'ADRP/ADD'])
                pages.append(dict(pc=hex(pc),page=hex(page),resolved=resolved))
    for i in range(0,len(data)-7,4):
        value=struct.unpack_from('<Q',data,i)[0]
        if ENTRY<=value<END:pointers.append([hex(i),hex(value)])
    return branches,addresses,pages,pointers

def audit(data,symbols,source):
    assert hashlib.sha256(data).hexdigest()==KERNEL_SHA
    assert len(re.findall(r'\bstep_core_start\b',re.sub(r'/\*.*?\*/', '',source,flags=re.S)))==3, 'Demo has additional source callers'
    assert len(re.findall(r'\bsteps\s*\[',source))==3 and 'sizeof(steps[0])' in source, 'Step table has additional readers'
    assert 'if (!steps[step - 1]())' in source
    init=source.split('void\nredwood_adreno_init(void)',1)[1]
    assert 'if (!steps[step - 1]())' in init
    syms=[(int(p[0],16),p[2]) for line in symbols.splitlines() if len(p:=line.split(maxsplit=2))==3]
    assert (ENTRY,'_step_core_start') in syms and (END,'_step_core_commands') in syms
    assert not any(ENTRY<a<END for a,n in syms), 'Named interior target'
    sects=sections(data);cover=[s for s in sects if s[1]<=ENTRY<END<=s[1]+s[2]];assert len(cover)==1
    name,va,length,off,flags,prot=cover[0];assert prot==5 and flags&0x80000400
    at=off+ENTRY-va
    branches,addresses,pages,pointers=scan(data,sects)
    assert not branches and not addresses, (branches,addresses)
    # Mach-O nlist metadata also contains the function address. Identify that
    # exact named record, rather than treating it as a runtime function table.
    pos=32;symbol_values=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,z=struct.unpack_from('<II',data,pos)
        if cmd==2:
            so,n,strings,ss=struct.unpack_from('<4I',data,pos+8)
            for k in range(n):
                at_symbol=so+16*k
                if struct.unpack_from('<Q',data,at_symbol+8)[0]!=ENTRY:continue
                name_at=strings+struct.unpack_from('<I',data,at_symbol)[0]
                assert data[name_at:data.index(b'\0',name_at)]==b'_step_core_start'
                symbol_values.append(hex(at_symbol+8))
        pos+=z
    assert len(symbol_values)==1
    runtime_pointers=[p for p in pointers if p[0] not in symbol_values]
    assert len(runtime_pointers)==1 and runtime_pointers[0][1]==hex(ENTRY), pointers
    table_off=int(runtime_pointers[0][0],16)-19*8
    table_section=next(s for s in sects if s[3]<=table_off<table_off+22*8<=s[3]+s[2])
    table_va=table_section[1]+table_off-table_section[3]
    assert (table_va,'_steps') in syms and table_section[5]&2==0
    assert struct.unpack_from('<Q',data,table_off)[0]==0xfffffff0074d7870
    report=dict(result='PASS',kernel_sha256=KERNEL_SHA,entry=hex(ENTRY),start=hex(START),end=hex(END),bytes=END-START,
        original_entry_words=[hex(x) for x in struct.unpack_from('<2I',data,at)],
        entry_replacement=['0x52800000','0xd65f03c0'],segment_initprot=prot,
        external_interior_branches=branches,external_interior_addresses=addresses,stored_targets=pointers,nlist_metadata=symbol_values,
        step_table_va=hex(table_va),step_table_only_reader_source='redwood_adreno_init; entry must branch to lmi probe',
        additional_source_caller='core recovery; obsolete core-start entry must return false',
        adrp_same_page=pages,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        hardware_execution_verified=False,limitation='Static scan cannot exclude arbitrary dynamic interior targets; source review, entry stubbing, replaced initializer and real canary execution required')
    return report

if __name__=='__main__':
    r=Path(__file__).resolve().parents[1]
    data=(r/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel/mach.development.bcm2837').read_bytes()
    result=audit(data,(r/'out/kernel-symbols.txt').read_text(),(r/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text())
    (r/'out/lmi-gpu-research/normal-diag-region-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
