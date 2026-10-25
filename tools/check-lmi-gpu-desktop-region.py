"""Adversarial references must fail even after repinning the input hash."""
from pathlib import Path
import hashlib,json,runpy,struct
r=Path(__file__).resolve().parents[1];m=runpy.run_path(str(r/'tools/audit-lmi-gpu-desktop-region.py'))
data=(r/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel/mach.development.bcm2837').read_bytes()
symbols=(r/'out/kernel-symbols.txt').read_text();source=(r/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text()
audit=m['audit'];g=audit.__globals__;original=g['KERNEL_SHA'];positive=audit(data,symbols,source)
secs=runpy.run_path(str(r/'tools/audit-lmi-gpu-normal-diag-region.py'))['sections'](data)
pc=m['ENTRY']-0x100;target=m['START'];s=next(s for s in secs if s[1]<=pc<s[1]+s[2]);at=s[3]+pc-s[1];checks=[]
def reject(name,blob,syms=symbols,src=source):
    g['KERNEL_SHA']=hashlib.sha256(blob).hexdigest()
    try:audit(blob,syms,src)
    except AssertionError:checks.append(name)
    else:raise AssertionError('Accepted '+name)
    finally:g['KERNEL_SHA']=original
for name,word in [('B',0x14000000|(((target-pc)//4)&0x3ffffff)),('BL',0x94000000|(((target-pc)//4)&0x3ffffff)),
    ('ADR',0x10000000|(((target-pc)&3)<<29)|((((target-pc)>>2)&0x7ffff)<<5)),
    ('literal',0x58000000|((((target-pc)//4)&0x7ffff)<<5))]:
    blob=bytearray(data);struct.pack_into('<I',blob,at,word);reject(name,blob)
blob=bytearray(data);struct.pack_into('<Q',blob,at,target);reject('interior pointer',blob)
reject('named interior',data,symbols+f'\n{target:x} s _extra_desktop_entry\n')
for name in m['ENTRIES']:reject('extra caller '+name,data,src=source+'\nvoid extra(void) { '+name[1:]+'(); }\n')
reject('extra step reader',data,src=source+'\nvoid extra(void) { steps[0](); }\n')
blob=bytearray(data);struct.pack_into('<Q',blob,int(positive['table_slots'][1],16),target);reject('changed step pointer',blob)
report=dict(result='PASS',negative_cases=checks,region_bytes=positive['bytes'],hardware_verified=False)
(r/'out/lmi-gpu-research/desktop-region-negative-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'PASS: {len(checks)} desktop region negative cases')
