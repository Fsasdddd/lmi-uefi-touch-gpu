"""Authenticated A6xx mode packet completion plus distinct GPU writeback.

The inherited mode45 parser covers the prefix and retained-parent suffix.
This parser exclusively validates the bounded normal-mode operation between
NORMAL_BEGIN and NORMAL_RESULT, including all three additional CP snapshots.
"""
from pathlib import Path
import re,runpy

def verify(log,firmware,window=None):
    begin='LMI_GPU_NORMAL_BEGIN\n';end='LMI_GPU_NORMAL_RESULT\n0000000000000001\n'
    assert log.count(begin)==log.count('LMI_GPU_NORMAL_RESULT\n')==log.count(end)==1
    a=log.index(begin);b=log.index(end)+len(end);assert a<b
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-zap-load.py')))['verify'](log[:a]+log[b:],firmware,window)
    assert result['mode']==45 and result['zap_authenticated']
    assert log.index('LMI_GPU_ZAP_LOAD_RESULT\n0000000000000001\n')<a<b<=log.index('LMI_GPU_CORE_MEMORY_RESULT\n')
    scope=log[a:b]
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',scope);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_NORMAL_BEGIN',1)==[0x7eabe044]
    assert rows('LMI_GPU_NORMAL_DIAG_CANARY',1)==[0x7eabe04a]
    prereqs=rows('LMI_GPU_NORMAL_PREREQ_READONLY',17)
    words=[0x842,0xc01,0x8601,0x8e05,0x9e01,0xbe05,0xa601,0x9601,0xe00,0xae01,0xb601,
           0xae,0xb0,0x11b,0x10b,0x118]
    assert [v>>32 for v in prereqs]==[0x3d7e340,*[0x3d00000+4*w for w in words]]
    before_addresses=rows('LMI_GPU_NORMAL_ADDR_BEFORE',10)
    after_addresses=rows('LMI_GPU_NORMAL_ADDR_AFTER',10)
    addresses=[0x3d00000+4*w for w in words[1:11]]
    assert [v>>32 for v in before_addresses]==[v>>32 for v in after_addresses]==addresses
    assert all(v&0xffffffff in (0,1) for v in before_addresses)
    assert all(v&0xffffffff==1 for v in after_addresses)
    assert all(v&0xffffffff==1 for v in prereqs[1:12])
    before,after=rows('LMI_GPU_NORMAL_SP',2)
    force,clock,state=rows('LMI_GPU_NORMAL_CLOCK_POLICY',3)
    assert force in (0,1) and state<=0xffffffff and not state&0xd7
    assert before<=0xffffffff
    assert (clock==0x8aa8aa82 and after==before|1) if force else (clock==0 and before==after==0)
    assert prereqs[0]&0xffffffff==state and prereqs[12]&0xffffffff==clock
    assert rows('LMI_GPU_NORMAL_PACKET',2)==[0x70e60001,0]
    assert rows('LMI_GPU_NORMAL_WRITE_PACKET',4)==[0x703d8003,0x1010004,0,0x650c0de2]
    assert rows('LMI_GPU_NORMAL_FENCE',2)==[0x650c0de1,0x650c0de2]
    snapshots=list(re.finditer(r'LMI_GPU_CP_STATUS\n((?:[0-9a-f]{16}\n){14})',scope))
    assert len(snapshots)==scope.count('LMI_GPU_CP_STATUS\n')==4
    for m,target in zip(snapshots,[13,13,15,19]):
        v=[int(x,16) for x in m[1].splitlines()];assert v[0]==target
        assert [x>>32 for x in v[1:9]]==[0x3d00000+4*n for n in [0x210,0x201,0x806,0x807,0x808,0x821,0x823,0x824]]
        s=[x&0xffffffff for x in v[1:9]]
        assert not s[0]&~1 and s[1]==0 and s[2:5]==[target,target,1] and s[5:]==[0,0,0]
        assert [x>>32 for x in v[9:]]==[0x3da9058,0x3da9060,0x3da9064,0x3da9068,0x3da0048]
        assert v[9]&0xffffffff==0x400 and v[13]&0xffffffff==0
    assert scope.count('LMI_GPU_NORMAL_VERIFIED_HELD\n')==1
    ordered=[0,snapshots[0].start(),scope.index('LMI_GPU_NORMAL_DIAG_CANARY\n'),scope.index('LMI_GPU_NORMAL_ADDR_BEFORE\n'),
             snapshots[1].start(),scope.index('LMI_GPU_NORMAL_ADDR_AFTER\n'),scope.index('LMI_GPU_NORMAL_SP\n'),scope.index('LMI_GPU_NORMAL_CLOCK_POLICY\n'),
             scope.index('LMI_GPU_NORMAL_PREREQ_READONLY\n'),scope.index('LMI_GPU_NORMAL_PACKET\n'),snapshots[2].start(),
             scope.index('LMI_GPU_NORMAL_WRITE_PACKET\n'),snapshots[3].start(),scope.index('LMI_GPU_NORMAL_FENCE\n'),
             scope.index('LMI_GPU_NORMAL_VERIFIED_HELD\n'),scope.index('LMI_GPU_NORMAL_RESULT\n')]
    assert ordered==sorted(ordered)
    result.update(mode=46,secure_mode_packet_sent=True,normal_mode_packet_completed=True,
                  normal_mode_execution_verified=True,normal_mode_writeback_value=0x650c0de2,
                  normal_mode_register_state_observed=False,gpu_secure_mode_changed=True,
                  normal_sp_clock_before=before,normal_sp_clock_after=after,
                  normal_hwcg_enabled=bool(force),normal_sp_force_write_used=bool(force),
                  normal_prereq_observations={hex(v>>32):hex(v&0xffffffff) for v in prereqs},
                  normal_nonsecure_address_modes_verified=True,
                  hardware_acceleration_verified=False)
    return result
