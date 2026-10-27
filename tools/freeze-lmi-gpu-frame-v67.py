"""Freeze the reviewed candidate before a new, unique RAM-only test."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1];candidate=root/'out/lmi-gpu-frame-v67'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
audit=json.loads((candidate/'build-audit.json').read_text())
host_path=root/'out/lmi-gpu-frame-v67-host/result.json';host=json.loads(host_path.read_text())
link_path=root/'out/lmi-gpu-frame-v67-link-review/result.json';link=json.loads(link_path.read_text())
policy_path=root/'out/lmi-display-v67-policy-host/result.json';policy=json.loads(policy_path.read_text())
assert host['result']==link['result']==policy['result']=='PASS'
paths=set()
for report in (audit,host,policy):
    for n,d in report['sources'].items():
        q=root/'tools'/n;assert sha(q)==d,n;paths.add(q)
for report in (audit,link):
    for n,d in report['inputs'].items():
        q=root/n;assert sha(q)==d,n;paths.add(q)
for n,d in host['generated_sources'].items():
    q=host_path.parent/n;assert sha(q)==d;paths.add(q)
prepared=root/'out/lmi-checkpoint-63-ios-probe-test-display-v67-reviewed-b'
proof=json.loads((prepared/'prepared-only.json').read_text())
assert proof['result']=='HOST_PREPARED_ONLY' and proof['device_access'] is False and proof['display_v67'] is True
kernel=candidate/'mach.development.bcm2837';assert sha(kernel)==audit['sha256']==link['kernel_sha256']==proof['kernel_sha256']
assert sha(prepared/'display-v67-candidate/mach.development.bcm2837')==sha(kernel)
image=root/'out/lmi-gpu-gl-hid-initial-v38'
manifest=json.loads((image/'manifest.json').read_text())
for q in (prepared/'tools').rglob('*'):
    if not q.is_file():continue
    name=q.relative_to(prepared/'tools')
    if name.parts[0]=='gles-copy':
        original=root/Path(*name.parts[1:])
    elif (root/'tools'/name).exists():original=root/'tools'/name
    else:
        assert q.name in manifest['input_trace_source_sha256'],q.name
        original=image/q.name
        assert sha(original)==manifest['input_trace_source_sha256'][q.name]
    assert sha(q)==sha(original),str(name)
    paths.update([q,original])
legacy=root/'out/lmi-checkpoint-63-ios-probe-test-display-v66-desktop-180/tools'
verifiers=list(legacy.glob('verify-*.py'));assert verifiers
for q in verifiers:assert sha(q)==sha(root/'tools'/q.name),q.name
paths.update([kernel,candidate/'build-audit.json',host_path,link_path,policy_path,Path(__file__),
    root/'tools/test-lmi-checkpoints.py',root/'tools/lmi_display_v67_policy.py',candidate/'code-review.md',
    prepared/'prepared-only.json',prepared/'kernel-checkpoint.bin',prepared/'display-v67-candidate/execution-profile.json',
    root/'out/lmi-gpu-research/mode46-desktop-preflight.json',*verifiers])
report=dict(result='OFFLINE_REVIEWED',kernel_sha256=sha(kernel),hardware_tested=False,device_access=False,
    desktop_gpu_copy=True,partial_cpu_fallback=True,all_cpu_display_work_removed=False,
    wifi_integrated=False,performance_verified=False,frozen_legacy_verifiers_unchanged=True,
    artifacts={str(q.relative_to(root)):sha(q) for q in sorted(paths)})
(candidate/'offline-release.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: reviewed v67 release, current prepared provenance and frozen legacy verifiers')
