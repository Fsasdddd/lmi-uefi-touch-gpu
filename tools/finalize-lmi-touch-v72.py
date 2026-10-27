"""Save factual latency comparison and immutable run hashes after recovery."""
from pathlib import Path
import hashlib, json
ROOT = Path(__file__).resolve().parents[1]
old = ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v71-desktop-180'
out = ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v72-desktop-180-retry'
before = json.loads((old/'input-cadence-analysis.json').read_text(encoding='utf-8'))
after = json.loads((out/'input-cadence-analysis.json').read_text(encoding='utf-8'))
result = json.loads((out/'result-analysis-v72.json').read_text(encoding='utf-8'))
assert result['validation']['passed'] and result['android_return']['android_boot_completed']
assert all(result['android_return']['original_partition_hashes_match'].values())
assert not result['independent_legacy']['passed']
assert 'verify-lmi-gpu-route.py' in result['independent_legacy']['traceback']
comparison = dict(before_version='v71', after_version='v72b',
    before=before, after=after,
    median_sample_interval_reduction_us=(before['same_contact_intervals_us']['median']-
                                         after['same_contact_intervals_us']['median']),
    input_cadence_ratio=(after['reciprocal_median_samples_per_second']/
                         before['reciprocal_median_samples_per_second']),
    user_feedback=result['user_feedback'],
    touch_to_photon_measured=False, animation_fps_speedup_proven=False,
    scope='Only contact sample cadence is quantified. User explicitly confirms improved response and tracking. These are uncontrolled input windows; do not interpret the cadence ratio as FPS gain or end-to-end latency ratio.')
path = out/'input-cadence-comparison.json'
assert not path.exists()
path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
paths = [p for p in out.iterdir() if p.is_file() and p.suffix in ('.json','.log','.raw')]
paths += [ROOT/'out/lmi-v72-integration/hardware-console-retry.log',
          ROOT/'out/lmi-touch-cadence-v72b/offline-release.json',
          ROOT/'tools/analyze-lmi-display-v72.py', ROOT/'tools/analyze-lmi-input-cadence.py',
          ROOT/'tools/analyze-lmi-display-timing.py', Path(__file__)]
manifest = dict(result='EVIDENCE_SAVED', whole_test_result=result['result'],
    strict_gpu_display_validation_passed=True, legacy_verifier_passed=False,
    legacy_failure='verify-lmi-gpu-route.py:62 bus clock records; interleaved button diagnostics visible in original log',
    original_logs_changed=False, verifier_changed=False, android_return_verified=True,
    hardware_tested=True, input_cadence_improved=True, user_tracking_improved=True,
    touch_to_photon_measured=False, animation_fps_speedup_proven=False, wifi_integrated=False,
    artifacts={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})
path = out/'evidence-manifest-v72.json'
assert not path.exists()
path.write_text(json.dumps(manifest, indent=2)+'\n')
print('Saved input-cadence comparison and',len(paths),'evidence hashes; whole-test INCOMPLETE preserved')
