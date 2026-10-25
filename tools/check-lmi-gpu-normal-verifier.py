"""Verify an in-memory host transaction against genuine mode45 parent evidence.

The combined stream is never saved or reported as hardware success.
"""
from pathlib import Path
import json,runpy

r=Path(__file__).resolve().parents[1]
e=r/'out/lmi-checkpoint-63-ios-probe-test-a650-zap-auth-va-mode45-25'
parent=(e/'checkpoint-63.log').read_text()
host=(r/'out/lmi-gmu-unsecure-diag-host.log').read_text()
host=host[:host.index('PASS:')]+'LMI_GPU_NORMAL_RESULT\n0000000000000001\n'
at=parent.index('LMI_GPU_CORE_MEMORY_RESULT\n')
combined=parent[:at]+host+parent[at:]
verify=runpy.run_path(str(r/'tools/verify-lmi-gpu-unsecure.py'))['verify']
fw=(r/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
window=json.loads((e/'hardware-test.json').read_text())['kernel_window']
assert verify(combined,fw,window)['normal_mode_execution_verified']
disabled=(r/'out/lmi-gmu-unsecure-hwcg-off-host.log').read_text()
disabled=disabled[:disabled.index('PASS:')]+'LMI_GPU_NORMAL_RESULT\n0000000000000001\n'
assert not verify(parent[:at]+disabled+parent[at:],fw,window)['normal_sp_force_write_used']
cases={
    'missing new fence':('00000000650c0de2\nLMI_GPU_NORMAL_VERIFIED_HELD','0000000000000000\nLMI_GPU_NORMAL_VERIFIED_HELD'),
    'old fence changed':('LMI_GPU_NORMAL_FENCE\n00000000650c0de1','LMI_GPU_NORMAL_FENCE\n0000000000000000'),
    'SP readback mismatch':('LMI_GPU_NORMAL_SP\n0000000000000000\n0000000000000001','LMI_GPU_NORMAL_SP\n0000000000000000\n0000000000000000'),
    'SP other bits lost':('LMI_GPU_NORMAL_SP\n0000000000000000','LMI_GPU_NORMAL_SP\n00000000000000a4'),
    'wrong mode opcode':('0000000070e60001','0000000070660001'),
    'wrong write destination':('0000000001010004','0000000001010000'),
    'busy despite RPTR15':('LMI_GPU_CP_STATUS\n000000000000000f\n03d0084000000001','LMI_GPU_CP_STATUS\n000000000000000f\n03d0084000e61097'),
    'CP fault':('03d0208400000000','03d0208400000001'),
    'SMMU fault':('03da905800000400','03da905800000402'),
    'wrong RPTR':('03d020180000000f','03d020180000000e'),
    'wrong canary':('LMI_GPU_NORMAL_BEGIN\n000000007eabe044','LMI_GPU_NORMAL_BEGIN\n000000007eabe045'),
    'wrong diagnostic canary':('000000007eabe04a','000000007eabe04b'),
    'wrong diagnostic address':('03d2f814','03d2f818'),
    'missing diagnostic row':('03d2b80400000001\n',''),
    'address control did not latch':('LMI_GPU_NORMAL_ADDR_AFTER\n03d0300400000001','LMI_GPU_NORMAL_ADDR_AFTER\n03d0300400000000'),
    'unexpected initial address bits':('LMI_GPU_NORMAL_ADDR_BEFORE\n03d0300400000000','LMI_GPU_NORMAL_ADDR_BEFORE\n03d0300400000003'),
    'false result':('LMI_GPU_NORMAL_RESULT\n0000000000000001','LMI_GPU_NORMAL_RESULT\n0000000000000000'),
    'wrong clock policy':('LMI_GPU_NORMAL_CLOCK_POLICY\n0000000000000001','LMI_GPU_NORMAL_CLOCK_POLICY\n0000000000000000'),
    'SP status off':('LMI_GPU_NORMAL_CLOCK_POLICY\n0000000000000001\n000000008aa8aa82\n0000000000000000','LMI_GPU_NORMAL_CLOCK_POLICY\n0000000000000001\n000000008aa8aa82\n0000000000000010'),
}
for name,(old,new) in cases.items():
    assert old in host,name
    changed=host.replace(old,new,1)
    try:
        verify(parent[:at]+changed+parent[at:],fw,window)
    except AssertionError:
        continue
    raise AssertionError('Accepted '+name)
disabled_cases={
    'disabled HWCG with force policy':('LMI_GPU_NORMAL_CLOCK_POLICY\n0000000000000000','LMI_GPU_NORMAL_CLOCK_POLICY\n0000000000000001'),
    'disabled HWCG with SP off':('LMI_GPU_NORMAL_CLOCK_POLICY\n0000000000000000\n0000000000000000\n0000000000000000','LMI_GPU_NORMAL_CLOCK_POLICY\n0000000000000000\n0000000000000000\n0000000000000010'),
    'disabled HWCG with changed SP control':('LMI_GPU_NORMAL_SP\n0000000000000000\n0000000000000000','LMI_GPU_NORMAL_SP\n0000000000000000\n0000000000000001'),
}
for name,(old,new) in disabled_cases.items():
    assert old in disabled,name
    try:
        verify(parent[:at]+disabled.replace(old,new,1)+parent[at:],fw,window)
    except AssertionError:
        continue
    raise AssertionError('Accepted '+name)
report=dict(result='PASS',negative_cases=[*cases,*disabled_cases],host_scenarios=44,
            synthetic_positive_in_memory_only=True,hardware_verified=False)
(r/'out/lmi-gpu-research/mode46-diag-offline-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
