"""Read-only comparison of the proved lmi transaction and existing desktop ABI.

This report does not publish a service or mark desktop acceleration ready.
"""
from pathlib import Path
import hashlib,json,re

r=Path(__file__).resolve().parents[1]
paths={
    'backend':'hackios/xnu/files/bsd/dev/redwood_adreno.c',
    'service':'hackios/xnu/files/iokit/Kernel/RedwoodGPU.cpp',
    'drm':'userland-source/tools/mesa/redwood-drm/redwood_drm.c',
    'compositor':'userland-source/userland/src/inject.c',
    'owned_memory':'tools/lmi-gpu-core-memory.c',
    'vendor_cores':'out/lmi-gpu-research/lmi-vendor/drivers/gpu/msm/adreno-gpulist.h',
    'mesa_devices':'out/lmi-gpu-research/rsc-register-source/mesa-24.3.0-freedreno_devices.py',
}
s={k:(r/p).read_text() for k,p in paths.items()}
backend=s['backend'];memory=s['owned_memory']
assert '#define GPU_CHIP_ID             0x06030500ull' in backend
assert '#define CORE_SQE_ADDRESS        0x01100000u' in backend
assert '#define CORE_SCRATCH_ADDRESS    0x01200000u' in backend
assert 'struct gpu_space core_space = { .name = "the 3D core", .context = 0' in backend
assert 'rsc_read(s+0x800/4)!=0x84000005' in memory and '0x1f300,0x38071,0x803519' in memory
assert 'log_hex(0x1000000);log_hex(0x1008000);log_hex(0x1010000);' in memory
assert 'wr(smmu.base + context + SMMU_CB_TLBIASID, core_space.context)' in backend
assert 'if (!step_core_start() || !step_core_commands())' in backend
assert 'gpu_block_stop();' in backend.split('redwood_gpu_stop(void)',1)[1].split('redwood_adreno_stop',1)[0]
assert 'gpu = IOServiceGetMatchingService(0, IOServiceMatching("RedwoodGPU"))' in s['compositor']
assert '#define REDWOOD_GPU_SERVICE     "RedwoodGPU"' in s['drm']
assert 'redwood_gpu_unmap(b->address, b->size)' in s['service']
for name in ['adreno_gpu_core_a650 =','adreno_gpu_core_a650v2 =']:
    core=s['vendor_cores'].split(name,1)[1].split('\n};',1)[0]
    assert re.search(r'\.gmem_size = SZ_1M \+ SZ_128K',core)
mesa=s['mesa_devices'].split('GPUId(650)',1)[1].split('add_gpus(',1)[0]
assert 'num_ccu = 3' in mesa and 'highest_bank_bit = 16' in mesa
e=r/'out/lmi-checkpoint-63-ios-probe-test-a650-tile-seq-mode46-25'
proof=json.loads((e/'hardware-test.json').read_text())
assert proof['result'].startswith('PASS:') and proof['gpu_gmu_boot']['gpu_tile_pixels_verified']
assert proof['android_return']['android_boot_completed']
report=dict(result='AUDITED: desktop bridge still required',hardware_tile_verified=True,
    desktop_acceleration_verified=False,service_publication_authorized_by_this_audit=False,
    sources={k:dict(path=p,sha256=hashlib.sha256((r/p).read_bytes()).hexdigest()) for k,p in paths.items()},
    hardware_evidence=str(e.relative_to(r)),
    mismatches=[
        dict(field='chip_id',old='0x06030500',lmi='0x06050002',effect='Mesa chooses the wrong GPU configuration'),
        dict(field='gmem_bytes',old=512*1024,lmi=1152*1024,effect='Use the pinned A650 vendor size, not a guessed cache total'),
        dict(field='highest_bank_bit',old=14,lmi=16,effect='Tiled resources and UBWC require matching hardware configuration'),
        dict(field='sqe_iova',old='0x01100000',lmi='0x01008000',effect='Recovery must not reuse the old firmware location'),
        dict(field='scratch_iova',old='0x01200000',lmi='0x01010000',effect='Submit/time/fence destinations need an owned mapping'),
        dict(field='SMMU_context',old=0,lmi=1,effect='Mapping, unmapping, fault reads and TLB synchronization must use CB1'),
        dict(field='SMMU_ASID',old='uses context index',lmi=2,effect='TLB invalidation must use the actual TTBR ASID'),
    ],
    remaining=[
        'Provide an lmi backend with owned table inventory, dynamic buffer mappings and correct query values',
        'Publish RedwoodGPU only after authenticated normal mode and exact GPU pixels pass',
        'Make buffer release, fault/timeout and end-of-run paths retain uncertain DMA dependencies until bounded reboot',
        'Replace the old board reset/power recovery path before the lmi service can use it',
        'Verify Mesa GL rendering, desktop composition and repeated submissions on real hardware',
    ])
(r/'out/lmi-gpu-research/desktop-integration-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('AUDITED: real GPU pixels PASS; desktop needs lmi chip/memory/CB1-ASID2/lifecycle backend')
