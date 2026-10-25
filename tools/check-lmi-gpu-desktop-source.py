"""Reconstruct desktop configuration and headers from pinned primary sources."""
from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
r=Path(__file__).resolve().parents[1];d=r/'out/lmi-gpu-research/rsc-register-source'
pins={'linux-v6.12-a6xx_gpu.c':'c33479377574ed193e82c272b3708e19a2b2153088f246e2639d8a43fef943a2',
    'mesa-24.3.0-a6xx.xml':'543f6843c0b90f61d367b2cd96863569b01d524e1238c82357bd206ec612603b',
    'mesa-24.3.0-adreno_pm4.xml':'3d96f39a6beef90e74325c827e41e0e165ee3eaf9737f94fcbdb75a2e4011f1c'}
for name,sha in pins.items():assert hashlib.sha256((d/name).read_bytes()).hexdigest()==sha,name
linux=(d/'linux-v6.12-a6xx_gpu.c').read_text();x=ET.fromstring((d/'mesa-24.3.0-a6xx.xml').read_text());pm=ET.fromstring((d/'mesa-24.3.0-adreno_pm4.xml').read_text())
for tree in [x,pm]:
    for e in tree.iter():e.tag=e.tag.split('}')[-1]
def reg(name):return int(next(e for e in x.iter() if e.tag in ['reg32','reg64'] and e.get('name')==name).get('offset'),0)
def opcode(name):return int(next(e for e in pm.iter('value') if e.get('name')==name).get('value'),0)
def p7(op,n):return 0x70000000|op<<16|n|((1^(op.bit_count()&1))<<23)|((1^(n.bit_count()&1))<<15)
calc=linux.split('static void a6xx_calc_ubwc_config',1)[1].split('static void a6xx_set_ubwc_config',1)[0]
assert 'adreno_is_a650(gpu)' in calc
for text in ['highest_bank_bit = 16','amsbc = 1','rgb565_predicator = 1','uavflagprd_inv = 2','macrotile_mode = 1','ubwc_swizzle = 0x6']:
    assert text in calc,text
hbb=16-13;swizzle=6;hi=hbb>>2;lo=hbb&3;level2=int(not swizzle&2);mode=swizzle&1
expected=[(reg('RB_NC_MODE_CNTL'),level2<<12|1<<11|hi<<10|1<<4|lo<<1|mode),
    (reg('TPL1_NC_MODE_CNTL'),level2<<6|hi<<4|lo<<1|mode),
    (reg('SP_NC_MODE_CNTL'),level2<<12|hi<<10|2<<4|lo<<1|mode),
    (reg('UCHE_MODE_CNTL'),lo<<21),(reg('RBBM_NC_MODE_CNTL'),1)]
for name,val in [('UCHE_WRITE_RANGE_MAX',0x1ffffffffffc0),('UCHE_WRITE_THRU_BASE',0x1fffffffff000),('UCHE_TRAP_BASE',0x1fffffffff000)]:
    assert re.search(r'gpu_write64\(gpu, REG_A6XX_'+name+r', 0x0*'+f'{val:x}'+r'llu\)',linux)
    expected.extend([(reg(name),val&0xffffffff),(reg(name)+1,val>>32)])
for name,val,expression in [('UCHE_FILTER_CNTL',0x804,'0x804'),('UCHE_CACHE_WAYS',4,'0x4')]:
    assert 'gpu_write(gpu, REG_A6XX_'+name+', '+expression+');' in linux
    expected.append((reg(name),val))
src=(r/'tools/lmi-gpu-desktop.c').read_text()
actual=[tuple(int(v,0) for v in pair) for pair in re.findall(r'\{(0x[0-9a-f]+|\d+),(0x[0-9a-f]+|\d+)\}',src.split('static const u32 nc[][2]',1)[1].split('int DESK lmi_gpu_desktop',1)[0])]
assert actual==expected
for name,count,word in [('CP_EVENT_WRITE',1,0x70460001),('CP_INDIRECT_BUFFER',3,0x70bf8003),('CP_WAIT_FOR_IDLE',0,0x70268000),('CP_EVENT_WRITE',4,0x70460004),('CP_MEM_WRITE',3,0x703d8003)]:
    assert p7(opcode(name),count)==word and f'0x{word:x}' in src
assert 'word(d,4);word(d,0x1010040);word(d,0);word(d,fence)' in src
assert 'rsc_write(d->s+0x9610/4,2)' in src and 'rsc_write(d->s+0x97f0/4,0)' in src
report=dict(result='PASS',primary_sha256=pins,config=expected,source_sha256=hashlib.sha256(src.encode()).hexdigest(),hardware_verified=False)
(r/'out/lmi-gpu-research/mode46-desktop-source-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: pinned A650 UBWC, UCHE cache/bypass setup, independent type7 parity, sequence fences and CB1/ASID2')
