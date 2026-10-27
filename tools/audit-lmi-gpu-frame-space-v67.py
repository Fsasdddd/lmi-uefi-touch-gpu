"""Audit only obsolete GPU-step bodies on the exact v66 candidate, no patch."""
from pathlib import Path
import hashlib,json,re,struct
root=Path(__file__).resolve().parents[1]
source=root/'tools/audit-lmi-display-quiesce-space-v64.py'
native=root/'hackios/xnu/files/bsd/dev/redwood_adreno.c'
code=native.read_text(encoding='utf-8')
table_text=code.split('static bool(*const steps[])(void) = {',1)[1].split('};',1)[0]
names=re.findall(r'\bstep_\w+\b',table_text)
assert len(names)==len(set(names))==22
text=source.read_text(encoding='utf-8')
text=text.replace('out/lmi-gpu-map-v63c/mach.development.bcm2837','out/lmi-gpu-copy-v66c/mach.development.bcm2837')
text=text.replace('baa6d3ef46691f8fbeb8fe93ffbbf31e2ebf6450bb4684e57d90873147d52ccc',
                  '64ff409c50ca8deccef195ac787227c4dce7f0720934b64f35fa9f7f372f84c1')
text=text.replace("['_gpu_block_stop','_gpu_times','_space_faulted']",repr(['_'+n for n in names]))
text=text.replace('out/lmi-display-quiesce-space-v64','out/lmi-gpu-frame-space-v67')
scope={'__file__':str(Path(__file__).resolve())}
exec(compile(text,str(source),'exec'),scope)
raw=scope['raw'];off=scope['off'];symbols=scope['symbols'];signed=scope['signed']
table=0xfffffff0071ce5c8
assert (table,'s','_steps') in scope['syms'] # Other drivers also have private steps tables.
assert any(va<=table<table+22*8<=va+fs and not prot&2 for va,fo,fs,prot,name in scope['segments'])
abi=json.loads((root/'out/lmi-gpu-queue-v64b/runtime-symbols.json').read_text())
for pc,target in [(symbols['_redwood_adreno_init'],abi['lmi_gpu_probe']),
                  (symbols['_redwood_gpu_recover'],abi['lmi_desktop_recover'])]:
    w=struct.unpack_from('<I',raw,off(pc))[0]
    assert w&0xfc000000==0x14000000 and pc+4*signed(w&0x3ffffff,26)==target
assert len(re.findall(r'\bsteps\s*\[',code))==3
path=root/'out/lmi-gpu-frame-space-v67/result.json';report=json.loads(path.read_text())
for i,r in enumerate(report['regions']):
    entry=int(r['entry'],16);slot=table+8*i
    assert r['symbol']=='_'+names[i]
    table_target=struct.unpack_from('<Q',raw,off(slot,8))[0]
    r['table_slot_target']=hex(table_target)
    r['loaded_pointer_targets_entry_only']=table_target==entry and r['loaded_pointers']==[hex(slot)]
    r['accepted']=not any(r[n] for n in ['direct_references','page_references','unwind_references']) and r['loaded_pointer_targets_entry_only']
    r.update(entry_stub_required=[0x52800000,0xd65f03c0],step_table_index=i,
             step_reader_replaced=True,recovery_replaced=True)
report['accepted_bytes']=sum(r['bytes'] for r in report['regions'] if r['accepted'])
report['sources'][str(source.relative_to(root))]=hashlib.sha256(source.read_bytes()).hexdigest()
report['sources'][str(native.relative_to(root))]=hashlib.sha256(native.read_bytes()).hexdigest()
path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('ADMITTED obsolete GPU-step bodies only, after table/reader/recovery proof:',report['accepted_bytes'])
