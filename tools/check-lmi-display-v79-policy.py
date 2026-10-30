"""Check the exact image and directly inherited CPU/GPU/DPU run policy."""
from pathlib import Path
import hashlib
import json
import re
import lmi_display_v79_policy as policy

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'out/lmi-render-cpu-v79-policy'
assert not out.exists()
out.mkdir()
base = ROOT / 'out/lmi-cpu-epss-v77e/mach.development.bcm2837'
candidate = ROOT / 'out/lmi-render-cpu-v79/mach.development.bcm2837'
old, raw = base.read_bytes(), candidate.read_bytes()
policy.verify_image(old, raw)
assert policy.observe is policy.prior.observe and policy.validate_run is policy.prior.validate_run
image_rejections = []


def reject_image(name, original, changed):
    try:
        policy.verify_image(original, changed)
    except AssertionError:
        image_rejections.append(name)
    else:
        raise AssertionError(name)


reject_image('unmodified-200us', old, old)
reject_image('wrong-parent', raw, raw)
reject_image('truncated', old, raw[:-4])
changed = bytearray(raw)
changed[policy.OFFSET + 8] ^= 1
reject_image('extra-instruction-edit', old, bytes(changed))
source = ROOT / 'out/lmi-checkpoint-63-ios-probe-test-display-v78-return45/checkpoint-63.log'
log = source.read_text(encoding='utf-8')
assert policy.validate_run(policy.observe(log))['passed']
assert policy.observe(log)['cpu_epss']['measured_cpu_frequency'] is None
assert policy.observe(log)['display_timing']['measured_animation_fps'] is None
mutations = {
    'missing-cpu-restore': re.sub(r'(?m)^LMI_CPU_EPSS_RESTORE .*\n', '', log),
    'missing-cpu-request': re.sub(r'(?m)^LMI_CPU_EPSS_REQUEST .*\n', '', log),
    'missing-frame-timing': re.sub(r'(?m)^LMI_TIME_FRAME .*\n', '', log),
    'missing-gpu-lifetime': re.sub(r'(?m)^LMI_GPU_BLIT_LIFETIME .*\n', '', log),
}
for name, text in mutations.items():
    assert text != log, name
    assert not policy.validate_run(policy.observe(text))['passed'], name
paths = [Path(__file__), ROOT / 'tools/lmi_display_v79_policy.py',
         ROOT / 'tools/lmi_display_v77_policy.py', base, candidate, source]
report = dict(
    result='PASS', scenarios=10, image_mutations_rejected=image_rejections,
    record_mutations_rejected=list(mutations),
    observer_and_validator_identical_to_v77=True,
    original_hardware_log_unchanged=True, mutated_records_are_synthetic=True,
    hardware_tested=False, performance_verified=False,
    inputs={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
)
(out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: exact v79 image plus unchanged CPU restore and GPU/DPU admission')
