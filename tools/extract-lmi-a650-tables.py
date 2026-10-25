"""Generate auditable A650 vendor tables; does not write GPU registers."""
from pathlib import Path
import hashlib,json,re
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-gpu-hardware'
header=(out/'a6xx_reg.h').read_text()
catalog=(out/'adreno-gpulist.h').read_text()
defines={k:int(v,16) for k,v in re.findall(r'^#define\s+(A6XX_\w+)\s+(0x[0-9a-fA-F]+)\b',header,re.M)}
report={'scope':'Vendor A650 values only; not hardware tested; no MMIO writes',
    'sources':{p:hashlib.sha256((out/p).read_bytes()).hexdigest() for p in ['a6xx_reg.h','adreno-gpulist.h']},'tables':{}}
for name in ['a650_hwcg_regs','a650_gbif_regs']:
    body=re.search(r'\b'+name+r'\[\]\s*=\s*\{(.*?)\n\};',catalog,re.S)[1]
    rows=[]
    for reg,value in re.findall(r'\{\s*(A6XX_\w+)\s*,\s*(0x[0-9a-fA-F]+)\s*\}',body):
        assert reg in defines,reg
        rows.append(dict(name=reg,word_offset=defines[reg],byte_offset=defines[reg]*4,value=int(value,16)))
    assert rows
    report['tables'][name]=rows
body=re.search(r'\ba620_protected_regs\[\]\s*=\s*\{(.*?)\n\};',catalog,re.S)[1]
rows=[]
for index,lo,hi,deny in re.findall(r'\{\s*A6XX_CP_PROTECT_REG\s*\+\s*(\d+),\s*(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+),\s*([01])\s*\}',body):
    rows.append(dict(index=int(index),first_word=int(lo,16),last_word=int(hi,16),noaccess=bool(int(deny))))
assert rows and rows[-1]['index']==47
report['tables']['a650_protected_ranges']=rows
(out/'a650-vendor-register-tables.json').write_text(json.dumps(report,indent=2)+'\n')
print({k:len(v) for k,v in report['tables'].items()})
