"""Re-run the frozen full-RX scanner on the exact remaining v65 tail."""
from pathlib import Path
import hashlib,json,struct
root=Path(__file__).resolve().parents[1]
source=root/'tools/audit-lmi-display-quiesce-space-v64.py'
text=source.read_text()
changes={
 'out/lmi-gpu-map-v63c/mach.development.bcm2837':'out/lmi-display-preclean-v65b/mach.development.bcm2837',
 'baa6d3ef46691f8fbeb8fe93ffbbf31e2ebf6450bb4684e57d90873147d52ccc':'0c61da0dda94a0280495d96af94c85edb8b28dea8f068e26b34f96fa885f44e6',
 "['_gpu_block_stop','_gpu_times','_space_faulted']":"['_v66_tail']",
 'entry=symbols[name];lo=entry+8;hi=':'entry=symbols[name];lo=entry;hi=',
 'reports=[]':'reports=[]\nsymbols[\'_v66_tail\']=0xfffffff0074d28d8',
 'out/lmi-display-quiesce-space-v64':'out/lmi-gpu-copy-v66-tail',
}
for old,new in changes.items():assert text.count(old)==1,old;text=text.replace(old,new)
scope={'__file__':str(Path(__file__).resolve())};exec(compile(text,str(source),'exec'),scope)
path=root/'out/lmi-gpu-copy-v66-tail/result.json';report=json.loads(path.read_text())
row,=report['regions'];assert row['accepted'] and row['start']=='0xfffffff0074d28d8' and row['bytes']==204
audit_path=root/'out/lmi-display-preclean-v65b/build-audit.json'
audit=json.loads(audit_path.read_text());placed=next(s for s in audit['sections'] if s['section']=='.slot0')
assert int(placed['start'],16)+placed['bytes']==0xfffffff0074d28d5
assert int(placed['start'],16)+placed['capacity']==0xfffffff0074d29a4
assert row['end']=='0xfffffff0074d29a4'
for p in [source,audit_path]:report['sources'][str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
report['no_entry_stub_needed']=True
path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS: actual v65 unused 204-byte tail, full RX/pointer/FDE scan')
