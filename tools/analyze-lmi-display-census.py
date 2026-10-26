"""Describe fixed DPU snapshots without guessing which engine drives the panel."""
from pathlib import Path
import argparse,collections,hashlib,json
import re

p=argparse.ArgumentParser()
p.add_argument('evidence',type=Path)
a=p.parse_args()
raw=(a.evidence/'checkpoint-63.log').read_bytes()
text=raw.decode(errors='replace')
static=collections.defaultdict(dict)
timed=collections.defaultdict(lambda:collections.defaultdict(dict))
for stage,kind,offset,value in re.findall(r'^LMI_DPU_REG (before|after) (\w+) offset=([0-9a-f]+) value=([0-9a-f]+)$',text,re.M):
    static[stage][int(offset,16)]=int(value,16)
for stage,tick,offset,value in re.findall(r'^LMI_DPU_TIME (before|after) ticks=([0-9a-f]+) offset=([0-9a-f]+) value=([0-9a-f]+)$',text,re.M):
    timed[stage][int(offset,16)][int(tick,16)]=int(value,16)
result=dict(log_sha256=hashlib.sha256(raw).hexdigest(),stages={})
for stage in ('before','after'):
    values=static[stage]
    counters=[]
    for offset,records in sorted(timed[stage].items()):
        samples=sorted(records.items())
        counters.append(dict(offset=hex(offset),samples=len(samples),
            distinct_values=len({v for t,v in samples}),values=[hex(v) for t,v in samples],
            ticks=[t for t,v in samples],span_ticks=samples[-1][0]-samples[0][0]))
    matches=[]
    for base in (0x5000,0x7000,0x9000,0xb000,0x25000,0x27000,0x29000,0x2b000):
        if values.get(base+0x14)==0x9c000000:
            matches.append(dict(sspp_base=hex(base),source_size=hex(values[base]),
                destination_size=hex(values[base+0xc]),stride=hex(values[base+0x24]),
                format=hex(values[base+0x30]),operation_mode=hex(values[base+0x38])))
    result['stages'][stage]=dict(begin=text.count('LMI_DPU_BEGIN '+stage+' readonly=1'),
        end=text.count('LMI_DPU_END '+stage),static_registers=len(values),
        gop_address_matches=matches,counters=counters,
        registers={hex(k):hex(v) for k,v in sorted(values.items())})
result['scope']='GOP address matches can be stale configuration; counter motion alone does not prove panel scan timing. Raw CNTVCT ticks retained; no assumed refresh rate. No display register was written by the census.'
(a.evidence/'display-census-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
for stage,s in result['stages'].items():
    print(stage,json.dumps({k:s[k] for k in ('begin','end','static_registers','gop_address_matches')}))
    print('moving counters:',','.join(c['offset'] for c in s['counters'] if c['distinct_values']>1))
