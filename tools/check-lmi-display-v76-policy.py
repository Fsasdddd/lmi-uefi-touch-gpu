"""Reject altered v76 inputs and ensure strict v73 admission is used directly."""
from pathlib import Path
import hashlib, json, re
import lmi_display_v76_policy as policy

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'out/lmi-display-v76-policy-host';assert not out.exists();out.mkdir()
base=ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837'
candidate=ROOT/'out/lmi-render-minimal-v76/mach.development.bcm2837'
old=base.read_bytes();raw=candidate.read_bytes();policy.verify_image(old,raw)
assert policy.observe is policy.prior.observe and policy.validate_run is policy.prior.validate_run
rejected=[]
def reject(name,a,b):
    try:policy.verify_image(a,b)
    except AssertionError:rejected.append(name)
    else:raise AssertionError('invalid input admitted: '+name)
reject('old-200us-image',old,old)
reject('wrong-parent',raw,raw)
reject('truncated-candidate',old,raw[:-4])
changed=bytearray(raw);changed[policy.OFFSET+8]^=1
reject('extra-instruction-edit',old,bytes(changed))
source=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v73-desktop-180/checkpoint-63.log'
log=source.read_text(encoding='utf-8')
assert policy.validate_run(policy.observe(log))['passed']
assert policy.observe(log)['display_timing']['measured_animation_fps'] is None
fields=re.search(r'(?m)^LMI_GPU_BLIT_LIFETIME .*$',log)[0].split();fields[-1]='1'
bad=re.sub(r'(?m)^LMI_GPU_BLIT_LIFETIME .*$', ' '.join(fields),log)
assert not policy.validate_run(policy.observe(bad))['passed']
assert not policy.validate_run(policy.observe(re.sub(r'(?m)^LMI_TIME_FRAME .*\n','',log)))['passed']
paths=[Path(__file__),ROOT/'tools/lmi_display_v76_policy.py',base,candidate,source]
report=dict(result='PASS',cases=9,image_mutations_rejected=rejected,
    prior_observer_and_validator_identical=True,inherited_gpu_and_timing_failures_rejected=True,
    original_hardware_log_unchanged=True,hardware_tested=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: exact candidate checks and unchanged v73 GPU/timing admission')
