"""Derive isolated review/test tools without changing frozen predecessors."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'out/lmi-v79-integration'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create(old, new, edits):
    before = (ROOT / 'tools' / old).read_text()
    after = before
    for needle, value in edits:
        assert needle in after, needle
        after = after.replace(needle, value)
    compile(after, new, 'exec')
    target = ROOT / 'tools' / new
    assert not target.exists()
    target.write_text(after, encoding='utf-8')
    (OUT / (new + '.diff')).write_text(''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile=old, tofile=new)), encoding='utf-8')
    return dict(parent=old, parent_sha256=sha(ROOT / 'tools' / old),
                variant=new, variant_sha256=sha(target))


if __name__ == '__main__':
    OUT.mkdir(exist_ok=False)
    rows = []
    rows.append(create('check-lmi-render-minimal-v76.py', 'check-lmi-render-cpu-v79.py', [
        ('out/lmi-display-timing-v73/mach.development.bcm2837', 'out/lmi-cpu-epss-v77e/mach.development.bcm2837'),
        ('out/lmi-render-minimal-v76b-host', 'out/lmi-render-cpu-v79-host'),
        ('out/lmi-render-minimal-v76', 'out/lmi-render-cpu-v79'),
        ('68ec1820fea704e99ab1ccac5d70f19670faa9428378f75592f251ff5ede56c2',
         'ca0b8c221f8318f1447b043e7e31bf944a6baadfa9647a83afb409b2bad4a901'),
    ]))
    rows.append(create('test-lmi-return-short-v78.py', 'test-lmi-render-cpu-v79.py', [
        ('display_v77', 'display_v79'), ('display-v77', 'display-v79'),
        ('explicit v77 profile', 'explicit v79 profile'),
        ("version='v77' if args.display_v79", "version='v79' if args.display_v79"),
        ('[*range(40,67),77]', '[*range(40,67),79]'),
        ("'lmi_display_v79_policy.py','lmi_display_v73_policy.py'",
         "'lmi_display_v79_policy.py','lmi_display_v77_policy.py','build-lmi-render-cpu-v79.py',"
         "'check-lmi-render-cpu-v79.py','check-lmi-display-v79-policy.py',"
         "'prepare-lmi-render-cpu-v79.py','finalize-lmi-render-cpu-v79.py','lmi_display_v73_policy.py'"),
    ]))
    tester = (ROOT / 'tools/test-lmi-render-cpu-v79.py').read_text()
    assert 'args.display_v77' not in tester
    assert tester.count('from lmi_display_v79_policy import stage') == 1
    assert "'lmi_display_v77_policy.py'" in tester
    (OUT / 'generation.json').write_text(json.dumps(dict(
        result='ISOLATED_V79_TOOLS_CREATED', variants=rows, device_access=False,
        loader_reused='v78', duration_seconds=45, host_query_delay_seconds=50,
        runtime_observer_and_validator='unchanged v77 CPU plus v73 GPU/DPU',
        original_legacy_verifier_unchanged=True,
    ), indent=2) + '\n')
    print('Created isolated v79 tools; v78 loader and original runtime checks retained')
