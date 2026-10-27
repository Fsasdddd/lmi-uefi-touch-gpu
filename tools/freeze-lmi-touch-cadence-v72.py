"""Record review and freeze the v72b release, including all frozen v71 files."""
from pathlib import Path
import hashlib, json
ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
candidate = ROOT/'out/lmi-touch-cadence-v72b'
review = ROOT/'out/lmi-touch-cadence-v72b-review'
prepared = ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v72-reviewed-b'
old_path = ROOT/'out/lmi-gpu-deferred-cache-v71/offline-release.json'
old = json.loads(old_path.read_text())
paths = {ROOT/n for n in old['artifacts']}
for name, digest in old['artifacts'].items():
    assert sha(ROOT/name) == digest, name
paths.add(old_path)
audit = json.loads((candidate/'build-audit.json').read_text())
check = json.loads((review/'result.json').read_text())
prep = json.loads((prepared/'prepared-only.json').read_text())
assert check['result'] == 'PASS' and check['scenarios'] == 15
assert prep['result'] == 'HOST_PREPARED_ONLY' and prep['device_access'] is False and prep['display_v72']
assert audit['sha256'] == check['kernel_sha256'] == prep['kernel_sha256']
assert sha(prepared/'display-v72-candidate/mach.development.bcm2837') == audit['sha256']
for report in (audit, check):
    for name, digest in report['inputs'].items():
        assert sha(ROOT/name) == digest, name
        paths.add(ROOT/name)
review_text = '''# v72b offline review

Only three guarded ARM64 immediate words differ from reviewed v71: valid report
pause 20ms -> 1ms, idle/header-retry pause 50ms -> 2ms, and finite loop bound
4000 -> 409600. The larger limit prevents a faster loop expiring before the
180-second RAM run finishes; original error exits and timer remain effective.

All I2C edge/clock-stretch timing, power/reset/chip-ID gates, full-report reads,
decoder, last-up coordinates, HID initialization, GPU fence/cache ownership and
DPU completion bytes remain identical. This is a binary patch; editing only the
old C source would not modify the running kernel. A restoration of all three
words reproduces the complete v71 image byte for byte.

Independent Capstone decode plus Unicorn execution of the actual ARM64 loop
passed 15 cases: tap/swipe/final-up/missing-up/multitouch/duplicate/FF/64 failures,
transient/header retry/clamp/active cleanup, both limit boundaries and modeled
185-second idle lifetime. Only external I/O and yielding delays are stubbed;
this does not prove hardware timing, actual sample rate or touch-to-photon time.

Preserved failures: first v72 candidate had the wrong shifted CMP immediate and
was rejected before hardware. Emulator setup initially omitted the dominating
w23=1 gate state; an explicit expected swipe assertion caught that harness error.
The staging script initially referenced a missing renamed ancestry checker;
the failed directory is retained and corrected prepare-only uses reviewed-b.
No failed result is counted as passing and no old candidate/log is overwritten.

Tradeoff: faster GPIO I2C polling consumes more CPU, especially during movement.
Compare same-contact timestamp intervals, post-to-HID delivery and animation
behavior in one RAM-only test. A better sample rate alone is not proof of lower
physical end-to-end latency or higher animation FPS. Legacy GPU admission and
strict source/DPU rules are inherited unchanged; Wi-Fi is not integrated.
'''
assert not (candidate/'code-review.md').exists()
(candidate/'code-review.md').write_text(review_text, encoding='utf-8')
# Record the rejected candidate without altering its original audit or image.
failure = ROOT/'out/lmi-touch-cadence-v72-review/failure.json'
if not failure.exists():
    failure.write_text(json.dumps(dict(result='FAIL', stage='independent ARM64 immediate decode',
        rejected_kernel_sha256=sha(ROOT/'out/lmi-touch-cadence-v72/mach.development.bcm2837'),
        wrong_cmp='0x7164027f', corrected_cmp='0x7141927f', hardware_tested=False), indent=2)+'\n')
for directory in [candidate, review, prepared/'tools', ROOT/'out/lmi-touch-cadence-v72',
                  ROOT/'out/lmi-touch-cadence-v72-review']:
    paths.update(p for p in directory.rglob('*') if p.is_file() and p.name != 'offline-release.json')
paths.update(ROOT/'tools'/name for name in ['build-lmi-touch-cadence-v72.py',
    'check-lmi-touch-cadence-v72.py', 'analyze-lmi-input-cadence.py',
    'prepare-lmi-touch-cadence-v72.py', 'lmi_display_v72_policy.py',
    'test-lmi-checkpoints-v72.py', 'freeze-lmi-touch-cadence-v72.py'])
paths.update([prepared/'prepared-only.json', prepared/'kernel-checkpoint.bin',
    prepared/'display-v72-candidate/execution-profile.json',
    ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v71-desktop-180/input-cadence-analysis.json'])
report = dict(result='OFFLINE_REVIEWED', kernel_sha256=audit['sha256'],
    frozen_v71_files_verified=len(old['artifacts']), changed_instruction_words=3,
    bus_edges_unchanged=True, gpu_and_dpu_unchanged=True, actual_loop_emulated=True,
    hardware_tested=False, performance_verified=False, device_access=False,
    artifacts={str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)})
target = candidate/'offline-release.json'
assert not target.exists()
target.write_text(json.dumps(report, indent=2)+'\n')
for name, digest in report['artifacts'].items():
    assert sha(ROOT/name) == digest, name
print('PASS: v72b release frozen;', len(old['artifacts']), 'v71 files unchanged;', len(paths), 'total')
