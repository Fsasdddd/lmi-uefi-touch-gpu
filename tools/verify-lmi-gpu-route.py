"""Owned live backing and real SID5 stage1 enable/detach, not DMA execution."""
import hashlib,re,struct,zlib

OFFSETS=[0x1800,0x8010,0x8030,0x8020,0x8024,0x8028,0x802c,0x8038,0x803c,
         0x8000,0xc00,0x800,0x1000,0x8058,0x48]

def verify(log,firmware,window=None,active=False):
    def rows(marker,count):
        assert log.count(marker+'\n')==1, 'Missing/duplicate '+marker
        m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',log)
        assert m, 'Incomplete '+marker
        return [int(v,16) for v in m[1].splitlines()]
    assert hashlib.sha256(firmware).hexdigest()=='df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c'
    live=rows('LMI_GPU_RAM_LIVE_MAP',52)
    base,size,page,allocated,root=live[:5];pas=live[5:]
    assert base>=0x100000000 and size==0x180000000 and page in (4096,16384)
    if window:assert base==int(window['base'],16) and size==int(window['size'],16)
    assert allocated==((47*4096+page-1)//page)*page and root==pas[42]
    assert len(set(pas))==47 and all(base<=p<=base+size-4096 and p%4096==0 and p>>36==0 for p in pas)
    segments=rows('LMI_GPU_RAM_SEGMENTS',5)
    expected={a:zlib.crc32(firmware[o:o+n]+bytes(total-n)) for a,total,o,n in
              [(0x4000,0x8000,14812,21968),(0x144000,0x13000,0,0),(0x157000,0x9000,36796,920),(0x60000000,0x1000,0,0)]}
    layout_logged='LMI_GPU_RAM_HFI_RING_OFFSET\n' in log
    if layout_logged:assert rows('LMI_GPU_RAM_HFI_RING_OFFSET',1)==[256]
    # First mode31 binary omitted the compacted layout label; PERF could
    # only run on its fixed 256B layout. CRC still proves the exact table.
    aligned=layout_logged or 'LMI_GPU_HFI_PERF_REQUEST\n' in log
    ring_offset=256 if aligned else 224 # Old frozen mode27..30 evidence.
    hfi=bytearray(20480);struct.pack_into('<6I',hfi,0,0,54,6,12,4,4)
    for i,priority in enumerate((10,10,40,20)):
        struct.pack_into('<12I',hfi,24+i*48,int(i<3),0x60001000+ring_offset+i*4096,i|(priority<<8),1024,*([0]*8))
    expected[0x60001000]=zlib.crc32(hfi)
    assert {v>>32:v&0xffffffff for v in segments}==expected, 'Firmware/HFI payload CRC mismatch'
    registers={}
    for phase in (('BEFORE','ACTUAL') if active else ('BEFORE','ACTUAL','RESTORED')):
        raw=rows('LMI_GPU_GMU_ROUTE_'+phase,15)
        assert [v>>32 for v in raw]==[0x3da0000+off for off in OFFSETS]
        registers[phase]=[v&0xffffffff for v in raw]
    before,actual=[registers[k] for k in ('BEFORE','ACTUAL')]
    assert before[0]==0 and not before[9]&1 and before[11:]==[0,0,0,0]
    target=[1,0x38071,0x803519,root&0xffffffff,(root>>32)|0x10000,0,0,0xf404ff44,0,
            0xc000e7,(before[10]&~0x030303ff)|0x300,0x84000005,0x1f300,0x400,0]
    assert actual==target, 'Actual SMMU context/route not established'
    assert rows('LMI_GPU_GMU_ROUTE_ROOT',1)==[root]
    expected_result=3 if active else 1
    assert rows('LMI_GPU_GMU_ROUTE_RESULT',1)==[expected_result]
    assert rows('LMI_GPU_RAM_CONSUMER_RESULT',1)==[expected_result]
    assert not any(v in log for v in ('LMI_GPU_RAM_RETAINED\n','LMI_GPU_RAM_REFUSED\n','LMI_GPU_REFUSED\n'))
    markers=['LMI_GPU_GMU_200MHZ_ACTUAL','LMI_GPU_RAM_BEGIN','LMI_GPU_RAM_SOFTWARE_WALK_OK',
             'LMI_GPU_RAM_LIVE_MAP','LMI_GPU_GMU_ROUTE_BEFORE','LMI_GPU_GMU_ROUTE_ACTUAL']
    if active:
        assert log.count('LMI_GPU_RAM_ACTIVE_RETAINED\n')==1
        assert all(v not in log for v in ('LMI_GPU_GMU_ROUTE_RESTORED','LMI_GPU_GMU_ROUTE_DETACH_OK','LMI_GPU_RAM_CLEANUP_DONE','LMI_GPU_GMU_200MHZ_RESTORED','LMI_GPU_SMMU_RESTORE_OFFSET'))
        markers+=['LMI_GPU_GMU_BOOT_ACTIVE_HELD','LMI_GPU_GMU_BOOT_RESULT','LMI_GPU_RAM_ACTIVE_RETAINED','LMI_GPU_GMU_ROUTE_RESULT']
    else:
        restored=registers['RESTORED']
        assert restored[:12]==before[:12] and restored[12:]==[0x1f300,0,0], 'Unsafe/incomplete detach'
        assert log.count('LMI_GPU_GMU_ROUTE_DETACH_OK\n')==1 and log.count('LMI_GPU_RAM_CLEANUP_DONE\n')==1
        markers+=['LMI_GPU_GMU_ROUTE_RESTORED','LMI_GPU_GMU_ROUTE_DETACH_OK','LMI_GPU_RAM_CLEANUP_DONE','LMI_GPU_GMU_ROUTE_RESULT','LMI_GPU_GMU_200MHZ_RESTORED']
    indices=[log.index(k+'\n') for k in markers];assert indices==sorted(indices), 'Backing/clock lifetime order invalid'
    bus=re.findall(r'LMI_GPU_SMMU_CLOCK_OFFSET\n([0-9a-f]{16})\nLMI_GPU_SMMU_CLOCK_STATUS\n([0-9a-f]{16})\n',log)
    assert {int(k,16) for k,v in bus}=={0x7100c,0x71018}
    assert all(not int(v,16)&0x80000000 or int(v,16)&0xf0000000==0x20000000 for k,v in bus)
    undo=re.findall(r'LMI_GPU_SMMU_RESTORE_OFFSET\n([0-9a-f]{16})\nLMI_GPU_SMMU_RESTORE_EXPECTED\n([0-9a-f]{16})\nLMI_GPU_SMMU_RESTORE_ACTUAL\n([0-9a-f]{16})\nLMI_GPU_SMMU_RESTORE_STATUS\n([0-9a-f]{16})\n',log)
    assert not undo if active else {int(k,16) for k,e,a,s in undo}=={0x7100c,0x71018} and all(e==a for k,e,a,s in undo)
    assert all(int(s,16)&0x80000000 for k,e,a,s in undo if int(k,16)==0x71018 and int(e,16)==0)
    return dict(mode=28 if active else 27,root_pa=hex(root),page_pas=[hex(p) for p in pas],wired_bytes=allocated,
                segment_crcs={hex(a):hex(c) for a,c in expected.items()},registers=registers,sid=5,mask=0x400,
                translation_and_route_registers_verified=True,detach_verified=not active,backing_live_through_detach=not active,
                allocation_freed=not active,backing_retained_active=active,cbar_restored=False,cbar_retained_inert='0x1f300',bus_votes_restored=not active,
                hfi_ring_offset=ring_offset,dma_verified=False,firmware_execution=active,hardware_acceleration_verified=False)
