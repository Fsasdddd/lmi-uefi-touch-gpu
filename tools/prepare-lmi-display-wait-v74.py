"""Pin reviewed v74 outputs and create an isolated tester; no device access."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1];t=ROOT/'tools'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
policy=t/'lmi_display_v74_policy.py';source=policy.read_text()
for key,path in {'AUDIT_SHA':'out/lmi-display-wait-v74/build-audit.json',
    'HOST_SHA':'out/lmi-display-wait-v74-host/result.json','LINK_SHA':'out/lmi-display-wait-v74-link-review/result.json',
    'PRIOR_SHA':'tools/lmi_display_v73_policy.py'}.items():
    marker='__'+key+'__';assert source.count(marker)==1;source=source.replace(marker,sha(ROOT/path))
compile(source,str(policy),'exec');policy.write_text(source)
source=(t/'test-lmi-checkpoints-v73.py').read_text()
source=source.replace('display_v73','display_v74').replace('display-v73','display-v74')
source=source.replace('[*range(40,67),73]','[*range(40,67),74]').replace('explicit v73 profile','explicit v74 profile')
source=source.replace("version='v73' if args.display_v74","version='v74' if args.display_v74")
source=source.replace("'lmi_display_v74_policy.py','lmi_display_v72_policy.py'",
    "'lmi_display_v74_policy.py','lmi_display_v73_policy.py','lmi_display_v72_policy.py',"
    "'lmi-display-wait-v74.c','lmi-display-wait-v74.h','build-lmi-display-wait-v74.py',"
    "'check-lmi-display-wait-v74.py','check-lmi-display-wait-v74.c','audit-lmi-display-wait-v74-linked.py',"
    "'prepare-lmi-display-wait-v74.py','check-lmi-display-v74-policy.py'")
assert source.count('from lmi_display_v74_policy import stage')==1 and 'args.display_v73' not in source
compile(source,'test-lmi-checkpoints-v74.py','exec')
tester=t/'test-lmi-checkpoints-v74.py';assert not tester.exists();tester.write_text(source)
print('Created isolated v74 tester; all frozen parents unchanged')
