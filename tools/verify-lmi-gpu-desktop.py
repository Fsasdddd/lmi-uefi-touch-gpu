"""Desktop adoption and IB evidence; retain the exact unchanged tile proof.

Service-start is void. READY alone cannot prove registration, GL rendering,
correct screen content, or sustained desktop acceleration.
"""
from pathlib import Path
import re,runpy
CONFIG=[(0x8e08,0x816),(0xb604,6),(0xae02,0x26),(0xe01,0x600000),(0x534,1),
    (0xe05,0xffffffc0),(0xe06,0x1ffff),(0xe07,0xfffff000),(0xe08,0x1ffff),
    (0xe09,0xfffff000),(0xe0a,0x1ffff),(0xe18,0x804),(0xe17,4)]
def verify(log,firmware,window=None):
    # One observed native buttons diagnostic can appear between the RAM marker
    # and its five values on SMP. Recognize only this complete record, with
    # exact boundaries: no arbitrary line filtering or removal of GPU evidence.
    # The raw hardware log remains unchanged in the evidence directory.
    background='buttons: nothing that can be read: no buttons\n'
    interleaved=r'(?m)^LMI_GPU_RAM_SEGMENTS\n'+re.escape(background)+r'((?:[0-9a-f]{16}\n){5})(?=LMI_GPU_RAM_SOFTWARE_WALK_OK\n)'
    log,background_records=re.subn(interleaved,lambda m:'LMI_GPU_RAM_SEGMENTS\n'+m[1],log)
    assert background_records<=1, 'Duplicate interleaved RAM record'
    begin='LMI_GPU_DESKTOP_BEGIN\n';end='LMI_GPU_DESKTOP_RESULT\n0000000000000001\n'
    assert log.count(begin)==log.count('LMI_GPU_DESKTOP_RESULT\n')==log.count(end)==1
    a=log.index(begin);b=log.index(end)+len(end);assert a<b
    scope=log[a:b]
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',scope);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_DESKTOP_BEGIN',1)==[0x7eabe052]
    tables=rows('LMI_GPU_DESKTOP_TABLES',3)
    assert rows('LMI_GPU_DESKTOP_NC',len(CONFIG))==[((0x3d00000+4*k)<<32)|v for k,v in CONFIG]
    assert rows('LMI_GPU_DESKTOP_BIND_FENCE',2)==[72,0x650c0de4]
    assert rows('LMI_GPU_DESKTOP_READY',5)==[0x6050002,1179648,16,1,2]
    snapshots=list(re.finditer(r'LMI_GPU_CP_STATUS\n((?:[0-9a-f]{16}\n){14})',scope))
    assert len(snapshots)==scope.count('LMI_GPU_CP_STATUS\n')==1
    values=[int(v,16) for v in snapshots[0][1].splitlines()]
    addresses=[0x3d00000+4*k for k in [0x210,0x201,0x806,0x807,0x808,0x821,0x823,0x824]]+[0x3da0000+k for k in [0x9058,0x9060,0x9064,0x9068,0x48]]
    assert values[0]==68 and [v>>32 for v in values[1:]]==addresses
    low=[v&0xffffffff for v in values[1:]]
    assert not low[0]&~1 and low[1:9]==[0,68,68,1,0,0,0,0x400] and low[-1]==0
    assert snapshots[0].start()<scope.index('LMI_GPU_DESKTOP_TABLES\n')
    markers=['LMI_GPU_DESKTOP_BEGIN','LMI_GPU_DESKTOP_TABLES','LMI_GPU_DESKTOP_NC','LMI_GPU_DESKTOP_BIND_FENCE','LMI_GPU_DESKTOP_READY','LMI_GPU_DESKTOP_RESULT']
    pos=[scope.index(m+'\n') for m in markers];assert pos==sorted(pos)
    assert log.index('LMI_GPU_TILE_RESULT\n0000000000000001\n')<a<b<=log.index('LMI_GPU_CORE_MEMORY_RESULT\n')
    for marker in ['FAULT_HELD','RELEASE_HELD','REPORT']:
        assert 'LMI_GPU_DESKTOP_'+marker+'\n' not in log,'Desktop runtime failure: '+marker
    # Only remove explicitly decoded, ordered runtime completion records.
    pattern=r'LMI_GPU_DESKTOP_COMPLETED\n((?:[0-9a-f]{16}\n){3})'
    completed=list(re.finditer(pattern,log));assert len(completed)==log.count('LMI_GPU_DESKTOP_COMPLETED\n')
    last=0
    for m in completed:
        fence,rptr,observed=[int(v,16) for v in m[1].splitlines()]
        assert m.start()>log.index('LMI_GPU_DESKTOP_READY\n') and fence>last and rptr<8192 and observed==fence
        assert fence<=4 or fence%16==0
        last=fence
    cleaned=re.sub(pattern,'',log[:a])+re.sub(pattern,'',log[b:])
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-tile.py')))['verify'](cleaned,firmware,window)
    assert tables==result['core_backing_pages'][17:20]
    renderer=re.findall(r'redwood-gl:.*(?:CoreAnimation|Adreno|FD650|A650).*',log)
    result.update(desktop_backend_adopted=True,desktop_binding_gpu_writeback_verified=True,
        interleaved_buttons_records=background_records,
        desktop_completed_fence_samples=len(completed),desktop_last_logged_fence=last,
        desktop_ib_completion_observed=bool(completed),desktop_renderer_log=renderer,
        desktop_acceleration_verified=False,hardware_acceleration_verified=False)
    return result
