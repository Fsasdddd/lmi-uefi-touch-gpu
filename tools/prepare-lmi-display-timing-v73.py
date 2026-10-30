"""Pin completed offline reviews and create a separate v73 tester."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1];t=ROOT/'tools'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
policy=t/'lmi_display_v73_policy.py';source=policy.read_text()
for key,path in {
    'AUDIT_SHA':'out/lmi-display-timing-v73/build-audit.json',
    'HOST_SHA':'out/lmi-display-timing-v73b-host/result.json',
    'LINK_SHA':'out/lmi-display-timing-v73b-link-review/result.json',
    'PRIOR_SHA':'tools/lmi_display_v72_policy.py',
}.items():
    marker='__'+key+'__';assert source.count(marker)==1
    source=source.replace(marker,sha(ROOT/path))
compile(source,str(policy),'exec');policy.write_text(source)
source=(t/'test-lmi-checkpoints-v72.py').read_text()
source=source.replace('display_v72','display_v73').replace('display-v72','display-v73')
source=source.replace('[*range(40,67),72]','[*range(40,67),73]')
source=source.replace('explicit v72 profile','explicit v73 profile')
source=source.replace("version='v72' if args.display_v73","version='v73' if args.display_v73")
source=source.replace("'lmi_display_v73_policy.py','lmi_display_v71_policy.py'",
    "'lmi_display_v73_policy.py','lmi_display_v72_policy.py','lmi_display_v71_policy.py',"
    "'lmi-display-timing-v73.c','lmi-display-timing-v73.h','build-lmi-display-timing-v73.py',"
    "'check-lmi-display-timing-v73.py','check-lmi-display-timing-v73.c',"
    "'audit-lmi-display-timing-v73-linked.py','check-lmi-display-v73-policy.py',"
    "'prepare-lmi-display-timing-v73.py'")
assert source.count('from lmi_display_v73_policy import stage')==1 and 'args.display_v72' not in source
compile(source,'test-lmi-checkpoints-v73.py','exec')
tester=t/'test-lmi-checkpoints-v73.py';assert not tester.exists();tester.write_text(source)
print('Created separate v73 policy/tester; all frozen v72 ancestors unchanged')
