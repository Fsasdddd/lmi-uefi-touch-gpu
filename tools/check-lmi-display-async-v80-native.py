"""Execute actual linked ARM64 show/worker code, interleaving saved CPUs.

Only external OS, GPU-copy and DPU services are modeled. The real frozen
pipeline and timing code are separately exercised by the pthread integration
test. Neither test proves physical display completion, shutdown or FPS.
"""
from pathlib import Path
from importlib.machinery import SourceFileLoader
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'out/lmi-smp-host-deps'))
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X19,UC_ARM64_REG_X29,UC_ARM64_REG_X30,UC_ARM64_REG_PC,UC_ARM64_REG_SP
helper=SourceFileLoader('v73_build_native',str(ROOT/'tools/build-lmi-display-timing-v73.py')).load_module()
FOLDER=ROOT/'out/lmi-display-async-v80a'
OUT=ROOT/'out/lmi-display-async-v80-native-a'
names=['fast_bytes','stats_bytes','ctx','lock','owner','native','ticket','pending','attempted','started','failed',
       'enqueued','submitted','completed','waits','polls','failures','pipeline','compositor','pstate','pticket','scanning']
layout_section=helper.elf(OUT/'layout.o')['.rodata'][1]
L=dict(zip(names,struct.unpack('<'+'Q'*len(names),layout_section)))
symbols=json.loads((FOLDER/'runtime-symbols.json').read_text())
audit=json.loads((FOLDER/'build-audit.json').read_text())
raw=(FOLDER/'mach.development.bcm2837').read_bytes()
assert hashlib.sha256(raw).hexdigest()==audit['sha256']
KBASE=0xfffffff007004000
STATS,NATIVE,RETURN,LOCK,THREAD=0x3000000,0x4000000,0x2000000,0x6000000,0x6100000
MASK=(1<<64)-1


class Machine:
    def __init__(self,**options):
        self.u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
        self.u.mem_map(KBASE,(len(raw)+4095)&~4095);self.u.mem_write(KBASE,raw)
        for a,n in [(STATS,65536),(NATIVE,131072),(RETURN,4096),(0x1000000,65536),(0x1100000,65536),(0x1200000,65536),(0x5000000,4096)]:
            self.u.mem_map(a,n)
        self.options=options;self.locked=False;self.now=1000;self.serial=0;self.allow=False
        self.calls=[];self.thread=None;self.clean=False;self.emitted=None;self.tasks=[]
        self.ctx=STATS+L['ctx'];self.pipeline=NATIVE+L['pipeline'];self.current=None
        self.w64(symbols['lmi_fast_state'],STATS)
        self.w64(symbols['lmi_async_native_state'],NATIVE)
        self.w32(symbols['lmi_async_native_state']+20,options.get('done',2))
        self.w32(self.pipeline+L['scanning'],0xffffffff)
        self.u.hook_add(UC_HOOK_CODE,self.hook)

    def r32(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
    def r64(self,a):return struct.unpack('<Q',self.u.mem_read(a,8))[0]
    def w32(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
    def w64(self,a,v):self.u.mem_write(a,struct.pack('<Q',v&MASK))
    def field(self,name):return self.r64(self.ctx+L[name])
    def new(self,name,entry,*args):
        slot=len(self.tasks);assert slot<3
        sp=0x1000000+slot*0x100000+32768
        self.u.reg_write(UC_ARM64_REG_SP,sp)
        self.u.reg_write(UC_ARM64_REG_X30,RETURN)
        saved={UC_ARM64_REG_X19+n:0xabc000+n for n in range(10)}
        saved[UC_ARM64_REG_X29]=0xabc029
        for reg,v in saved.items():self.u.reg_write(reg,v)
        for n,v in enumerate(args):self.u.reg_write(UC_ARM64_REG_X0+n,v)
        self.u.reg_write(UC_ARM64_REG_PC,entry)
        t=dict(name=name,context=self.u.context_save(),state='new',sp=sp,saved=saved)
        self.tasks.append(t);return t
    def run(self,t):
        self.current=t;self.u.context_restore(t['context'])
        if t['state']=='sleep':assert not self.locked;self.locked=True
        t['state']='running'
        self.u.emu_start(self.u.reg_read(UC_ARM64_REG_PC),RETURN+4,count=20000)
        assert t['state']!='running','unbounded native loop'
        t['context']=self.u.context_save()
        if t['state']=='returned':
            assert self.u.reg_read(UC_ARM64_REG_SP)==t['sp']
            for reg,v in t['saved'].items():assert self.u.reg_read(reg)==v
        return t['state']
    def show(self,slot=0):
        # This address may be unmapped after show returns; worker owns no source.
        if slot==0:
            t=self.new('presenter',symbols['lmi_async_show'],0x777,0x5000000,0x5000100)
        else:
            t=self.tasks[slot]
            assert t['state']=='returned'
            t['context']=self.recall(t,symbols['lmi_async_show'],0x777,0x5000000,0x5000100)
        return t,self.run(t)
    def recall(self,t,entry,*args):
        self.u.context_restore(t['context']);self.u.reg_write(UC_ARM64_REG_PC,entry)
        self.u.reg_write(UC_ARM64_REG_X30,RETURN)
        for n,v in enumerate(args):self.u.reg_write(UC_ARM64_REG_X0+n,v)
        return self.u.context_save()
    def hook(self,u,pc,size,unused):
        if pc==RETURN:
            self.current['state']='returned';self.current['value']=u.reg_read(UC_ARM64_REG_X0);u.emu_stop();return
        external={v:k for k,v in audit['bindings'].items()}
        binding=next((name for value,name in external.items() if int(value,16)==pc),None)
        if binding is None:return
        a=[u.reg_read(UC_ARM64_REG_X0+n) for n in range(6)];result=0;pause=None
        self.calls.append(binding)
        if binding=='IOMallocAligned':
            assert a[:2]==[L['stats_bytes'],16];result=STATS
        elif binding=='bzero':
            assert a[:2]==[STATS,L['stats_bytes']];u.mem_write(STATS,bytes(a[1]))
        elif binding=='IOLockAlloc':result=0 if self.options.get('lock_fail') else LOCK
        elif binding=='IOLockLock':assert a[0]==LOCK and not self.locked;self.locked=True
        elif binding=='IOLockUnlock':assert a[0]==LOCK and self.locked;self.locked=False
        elif binding=='IOLockWakeup':assert a[:3]==[LOCK,self.ctx,0] and self.locked
        elif binding=='IOLockSleep':
            assert a[:3]==[LOCK,self.ctx,1] and self.locked;self.locked=False;pause='sleep'
        elif binding=='delay':assert a[0]==50 and not self.locked;self.now+=960;pause='delay'
        elif binding=='IOSleep':assert a[0]==1000 and not self.locked;pause='parked'
        elif binding=='kernel_thread_start':
            assert a[1]==self.ctx
            if self.options.get('thread_fail'):result=5
            else:self.thread=(a[0],a[1]);self.w64(a[2],THREAD)
        elif binding=='thread_deallocate':assert a[0]==THREAD
        elif binding=='lmi_frame_ticks':self.now+=100;result=self.now
        elif binding=='lmi_async_original_show':assert not self.locked
        elif binding=='lmi_timing_frame':
            assert self.locked and a[:2]==[NATIVE+L['compositor'],self.pipeline]
            if self.options.get('frame_failure'):result=-1&MASK
            else:
                n=next(n for n in range(2) if self.r32(self.pipeline+L['pstate']+4*n)==0)
                self.serial+=1;self.w32(self.pipeline+L['pstate']+4*n,2)
                self.w64(self.pipeline+L['pticket']+8*n,self.serial)
                self.w32(a[4],n);self.w64(a[5],self.serial);result=1
        elif binding=='lmi_timing_submit':
            p,n,ticket,now=a[:4]
            assert self.locked and p==self.pipeline and n<2
            assert self.r32(p+L['scanning'])==0xffffffff and self.r32(p+L['pstate']+4*n)==2
            assert self.r64(p+L['pticket']+8*n)==ticket and ticket>0
            if not self.options.get('submit_failure'):
                self.w32(p+L['scanning'],n);self.w32(p+L['pstate']+4*n,3);result=1
        elif binding=='lmi_pipeline_poll':
            assert self.locked and a[0]==self.pipeline
            n=self.r32(self.pipeline+L['scanning']);assert n<2
            if self.options.get('poll_failure'):result=-1&MASK
            elif self.allow:
                self.w32(self.pipeline+L['pstate']+4*n,0);self.w32(self.pipeline+L['scanning'],0xffffffff);result=1
        elif binding=='lmi_async_original_cleanup':assert not self.locked;self.clean=True
        elif binding=='lmi_frame_emit':
            assert self.clean and a[2]==10
            assert bytes(u.mem_read(a[0],14))==b'LMI_DPU_ASYNC\x00'
            self.emitted=list(struct.unpack('<10Q',u.mem_read(a[1],80)))
        else:raise AssertionError(binding)
        u.reg_write(UC_ARM64_REG_X0,result);u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_X30))
        if pause:self.current['state']=pause;u.emu_stop()


def main():
    cases=[]
    for size,alignment,expected in [(L['fast_bytes'],16,STATS),(L['fast_bytes']+8,16,0),(L['fast_bytes'],32,0)]:
        m=Machine();t=m.new('allocate',symbols['lmi_async_allocate'],size,alignment)
        assert m.run(t)=='returned' and t['value']==expected;cases.append('allocation-'+str(expected)+'-'+str(alignment))
    for opts in [dict(done=1),dict(lock_fail=True),dict(thread_fail=True)]:
        m=Machine(**opts);t,state=m.show();assert state=='returned' and not m.thread
        assert m.calls.count('lmi_async_original_show')==1;cases.append(str(opts))

    m=Machine();presenter,state=m.show();assert state=='returned' and m.field('enqueued')==1 and m.thread
    worker=m.new('worker',*m.thread)
    m.u.mem_unmap(0x5000000,4096) # Native worker must never reference retired source memory.
    assert m.run(worker)=='delay' and m.field('submitted')==1
    # The model's frame callback does not dereference the new source either;
    # all source reads reside in the separately frozen GPU/frame code.
    presenter['context']=m.recall(presenter,symbols['lmi_async_show'],0x777,0x5000000,0x5000100)
    assert m.run(presenter)=='returned' and m.field('enqueued')==2
    presenter['context']=m.recall(presenter,symbols['lmi_async_show'],0x777,0x5000000,0x5000100)
    assert m.run(presenter)=='sleep'
    assert m.run(presenter)=='sleep' # Spurious wake must not reuse scanning/ready buffers.
    m.allow=True;assert m.run(worker)=='delay' and m.field('submitted')==2
    assert m.run(presenter)=='returned' and m.field('enqueued')==3
    assert m.run(worker)=='delay' and m.field('submitted')==3
    assert m.run(worker)=='sleep' and m.field('completed')==3
    assert m.r32(m.ctx+L['pending'])==0xffffffff
    cleanup=m.new('cleanup',symbols['lmi_async_cleanup']);assert m.run(cleanup)=='returned'
    assert m.emitted[:6]==[1,1,0,3,3,3] and m.emitted[-1]==MASK
    cases.append('two-interleaved-cpus-spurious-wake-three-frames-idle-flush-retired-source-unmapped-cleanup')

    for option in ['frame_failure','submit_failure','poll_failure']:
        m=Machine(**{option:True});presenter,state=m.show()
        if option=='frame_failure':assert state=='parked' and m.field('enqueued')==0
        else:
            assert state=='returned';worker=m.new('worker',*m.thread)
            state=m.run(worker)
            if option=='poll_failure':assert state=='delay';state=m.run(worker)
            assert state=='parked'
        assert m.r32(m.ctx+L['failed'])==1 and m.field('failures')==1
        cases.append(option+'-retains-state')
    m=Machine();presenter,state=m.show();assert state=='returned'
    m.w32(symbols['lmi_async_native_state']+8,1);worker=m.new('worker',*m.thread)
    assert m.run(worker)=='parked' and m.field('submitted')==0
    assert m.r32(m.ctx+L['pending'])==0
    cases.append('stop-retains-unsubmitted-ready-frame')
    paths=[Path(__file__),ROOT/'tools/lmi-display-async-layout-v80.c',OUT/'layout.o',
           FOLDER/'mach.development.bcm2837',FOLDER/'runtime-symbols.json',FOLDER/'build-audit.json']
    report=dict(result='PASS',scenarios=len(cases),cases=cases,actual_linked_arm64_executed=True,
        two_saved_cpu_contexts_interleaved=True,native_stack_and_callee_saved_abi_verified=True,
        old_source_memory_unmapped_before_worker=True,layout=L,hardware_tested=False,performance_verified=False,
        limitation='External OS, GPU-copy, DPU and PSCI services modeled; physical completion and frame rate are unproven.',
        inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    target=OUT/'result.json';assert not target.exists();target.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS:',len(cases),'actual ARM64 scenarios; interleaved presenter/worker, ABI, buffer pressure and failure retention')


if __name__=='__main__':main()
