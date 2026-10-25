"""Exact owned-tile proof, preserving the authenticated normal-mode proof."""
from pathlib import Path
import re,runpy,struct,zlib

# Independently specified Mesa24.3 A650 stream, including sequence writes.
COMMANDS=[
    0x70e50001,12,0x70268000,0x408e0701,0x18000000,
    0x48840502,0,0xf000f,0x488c2c04,0x33,0x66,0xcc,0xff,
    0x408c0001,0x10f03080,0x48840001,0x10f03080,0x48acc001,0xf180,
    0x488c0101,0,0x408c1704,0x430,0x1010100,0,1,
    0x70268000,0x408e0401,0x04100000,0x702c0001,3,0x70268000,0x408e0401,0,
    0x70460004,0x1d,0x1010008,0,0x650c0101,
    0x70460004,4,0x101000c,0,0x650c0102,
    0x70268000,0x703d8003,0x1010010,0,0x650c0de3]

def verify(log,firmware,window=None):
    begin='LMI_GPU_TILE_BEGIN\n';end='LMI_GPU_TILE_RESULT\n0000000000000001\n'
    assert log.count(begin)==log.count('LMI_GPU_TILE_RESULT\n')==log.count(end)==1
    a=log.index(begin);b=log.index(end)+len(end);assert a<b
    result=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-unsecure.py')))['verify'](log[:a]+log[b:],firmware,window)
    assert result['mode']==46 and result['normal_mode_execution_verified']
    assert log.index('LMI_GPU_NORMAL_RESULT\n0000000000000001\n')<a<b<=log.index('LMI_GPU_CORE_MEMORY_RESULT\n')
    scope=log[a:b]
    def rows(marker,count):
        assert log.count(marker+'\n')==1,marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',scope);assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    assert rows('LMI_GPU_TILE_BEGIN',1)==[0x7eabe04b]
    assert rows('LMI_GPU_TILE_PACKET',50)==[49,*COMMANDS]
    assert rows('LMI_GPU_TILE_FENCES',5)==[0x650c0de1,0x650c0de2,0x650c0101,0x650c0102,0x650c0de3]
    crc=zlib.crc32(struct.pack('<I',0xff3366cc)*256)
    assert rows('LMI_GPU_TILE_PIXELS',3)==[256,0,crc]
    snapshots=list(re.finditer(r'LMI_GPU_CP_STATUS\n((?:[0-9a-f]{16}\n){14})',scope))
    assert len(snapshots)==scope.count('LMI_GPU_CP_STATUS\n')==2
    for m,target in zip(snapshots,[19,68]):
        v=[int(x,16) for x in m[1].splitlines()];assert v[0]==target
        assert [x>>32 for x in v[1:9]]==[0x3d00000+4*n for n in [0x210,0x201,0x806,0x807,0x808,0x821,0x823,0x824]]
        s=[x&0xffffffff for x in v[1:9]]
        assert not s[0]&~1 and s[1]==0 and s[2:5]==[target,target,1] and s[5:]==[0,0,0]
        assert [x>>32 for x in v[9:]]==[0x3da9058,0x3da9060,0x3da9064,0x3da9068,0x3da0048]
        assert v[9]&0xffffffff==0x400 and v[13]&0xffffffff==0
    assert scope.count('LMI_GPU_TILE_VERIFIED_HELD\n')==1
    ordered=[0,snapshots[0].start(),scope.index('LMI_GPU_TILE_PACKET\n'),snapshots[1].start(),
             scope.index('LMI_GPU_TILE_FENCES\n'),scope.index('LMI_GPU_TILE_PIXELS\n'),
             scope.index('LMI_GPU_TILE_VERIFIED_HELD\n'),scope.index('LMI_GPU_TILE_RESULT\n')]
    assert ordered==sorted(ordered)
    result.update(gpu_tile_pixels_verified=True,gpu_tile=dict(width=16,height=16,pitch=64,
        iova='0x1010100',pixel='0xff3366cc',pixels=256,crc32=f'{crc:08x}',
        scratch_words_checked=384,guards_bytes_each=128,final_rptr=68),
        desktop_acceleration_verified=False,hardware_acceleration_verified=False)
    return result
