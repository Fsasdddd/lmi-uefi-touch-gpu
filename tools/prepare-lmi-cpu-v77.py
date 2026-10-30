"""Pin completed CPU reviews and derive a tester retaining v73's USB policy."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];tools=ROOT/'tools'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
policy=tools/'lmi_display_v77_policy.py';source=policy.read_text()
for key,name in {
    'AUDIT_SHA':'out/lmi-cpu-epss-v77e/build-audit.json','HOST_SHA':'out/lmi-cpu-epss/host-c/result.json',
    'NATIVE_SHA':'out/lmi-cpu-epss/native-e/result.json','LINK_SHA':'out/lmi-cpu-epss/link-c/result.json'}.items():
    marker='__'+key+'__';assert source.count(marker)==1;source=source.replace(marker,sha(ROOT/name))
compile(source,str(policy),'exec');policy.write_text(source)
parent=tools/'test-lmi-checkpoints-v73.py';original=parent.read_text()
source=original.replace('display_v73','display_v77').replace('display-v73','display-v77')
source=source.replace('[*range(40,67),73]','[*range(40,67),77]')
source=source.replace('explicit v73 profile','explicit v77 profile')
source=source.replace("version='v73' if args.display_v77","version='v77' if args.display_v77")
source=source.replace("'lmi_display_v77_policy.py','lmi_display_v72_policy.py'",
    "'lmi_display_v77_policy.py','lmi_display_v73_policy.py','lmi_display_v72_policy.py',"
    "'lmi-cpu-epss.c','lmi-cpu-epss.h','lmi-cpu-epss-native.c',"
    "'build-lmi-cpu-epss-v77.py','check-lmi-cpu-epss.py','check-lmi-cpu-epss.c',"
    "'check-lmi-cpu-epss-native.py','audit-lmi-cpu-epss-linked.py','audit-lmi-cpu-epss-space.py',"
    "'prepare-lmi-cpu-v77.py','check-lmi-display-v77-policy.py','build-lmi-loader-v77.py'")
needle="profile=json.loads((root/'out/lmi-loader/manifest.json').read_text())"
assert source.count(needle)==1
source=source.replace(needle,needle+"\nassert profile.get('lmi_cpu_requests')==2, 'v77 requires explicit CPU-only loader opt-in'")
source=source.replace("preflight_name='mode46-desktop-preflight.json'","preflight_name='mode46-desktop-preflight-v77.json'")
source=source.replace("'check-lmi-gpu-normal-preflight.py']","'check-lmi-gpu-normal-preflight.py','check-lmi-gpu-normal-preflight-v77.py']")
assert 'args.display_v73' not in source and source.count('from lmi_display_v77_policy import stage')==1
compile(source,'test-lmi-checkpoints-v77.py','exec')
target=tools/'test-lmi-checkpoints-v77.py';assert not target.exists();target.write_text(source)
(ROOT/'out/lmi-cpu-epss-v77e/tester-generation.json').write_text(json.dumps(dict(
    result='ISOLATED_TESTER_CREATED',parent_sha256=sha(parent),tester_sha256=sha(target),
    changes='Version/provenance plus explicit loader CPU opt-in assertion; original USB operations, delays, old verifier and all original runtime checks unchanged.',
    device_access=False),indent=2)+'\n')
print('v77 policy pinned and tester created; no device access')
