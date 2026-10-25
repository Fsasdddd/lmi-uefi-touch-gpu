"""Exercise the actual assembled SMP return guard, including refused returns.

Unicorn only supplies firmware/PSCI and native stop/log calls; the guard,
register preservation, branches and all seven affinity checks execute as ARM64.
This is an offline check, not evidence that lmi secondary CPUs have booted.
"""
from pathlib import Path
import hashlib, importlib.util, json, re, struct, sys

r=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(r/'out/lmi-smp-host-deps'))
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X21, UC_ARM64_REG_X22, UC_ARM64_REG_X23, UC_ARM64_REG_X24, UC_ARM64_REG_X29, UC_ARM64_REG_X30

k=r/'out/lmi-kernel-ios-continue'
raw=(k/'mach.development.bcm2837').read_bytes()
meta=json.loads((k/'manifest.json').read_text())
assert meta['smp_cpus']>1 and hashlib.sha256(raw).hexdigest()==meta['sha256']
source=r/meta['smp_return']['source']
assert hashlib.sha256(source.read_bytes()).hexdigest()==meta['smp_return']['source_sha256']
symbols={v[2]:int(v[0],16) for line in (r/'out/kernel-symbols.txt').read_text().splitlines() if len(v:=line.split())==3}
labels={name:int(pc,16) for pc,name in re.findall(r'^([0-9a-f]+) <([^>]+)>:',(k/'probe-disassembly.txt').read_text(),re.M)}
code=(k/'smp-return.bin').read_bytes();base=labels['smp_return_redirect'];end=base+len(code)
assert base==symbols['_ExceptionVectorsBase']+0x800 and end<=symbols['el1_sp0_synchronous_vector_long']

# Independent reference audit of the original NOP tail, outside all sixteen
# architectural vector slots. Source locore.s aligns to 4KiB after EL0_64.
spec=importlib.util.spec_from_file_location('padding',r/'tools/audit-lmi-gpu-padding.py')
padding=importlib.util.module_from_spec(spec);spec.loader.exec_module(padding)
original=(r/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel/mach.development.bcm2837').read_bytes()
assert hashlib.sha256(original).hexdigest()==padding.KERNEL_SHA
segments=[];sections=[];at=32
for _ in range(struct.unpack_from('<I',original,16)[0]):
    cmd,size=struct.unpack_from('<II',original,at)
    if cmd==25:
        va,vs,fo,fs,mp,ip,n=struct.unpack_from('<4Q3I',original,at+24)
        segments.append((va,fo,fs,ip))
        for i in range(n):
            p=at+72+80*i;name=original[p:p+16].split(b'\0')[0].decode()
            a,z,o=struct.unpack_from('<QQI',original,p+32);fl=struct.unpack_from('<I',original,p+64)[0]
            sections.append((name,a,z,o,fl))
    at+=size
def offset(address,size):
    s=next(s for s in segments if s[0]<=address and address+size<=s[0]+s[2])
    assert s[3]==5
    return s[1]+address-s[0]
off=offset(base,len(code))
assert original[off:off+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
assert raw[off:off+len(code)]==code
padding.START=base
branches,addresses,pages=padding.scan_references(original,sections,END=end)
assert not branches and not addresses
assert not any(base<=int(v[0],16)<end for line in (r/'out/kernel-symbols.txt').read_text().splitlines() if len(v:=line.split())==3)
assert not any(base<=struct.unpack_from('<Q',original,p)[0]<end for p in range(0,len(original)-7,4))
# The native handoff/stop code is an unchanged dependency of the guard.
psci_start=symbols['_psci_smp_stop_others'];psci_end=symbols['_psci_smp_note']
native_off=offset(psci_start,psci_end-psci_start)
assert raw[native_off:native_off+psci_end-psci_start]==original[native_off:native_off+psci_end-psci_start]

stack=0x2000000;returned=0x3000000
logline=symbols['_loader_log_line'];loghex=labels['smp_log_hex'];online=symbols['_processor_avail_count']
registers=[UC_ARM64_REG_X19,UC_ARM64_REG_X20,UC_ARM64_REG_X21,UC_ARM64_REG_X22,UC_ARM64_REG_X29]
def run_guard(boot,states,*,frequency=19200000,start_ticks=0,tick_step=1920000):
    uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);mapped=set()
    for address in [base,logline,loghex,online,psci_start,returned]:
        page=address&~4095
        if page not in mapped:uc.mem_map(page,4096);mapped.add(page)
    uc.mem_map(stack,16384);uc.mem_write(base,code);uc.mem_write(online,struct.pack('<I',meta['smp_cpus']))
    uc.reg_write(UC_ARM64_REG_SP,stack+8192);uc.reg_write(UC_ARM64_REG_X30,returned)
    saved={reg:0xabcdef000+reg for reg in registers}
    for reg,value in saved.items():uc.reg_write(reg,value)
    logs=[];queried=[];result=[];stops=[];ticks=[start_ticks];reads={}
    def hook(uc,pc,size,_):
        word=struct.unpack('<I',uc.mem_read(pc,4))[0]
        if pc in (logline,loghex,psci_start):
            if pc==logline:
                value=bytes(uc.mem_read(uc.reg_read(UC_ARM64_REG_X0),80)).split(b'\0')[0].decode()
                logs.append(value)
            elif pc==psci_start:stops.append(pc)
            uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_X30));return
        if pc==returned:result.append('returned');uc.emu_stop();return
        if word&~31==0xd53800a0: # MRS MPIDR_EL1
            assert word&31==20
            uc.reg_write(UC_ARM64_REG_X20,boot);uc.reg_write(UC_ARM64_REG_PC,pc+4)
        elif word==0xd4000003: # SMC
            assert uc.reg_read(UC_ARM64_REG_X0)==0xc4000004
            target=uc.reg_read(UC_ARM64_REG_X1);queried.append(target)
            value=states.get(target,1)
            if isinstance(value,(list,tuple)):
                index=reads.get(target,0);reads[target]=index+1
                value=value[min(index,len(value)-1)]
            uc.reg_write(UC_ARM64_REG_X0,value&((1<<64)-1));uc.reg_write(UC_ARM64_REG_PC,pc+4)
        elif word&~31 in (0xd53be040,0xd53be000): # MRS CNTVCT_EL0 / CNTFRQ_EL0
            counter=word&~31==0xd53be040
            value=ticks[0] if counter else frequency
            uc.reg_write(UC_ARM64_REG_X0+(word&31),value&((1<<64)-1))
            if counter:ticks[0]+=tick_step
            uc.reg_write(UC_ARM64_REG_PC,pc+4)
        elif word==0xd503207f:result.append('held');uc.emu_stop()
    def wrote(uc,access,address,size,value,_):assert stack<=address<stack+16384
    uc.hook_add(UC_HOOK_CODE,hook);uc.hook_add(UC_HOOK_MEM_WRITE,wrote)
    uc.emu_start(labels['smp_return_prepare'],returned+4,count=10000)
    assert result and len(stops)==1
    if result==['returned']:
        assert all(uc.reg_read(reg)==value for reg,value in saved.items())
        assert uc.reg_read(UC_ARM64_REG_SP)==stack+8192
        assert 'LMI_SMP_OTHER_CORES_OFF\n' in logs
    else:
        assert 'LMI_SMP_RETURN_HELD\n' in logs and 'LMI_SMP_OTHER_CORES_OFF\n' not in logs
    return result,queried

positive=negative=delayed=transition_errors=0
for boot in range(0,0x800,0x100):
    result,queried=run_guard(boot,{})
    assert result==['returned'] and queried==[x for x in range(0,0x800,0x100) if x!=boot];positive+=1
    for target in range(0,0x800,0x100):
        if target==boot:continue
        for state in (0,2,-1,-2,-3):
            result,queried=run_guard(boot,{target:state})
            assert result==['held'] and queried[-1]==target;negative+=1
        for transition in ([0,1],[2,1],[0,2,0,1]):
            result,queried=run_guard(boot,{target:transition})
            assert result==['returned'] and queried.count(target)==len(transition);delayed+=1
        for transition in ([0,-1],[2,-2],[0,3],[2,0xffffffffffffffff]):
            result,queried=run_guard(boot,{target:transition})
            assert result==['held'] and queried.count(target)==len(transition);transition_errors+=1
extra_cases=0
for boot in range(0,0x800,0x100):
    target=0x100 if boot==0 else 0
    for frequency in (0,24000000,19200001):
        result,queried=run_guard(boot,{target:[0,1]},frequency=frequency)
        assert result==['held'] and queried.count(target)==1;extra_cases+=1
    result,queried=run_guard(boot,{target:[0,2,1]},start_ticks=(1<<64)-100)
    assert result==['returned'] and queried.count(target)==3;extra_cases+=1
    # A shared budget must not restart for each CPU. The third pending core
    # reaches one second even though each individual transition would be short.
    targets=[x for x in range(0,0x800,0x100) if x!=boot]
    result,queried=run_guard(boot,{x:[0,0,0,0,1] for x in targets})
    assert result==['held'] and queried[-1]==targets[2];extra_cases+=1
redirect_cases=0
for checkpoint in (62,63):
    uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);pages=set()
    slot=symbols['_loader_stub_slot']+16
    resume=symbols['_loader_return']+4
    for address in (base,slot,labels['ram_timer'],resume):
        page=address&~4095
        if page not in pages:uc.mem_map(page,4096);pages.add(page)
    uc.mem_map(stack,16384);uc.mem_write(base,code);uc.mem_write(slot,struct.pack('<Q',checkpoint))
    uc.reg_write(UC_ARM64_REG_SP,stack+8192)
    uc.reg_write(UC_ARM64_REG_X23,0x11223344);uc.reg_write(UC_ARM64_REG_X24,0x55667788)
    reached=[]
    def redirect_hook(uc,pc,size,_):
        if pc in (labels['ram_timer'],resume):reached.append(pc);uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE,redirect_hook)
    uc.emu_start(base,base+len(code),count=20)
    if checkpoint==63:
        assert reached==[labels['ram_timer']] and uc.reg_read(UC_ARM64_REG_SP)==stack+8192
    else:
        assert reached==[resume] and uc.reg_read(UC_ARM64_REG_SP)==stack+8192-64
        assert bytes(uc.mem_read(stack+8192-64,16))==struct.pack('<QQ',0x55667788,0x11223344)
    redirect_cases+=1
# Execute the formatter rather than mocking it: the native sink must receive
# exactly one complete lowercase hex line per invocation, using only stack RAM.
import random
rng=random.Random(650)
hex_values=[0,(1<<64)-1,0x0123456789abcdef,0xfedcba9876543210]
hex_values += [n<<(4*n) for n in range(16)]
hex_values += [rng.getrandbits(64) for _ in range(64)]
for value in hex_values:
    uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);mapped=set()
    for address in [base,logline,returned]:
        page=address&~4095
        if page not in mapped:uc.mem_map(page,4096);mapped.add(page)
    uc.mem_map(stack,16384);uc.mem_write(base,code)
    uc.reg_write(UC_ARM64_REG_SP,stack+8192);uc.reg_write(UC_ARM64_REG_X30,returned)
    uc.reg_write(UC_ARM64_REG_X29,0x12345678);uc.reg_write(UC_ARM64_REG_X0,value)
    lines=[]
    def hex_hook(uc,pc,size,_):
        if pc==logline:
            pointer=uc.reg_read(UC_ARM64_REG_X0)
            assert pointer==stack+8192-48+16
            lines.append(bytes(uc.mem_read(pointer,18)))
            uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_X30))
        elif pc==returned:uc.emu_stop()
    def hex_write(uc,access,address,size,value,_):assert stack+8192-48<=address and address+size<=stack+8192
    uc.hook_add(UC_HOOK_CODE,hex_hook);uc.hook_add(UC_HOOK_MEM_WRITE,hex_write)
    uc.emu_start(loghex,returned+4,count=1000)
    assert lines==[f'{value:016x}\n\0'.encode()]
    assert uc.reg_read(UC_ARM64_REG_SP)==stack+8192 and uc.reg_read(UC_ARM64_REG_X29)==0x12345678
def touch_machine():
    uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);mapped=set()
    for address in [base,logline,returned]:
        page=address&~4095
        if page not in mapped:uc.mem_map(page,4096);mapped.add(page)
    uc.mem_map(stack,16384);uc.mem_write(base,code)
    uc.reg_write(UC_ARM64_REG_SP,stack+8192);uc.reg_write(UC_ARM64_REG_X30,returned)
    for reg,value in [(UC_ARM64_REG_X19,0x1234),(UC_ARM64_REG_X20,0x5678),(UC_ARM64_REG_X29,0x9abc)]:uc.reg_write(reg,value)
    def touch_write(uc,access,address,size,value,_):assert stack+8192-48<=address and address+size<=stack+8192
    uc.hook_add(UC_HOOK_MEM_WRITE,touch_write)
    return uc
def touch_preserved(uc):
    assert uc.reg_read(UC_ARM64_REG_SP)==stack+8192
    assert [uc.reg_read(reg) for reg in (UC_ARM64_REG_X19,UC_ARM64_REG_X20,UC_ARM64_REG_X29)]==[0x1234,0x5678,0x9abc]
touch_poll_cases=0
for tick in (0,1,255,256,512,3999):
    uc=touch_machine();logs=[];hexes=[];data=0x4000000+4093
    if tick%256==0:
        uc.mem_map(data&~4095,4096);uc.mem_write(data,b'\x12\x34\x56')
    uc.reg_write(UC_ARM64_REG_X0,data);uc.reg_write(UC_ARM64_REG_X1,tick)
    def poll_hook(uc,pc,size,_):
        if pc==returned:uc.emu_stop();return
        if pc==logline:logs.append(bytes(uc.mem_read(uc.reg_read(UC_ARM64_REG_X0),64)).split(b'\0')[0])
        elif pc==loghex:hexes.append(uc.reg_read(UC_ARM64_REG_X0))
        elif struct.unpack('<I',uc.mem_read(pc,4))[0]==0xd53800a0:
            uc.reg_write(UC_ARM64_REG_X0,0x700);uc.reg_write(UC_ARM64_REG_PC,pc+4);return
        else:return
        uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_X30))
    uc.hook_add(UC_HOOK_CODE,poll_hook);uc.emu_start(labels['smp_touch_poll'],returned+4,count=100)
    assert logs==([b'LMI_TOUCH_SMP_POLL\n'] if tick%256==0 else [])
    assert hexes==([tick,0x123456,0x700] if tick%256==0 else [])
    touch_preserved(uc);touch_poll_cases+=1
report=dict(result='PASS',positive=positive,refused_return_cases=negative,guard_bytes=len(code),guard_base=hex(base),
    delayed_off_cases=delayed,transition_error_cases=transition_errors,deadline_frequency_wrap_cases=extra_cases,
    atomic_hex_cases=len(hex_values),
    touch_poll_cases=touch_poll_cases,
    redirect_cases=redirect_cases,
    original_padding_no_references=True,native_stop_code_unchanged=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    kernel_sha256=meta['sha256'],hardware_smp_verified=False)
(r/'out/lmi-smp-return-host-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
