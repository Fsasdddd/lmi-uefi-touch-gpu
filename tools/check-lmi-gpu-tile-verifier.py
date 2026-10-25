"""Use real normal-mode parent evidence plus an in-memory host tile stream."""
from pathlib import Path
import hashlib,json,runpy

r=Path(__file__).resolve().parents[1]
e=r/'out/lmi-checkpoint-63-ios-probe-test-a650-normal-hwcg-off-mode46-25'
parent=(e/'checkpoint-63.log').read_text()
host=(r/'out/lmi-gpu-tile-host.log').read_text();assert 'PASS: 35 tile scenarios;' in host
host=host[:host.index('PASS:')]
at=parent.index('LMI_GPU_CORE_MEMORY_RESULT\n')
fw=(r/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
window=json.loads((e/'hardware-test.json').read_text())['kernel_window']
ns=runpy.run_path(str(r/'tools/verify-lmi-gpu-tile.py'));verify=ns['verify'];commands=ns['COMMANDS']
def check(tile,base=parent):return verify(base[:at]+tile+base[at:],fw,window)
assert check(host)['gpu_tile_pixels_verified']
cases={
    'wrong tile canary':host.replace('000000007eabe04b','000000007eabe04a',1),
    'pixel error summary':host.replace('LMI_GPU_TILE_PIXELS\n0000000000000100\n0000000000000000','LMI_GPU_TILE_PIXELS\n0000000000000100\n0000000000000001',1),
    'wrong pixel CRC':host.replace('00000000f21d9405','00000000f21d9404',1),
    'wrong pixel count':host.replace('LMI_GPU_TILE_PIXELS\n0000000000000100','LMI_GPU_TILE_PIXELS\n00000000000000ff',1),
    'failed result':host.replace('LMI_GPU_TILE_RESULT\n0000000000000001','LMI_GPU_TILE_RESULT\n0000000000000000',1),
    'duplicate tile stream':host+host,
    'missing verified marker':host.replace('LMI_GPU_TILE_VERIFIED_HELD\n','',1),
    'busy after consumed commands':host.replace('0000000000000044\n03d0084000000001','0000000000000044\n03d0084000000003',1),
    'CP fault':host.replace('03d0208400000000','03d0208400000001',1),
    'SMMU fault':host.replace('03da905800000400','03da905800000402',1),
    'wrong final RPTR':host.replace('03d0201800000044','03d0201800000043',1),
    'wrong final WPTR':host.replace('03d0201c00000044','03d0201c00000043',1),
    'wrong packet count':host.replace('LMI_GPU_TILE_PACKET\n0000000000000031','LMI_GPU_TILE_PACKET\n0000000000000030',1),
}
for i in range(5):
    old='LMI_GPU_TILE_FENCES\n'+''.join(f'{v:016x}\n' for v in [0x650c0de1,0x650c0de2,0x650c0101,0x650c0102,0x650c0de3][:i+1])
    cases[f'wrong fence{i}']=host.replace(old,old[:-17]+'0000000000000000\n',1)
packet='LMI_GPU_TILE_PACKET\n0000000000000031\n'+''.join(f'{v:016x}\n' for v in commands)
assert packet in host
for i,v in enumerate(commands):
    changed=list(commands);changed[i]=v^1
    cases[f'packet word{i}']=host.replace(packet,'LMI_GPU_TILE_PACKET\n0000000000000031\n'+''.join(f'{w:016x}\n' for w in changed),1)
for index in [35,40]:
    for bit,name in [(30,'timestamp'),(31,'IRQ')]:
        changed=list(commands);changed[index]|=1<<bit
        cases[f'event{index} {name} flag']=host.replace(packet,'LMI_GPU_TILE_PACKET\n0000000000000031\n'+''.join(f'{w:016x}\n' for w in changed),1)
for name,changed in cases.items():
    assert changed!=host,name
    try:check(changed)
    except AssertionError:continue
    raise AssertionError('Accepted '+name)
bad_parent=parent.replace('LMI_GPU_NORMAL_RESULT\n0000000000000001','LMI_GPU_NORMAL_RESULT\n0000000000000000',1)
try:check(host,bad_parent)
except AssertionError:pass
else:raise AssertionError('Accepted failed normal parent')
report=dict(result='PASS',host_scenarios=35,negative_cases=[*cases,'failed normal parent'],
    synthetic_positive_in_memory_only=True,hardware_verified=False,
    source_sha256={name:hashlib.sha256((r/'tools'/name).read_bytes()).hexdigest() for name in
        ['lmi-gpu-tile.c','check-lmi-gpu-tile.c','verify-lmi-gpu-tile.py','check-lmi-gpu-tile-verifier.py']},
    host_log_sha256=hashlib.sha256((r/'out/lmi-gpu-tile-host.log').read_bytes()).hexdigest())
(r/'out/lmi-gpu-research/mode46-tile-offline-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'PASS: 35 host scenarios, {len(report["negative_cases"])} verifier negative cases; no synthetic hardware log saved')
