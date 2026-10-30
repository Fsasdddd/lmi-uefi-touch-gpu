"""Pin v76 review and generate a separate tester from frozen v73."""
from pathlib import Path
import hashlib, json

ROOT=Path(__file__).resolve().parents[1];t=ROOT/'tools'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
policy=t/'lmi_display_v76_policy.py';source=policy.read_text()
for key,path in {'AUDIT_SHA':'out/lmi-render-minimal-v76/build-audit.json',
                 'HOST_SHA':'out/lmi-render-minimal-v76b-host/result.json'}.items():
    marker='__'+key+'__';assert source.count(marker)==1;source=source.replace(marker,sha(ROOT/path))
compile(source,str(policy),'exec');policy.write_text(source)
parent=t/'test-lmi-checkpoints-v73.py';original=parent.read_text()
source=original.replace('display_v73','display_v76').replace('display-v73','display-v76')
source=source.replace('[*range(40,67),73]','[*range(40,67),76]')
source=source.replace('explicit v73 profile','explicit v76 profile')
source=source.replace("version='v73' if args.display_v76","version='v76' if args.display_v76")
source=source.replace("'lmi_display_v76_policy.py','lmi_display_v72_policy.py'",
    "'lmi_display_v76_policy.py','lmi_display_v73_policy.py','lmi_display_v72_policy.py',"
    "'build-lmi-render-minimal-v76.py','check-lmi-render-minimal-v76.py',"
    "'check-lmi-display-v76-policy.py','prepare-lmi-render-minimal-v76.py'")
assert source.count('from lmi_display_v76_policy import stage')==1 and 'args.display_v73' not in source
compile(source,'test-lmi-checkpoints-v76.py','exec')
tester=t/'test-lmi-checkpoints-v76.py';assert not tester.exists();tester.write_text(source)
report=dict(result='ISOLATED_TESTER_CREATED',parent_sha256=sha(parent),tester_sha256=sha(tester),
    changes='Version selectors/provenance only; runtime/result delays, USB operations, fences and original legacy verifier unchanged',
    device_access=False)
(ROOT/'out/lmi-render-minimal-v76/tester-generation.json').write_text(json.dumps(report,indent=2)+'\n')
print('Created isolated v76 tester; frozen v73/v75 unchanged')
