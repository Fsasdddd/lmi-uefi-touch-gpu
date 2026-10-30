"""Execute final v77 ARM64 entry veneers, core, and real volatile IO wrappers.

Only native allocation, mapping, boot-arg, memcpy and logging services are
modeled. Register reads/writes and barriers execute from the final RAM image.
This is not hardware/thermal/SMP validation or a measurement of CPU speed.
"""
from pathlib import Path
import argparse,hashlib,json,re,struct,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'out/lmi-smp-host-deps'))
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X19,UC_ARM64_REG_X29,UC_ARM64_REG_X30,UC_ARM64_REG_PC,UC_ARM64_REG_SP
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
FOLDER=ROOT/'out/lmi-cpu-epss-v77e'
BASE=ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837'
INIT,QUIESCE=0xfffffff0074d0dfc,0xfffffff0074d0a78
KB=0xfffffff007004000
STATE=0xfffffff007e98850
STACK,HEAP,MMIO,RETURN=0x1000000,0x3000000,0x4000000,0x5000000
DIRTY,PREPARED=620,616
CAPS=[1804800,2419200,2841600]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def run(raw, *,mode=2,allocation_fail=False,map_fail=None,unsupported=False,
        corrupt_apply=False,restore_fail=False,interrupt=False,already_top=False):
    uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);mapped=set()
    audit=json.loads((FOLDER/'build-audit.json').read_text());bindings={n:int(v,16) for n,v in audit['bindings'].items()}
    for pc in [INIT,QUIESCE,STATE,RETURN,*bindings.values()]:
        page=pc&~4095
        if page not in mapped:uc.mem_map(page,4096);mapped.add(page)
    for row in audit['sections']:
        pc=int(row['start'],16);end=pc+row['bytes']
        for page in range(pc&~4095,(end+4095)&~4095,4096):
            if page not in mapped:uc.mem_map(page,4096);mapped.add(page)
        uc.mem_write(pc,bytes(raw[pc-KB:end-KB]))
    for pc in [INIT,QUIESCE]:uc.mem_write(pc,bytes(raw[pc-KB:pc-KB+4]))
    uc.mem_map(STACK,16384);uc.mem_map(HEAP,4096);uc.mem_map(MMIO,3*4096)
    def row(freq,cc=4):return (1<<30)|(cc<<16)|freq//19200
    original=[]
    for i,cap in enumerate(CAPS):
        lut=[4<<16,row(960000),row(cap),row(cap+19200),row(cap+38400,1),row(cap+38400,1)]+[0]*34
        if unsupported:lut=[row(960000,3)]*40
        uc.mem_write(MMIO+i*4096+0x100,struct.pack('<40I',*lut))
        orig=2 if already_top else 0;original.append(orig)
        uc.mem_write(MMIO+i*4096+0x320,struct.pack('<I',orig))
    u32=lambda pc:struct.unpack('<I',uc.mem_read(pc,4))[0]
    u64=lambda pc:struct.unpack('<Q',uc.mem_read(pc,8))[0]
    events=[];logs=[];writes=[];barriers=0;last_store_barrier=-1;ended=False;aborted=False;stopped=False
    maps=[];allocations=[];corrupt=corrupt_apply;phase='init';last_write={}
    saved={UC_ARM64_REG_X19+i:0xabcde000+i for i in range(10)};saved[UC_ARM64_REG_X29]=0xabcde029
    cs=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
    def string(pc):
        text=bytearray()
        while True:
            b=uc.mem_read(pc,1)[0];pc+=1
            if not b:return text.decode()
            text.append(b);assert len(text)<100
    def callback(uc,pc,size,unused):
        nonlocal barriers,ended,stopped
        if pc==RETURN:ended=True;uc.emu_stop();return
        if QUIESCE<=pc<0xfffffff0074d1e74:
            ins=list(cs.disasm(bytes(uc.mem_read(pc,4)),pc))
            if ins and ins[0].mnemonic=='dsb':
                assert ins[0].op_str=='sy';barriers+=1
            return
        name=next((n for n,v in bindings.items() if pc==v),None)
        assert name is not None,('unexpected native call',hex(pc))
        x=[uc.reg_read(r) for r in [UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2]]
        if name=='PE_parse_boot_argn':
            assert string(x[0])=='lmi_cpu' and x[2]==4
            uc.mem_write(x[1],struct.pack('<I',mode));uc.reg_write(UC_ARM64_REG_X0,int(mode!=0))
        elif name=='IOMallocAligned':
            assert x[:2]==[640,16];allocations.append(x[0]);uc.reg_write(UC_ARM64_REG_X0,0 if allocation_fail else HEAP)
        elif name=='bzero':
            assert x[:2]==[HEAP,640];uc.mem_write(HEAP,b'\0'*640)
        elif name=='memcpy':
            assert x[2]==40;uc.mem_write(x[0],bytes(uc.mem_read(x[1],x[2])))
        elif name=='ml_io_map':
            assert x[1]==4096 and x[0] in [0x18591000+i*4096 for i in range(3)]
            domain=(x[0]-0x18591000)//4096;maps.append(domain)
            uc.reg_write(UC_ARM64_REG_X0,0 if domain==map_fail else MMIO+domain*4096)
        elif name=='lmi_frame_emit':
            tag=string(x[0]);assert tag.startswith('LMI_CPU_EPSS_') and x[2]<=10
            values=list(struct.unpack('<'+str(x[2])+'Q',uc.mem_read(x[1],x[2]*8)))
            logs.append((tag,values))
        elif name=='lmi_timing_cleanup':
            assert phase=='restore';events.append('original-display-cleanup');stopped=True
        else:raise AssertionError(name)
        uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_X30))
    def write(uc,access,address,size,value,unused):
        nonlocal last_store_barrier,aborted
        if MMIO<=address<MMIO+3*4096:
            i=(address-MMIO)//4096;assert address-MMIO-i*4096==0x320 and size==4
            assert u64(STATE)==HEAP and u32(HEAP+PREPARED)==1 and u32(HEAP+DIRTY)&(1<<i)
            assert barriers>last_store_barrier;last_store_barrier=barriers
            assert value in [original[i],2];writes.append((phase,i,value));last_write[i]=value
            if phase=='restore':assert stopped
            if interrupt and not aborted and phase=='init':aborted=True;uc.emu_stop()
        else:
            assert (STACK<=address and address+size<=STACK+16384 or HEAP<=address and address+size<=HEAP+640 or STATE<=address and address+size<=STATE+8),hex(address)
    def read(uc,access,address,size,value,unused):
        nonlocal corrupt
        if MMIO<=address<MMIO+3*4096:
            i=(address-MMIO)//4096;offset=address-MMIO-i*4096
            assert size==4 and (offset==0x320 or 0x100<=offset<0x1a0 and offset%4==0)
            if offset==0x320 and i in last_write:
                if phase=='init' and corrupt and last_write[i]==2:
                    uc.mem_write(address,struct.pack('<I',original[i]));corrupt=False
                elif phase=='restore' and restore_fail:
                    uc.mem_write(address,struct.pack('<I',2))
    uc.hook_add(UC_HOOK_CODE,callback);uc.hook_add(UC_HOOK_MEM_WRITE,write);uc.hook_add(UC_HOOK_MEM_READ,read)
    def call(pc):
        nonlocal ended
        ended=False
        uc.reg_write(UC_ARM64_REG_SP,STACK+8192);uc.reg_write(UC_ARM64_REG_X30,RETURN)
        for reg,value in saved.items():uc.reg_write(reg,value)
        uc.emu_start(pc,RETURN+4,count=100000)
        if not ended:return False
        assert uc.reg_read(UC_ARM64_REG_SP)==STACK+8192
        for reg,value in saved.items():assert uc.reg_read(reg)==value,reg
        return True
    complete=call(INIT);assert complete or interrupt and aborted
    n=len(writes);phase='restore'
    syms=json.loads((FOLDER/'runtime-symbols.json').read_text())
    assert call(syms['lmi_epss_native_cleanup']) and stopped
    after=[u32(MMIO+i*4096+0x320) for i in range(3)]
    if not restore_fail:assert after==original and (not u64(STATE) or u32(HEAP+DIRTY)==0)
    return dict(logs=logs,writes=writes,maps=maps,allocations=allocations,
                init_completed=complete,requests_after=after,barriers=barriers,
                dirty=u32(HEAP+DIRTY) if u64(STATE) else 0,apply_writes=n,events=events)


def main(attempt):
    assert re.fullmatch('[a-z]',attempt)
    out=ROOT/('out/lmi-cpu-epss/native-'+attempt);assert not out.exists();out.mkdir()
    raw=(FOLDER/'mach.development.bcm2837').read_bytes();baseline=BASE.read_bytes()
    audit=json.loads((FOLDER/'build-audit.json').read_text());assert sha(BASE)==audit['base_sha256'] and sha(FOLDER/'mach.development.bcm2837')==audit['sha256']
    restored=bytearray(raw)
    for a,z in audit['allowed_file_ranges']:restored[a:z]=baseline[a:z]
    assert restored==baseline and len(raw)==len(baseline)
    for row in audit['hooks']:
        pc=int(row['pc'],16);ins=list(Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(raw[pc-KB:pc-KB+4],pc))
        expected='bl' if row['symbol']=='lmi_epss_native_cleanup' else 'b'
        assert len(ins)==1 and ins[0].mnemonic==expected and int(ins[0].op_str[1:],16)==int(row['target'],16)
    cases=[]
    def check(name,**options):
        result=run(raw,**options);cases.append(dict(name=name,**result));return result
    r=check('default-disabled',mode=0);assert not r['writes']+r['maps']+r['allocations']+r['logs']
    r=check('invalid-mode',mode=3);assert not r['writes']+r['maps']+r['allocations']+r['logs']
    r=check('read-only',mode=1);assert len(r['maps'])==3 and not r['writes']
    r=check('apply-all-and-restore');assert len(r['writes'])==6 and r['apply_writes']==3
    request=[v for tag,v in r['logs'] if tag=='LMI_CPU_EPSS_REQUEST'];assert [v[4] for v in request]==CAPS and all(v[5]==2 and v[6]==2 for v in request)
    r=check('allocation-failure',allocation_fail=True);assert not r['writes']+r['maps']
    for i in range(3):
        r=check('map-failure-'+str(i),map_fail=i);assert not r['writes'] and len(r['maps'])==i+1
    r=check('unsupported-core-count',unsupported=True);assert not r['writes'] and len(r['maps'])==1
    r=check('apply-readback-mismatch',corrupt_apply=True);assert r['apply_writes']==2 and r['dirty']==0
    r=check('already-at-target',already_top=True);assert not r['writes']
    r=check('restore-fails-bounded',restore_fail=True);assert len(r['writes'])==12 and r['dirty']==7
    r=check('return-during-first-store',interrupt=True);assert not r['init_completed'] and r['dirty']==0
    paths=[Path(__file__),BASE,FOLDER/'mach.development.bcm2837',FOLDER/'build-audit.json']
    report=dict(result='PASS',scenarios=len(cases),cases=cases,kernel_sha256=audit['sha256'],
        actual_final_arm64_executed=True,independent_instruction_decode=True,entry_veneers_verified=True,
        whole_image_outside_cpu_helpers_and_cleanup_hook_exact=True,stack_and_callee_saved_verified=True,
        original_display_cleanup_called_before_cpu_restore=True,
        dirty_journal_before_mmio_store=True,only_perf_state_written=True,bounded_restore_failure=True,
        interrupted_apply_recovery=True,no_ddr_mmio=True,
        hardware_tested=False,performance_verified=False,measured_cpu_frequency=None,
        limitation='Native services and EPSS memory are models; no real SMP stop, hardware timing or thermal policy is proven.',
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in paths})
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS:',len(cases),'final ARM64 entry/IO/restore/ABI scenarios')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--attempt',default='a');main(p.parse_args().attempt)
