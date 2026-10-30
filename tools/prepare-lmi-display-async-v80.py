"""Pin the async review and derive isolated v80 tooling from reviewed v79."""
from pathlib import Path
import difflib,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/lmi-v80-integration';OUT.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
policy=ROOT/'tools/lmi_display_v80_policy.py';source=policy.read_text()
for key,path in {'AUDIT_SHA':'out/lmi-display-async-v80a/build-audit.json',
                 'REVIEW_SHA':'out/lmi-display-async-v80-review-b/result.json','PRIOR_SHA':'tools/lmi_display_v79_policy.py'}.items():
    marker='__'+key+'__';assert source.count(marker)==1;source=source.replace(marker,sha(ROOT/path))
compile(source,str(policy),'exec');policy.write_text(source)
parent=ROOT/'tools/test-lmi-render-cpu-v79.py';before=parent.read_text()
after=before.replace('display_v79','display_v80').replace('display-v79','display-v80')
after=after.replace('explicit v79 profile','explicit v80 profile')
after=after.replace("version='v79' if args.display_v80","version='v80' if args.display_v80")
after=after.replace('[*range(40,67),79]','[*range(40,67),80]')
after=after.replace("'lmi_display_v80_policy.py','lmi_display_v77_policy.py'",
    "'lmi_display_v80_policy.py','lmi_display_v79_policy.py','lmi_display_v77_policy.py',"
    "'lmi-display-async-v80.c','lmi-display-async-v80.h','build-lmi-display-async-v80.py',"
    "'check-lmi-display-async-v80.c','check-lmi-display-async-v80-native.py',"
    "'review-lmi-display-async-v80-v2.py','check-lmi-display-v80-policy.py','prepare-lmi-display-async-v80.py'")
compile(after,'test-lmi-display-async-v80.py','exec')
target=ROOT/'tools/test-lmi-display-async-v80.py';assert not target.exists();target.write_text(after)
(OUT/'tester.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=parent.name,tofile=target.name)))
analyzer=ROOT/'tools/analyze-lmi-display-v79.py';target_analysis=ROOT/'tools/analyze-lmi-display-v80.py';assert not target_analysis.exists()
text=analyzer.read_text().replace('v79','v80')
text=text.replace("keys=['cpu_epss'","keys=['async_dpu','cpu_epss'")
compile(text,str(target_analysis),'exec');target_analysis.write_text(text)
(OUT/'generation.json').write_text(json.dumps(dict(result='ISOLATED_V80_TOOLS_CREATED',
    tester_parent_sha256=sha(parent),tester_sha256=sha(target),policy_sha256=sha(policy),
    loader_reused='v78',observation_seconds=45,host_query_delay_seconds=50,
    original_legacy_verifier_unchanged=True,original_usb_operations_unchanged=True,device_access=False),indent=2)+'\n')
print('Pinned async review; separate v80 tester/analyzer created')
