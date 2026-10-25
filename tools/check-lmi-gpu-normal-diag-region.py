"""Reject extra references into the isolated diagnostic region before patching."""
from pathlib import Path
import hashlib,json,runpy,struct

r=Path(__file__).resolve().parents[1]
m=runpy.run_path(str(r/'tools/audit-lmi-gpu-normal-diag-region.py'))
data=(r/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel/mach.development.bcm2837').read_bytes()
symbols=(r/'out/kernel-symbols.txt').read_text()
source=(r/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text()
audit=m['audit'];g=audit.__globals__;original=g['KERNEL_SHA']
positive=audit(data,symbols,source)
pc=m['ENTRY']-0x100;target=m['START']
section=next(s for s in m['sections'](data) if s[4]&0x80000400 and s[1]<=pc<s[1]+s[2])
at=section[3]+pc-section[1]
checks=[]

def reject(name,blob,syms=symbols,src=source):
    # An adversarial reference must be rejected independently of the hash pin.
    g['KERNEL_SHA']=hashlib.sha256(blob).hexdigest()
    try:
        audit(blob,syms,src)
    except AssertionError:
        checks.append(name)
    else:
        raise AssertionError('Accepted '+name)
    finally:
        g['KERNEL_SHA']=original

for name,word in [('branch',0x94000000|(((target-pc)//4)&0x3ffffff)),
                  ('ADR',0x10000000|(((target-pc)&3)<<29)|((((target-pc)>>2)&0x7ffff)<<5))]:
    blob=bytearray(data);struct.pack_into('<I',blob,at,word);reject(name,blob)
blob=bytearray(data);struct.pack_into('<Q',blob,at,target);reject('interior pointer',blob)
reject('named interior target',data,symbols+f'\n{target:x} s _unexpected_normal_diag\n')
reject('extra source caller',data,src=source+'\nvoid extra(void) { step_core_start(); }\n')
reject('extra step-table reader',data,src=source+'\nvoid extra(void) { steps[0](); }\n')
report=dict(result='PASS',negative_cases=checks,region_bytes=positive['bytes'],hardware_verified=False)
(r/'out/lmi-gpu-research/normal-diag-region-negative-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
