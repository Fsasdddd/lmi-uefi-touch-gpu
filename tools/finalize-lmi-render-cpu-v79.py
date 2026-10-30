"""Pin the completed native review and create an isolated result analyzer."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
policy = ROOT / 'tools/lmi_display_v79_policy.py'
source = policy.read_text()
for key, name in {
    'AUDIT_SHA': 'out/lmi-render-cpu-v79/build-audit.json',
    'HOST_SHA': 'out/lmi-render-cpu-v79-host/result.json',
    'PRIOR_SHA': 'tools/lmi_display_v77_policy.py',
}.items():
    marker = '__' + key + '__'
    assert source.count(marker) == 1
    source = source.replace(marker, sha(ROOT / name))
compile(source, str(policy), 'exec')
policy.write_text(source)
old = ROOT / 'tools/analyze-lmi-display-v77.py'
target = ROOT / 'tools/analyze-lmi-display-v79.py'
assert not target.exists()
source = old.read_text().replace('finished v77 run', 'finished v79 run')
source = source.replace('lmi_display_v77_policy', 'lmi_display_v79_policy')
source = source.replace('result-analysis-v77.json', 'result-analysis-v79.json')
compile(source, str(target), 'exec')
target.write_text(source)
report = dict(result='V79_NATIVE_REVIEW_PINNED', device_access=False,
              source_analysis_parent_sha256=sha(old), analyzer_sha256=sha(target),
              policy_sha256=sha(policy))
(ROOT / 'out/lmi-v79-integration/pins.json').write_text(json.dumps(report, indent=2) + '\n')
print('Pinned native review; isolated v79 analyzer created')
