"""Read-only candidate body audit against the exact v65b image.

Private entries must have no external code or loaded references. The entire
file-backed RX segments are scanned, including injected padding and real FDEs.
"""
from pathlib import Path
import hashlib,json,re,struct

root=Path(__file__).resolve().parents[1]
source=root/'tools/audit-lmi-display-quiesce-space-v64.py'
text=source.read_text(encoding='utf-8')
text=text.replace('out/lmi-gpu-map-v63c/mach.development.bcm2837',
                  'out/lmi-display-preclean-v65b/mach.development.bcm2837')
text=text.replace('baa6d3ef46691f8fbeb8fe93ffbbf31e2ebf6450bb4684e57d90873147d52ccc',
                  '0c61da0dda94a0280495d96af94c85edb8b28dea8f068e26b34f96fa885f44e6')
text=text.replace("['_gpu_block_stop','_gpu_times','_space_faulted']",
                  "['_ring_send','_step_core_commands','_redwood_adreno_minute']")
text=text.replace('out/lmi-display-quiesce-space-v64', 'out/lmi-gpu-copy-space-v66')
assert 'out/lmi-display-quiesce-space-v64' not in text
scope={'__file__':str(Path(__file__).resolve())}
exec(compile(text,str(source),'exec'),scope)
# Entry references rejected above are retained as raw evidence. Admit only the
# commands BODY after separately proving the sole loaded entry is steps[20],
# whose reader has been replaced, and preserving a false-return entry stub.
raw=scope['raw'];off=scope['off'];signed=scope['signed']
report=json.loads((root/'out/lmi-gpu-copy-space-v66/result.json').read_text())
row=next(r for r in report['regions'] if r['symbol']=='_step_core_commands')
entry=int(row['entry'],16)
assert row['direct_references']==row['page_references']==row['unwind_references']==[]
assert row['loaded_pointers']==['0xfffffff0071ce668']
native=root/'hackios/xnu/files/bsd/dev/redwood_adreno.c'
code=native.read_text(encoding='utf-8')
assert len(re.findall(r'\bstep_core_commands\b',re.sub(r'/\*.*?\*/','',code,flags=re.S)))==3
assert len(re.findall(r'\bsteps\s*\[',code))==3
assert 'if (!steps[step - 1]())' in code.split('void\nredwood_adreno_init(void)',1)[1]
table=0xfffffff0071ce5c8
assert (table,'s','_steps') in scope['syms']
assert struct.unpack_from('<Q',raw,off(table+20*8,8))[0]==entry
assert any(va<=table<table+22*8<=va+fs and not prot&2 for va,fo,fs,prot,name in scope['segments'])
abi=json.loads((root/'out/lmi-gpu-queue-v64b/runtime-symbols.json').read_text())
for pc,target in [(0xfffffff0074d4c48,abi['lmi_gpu_probe']),
                  (0xfffffff0074d3c50,abi['lmi_desktop_recover'])]:
    w=struct.unpack_from('<I',raw,off(pc))[0]
    assert w&0xfc000000==0x14000000 and pc+4*signed(w&0x3ffffff,26)==target
row.update(accepted=True,entry_stub_required=[0x52800000,0xd65f03c0],
    step_table_va=hex(table),step_table_index=20,step_reader_replaced=True,
    recovery_replaced=True,loaded_pointer_targets_entry_only=True)
report['accepted_bytes']=row['bytes']
report['sources'][str(source.relative_to(root))]=hashlib.sha256(source.read_bytes()).hexdigest()
report['sources']['tools/audit-lmi-gpu-copy-space-v66.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(root/'out/lmi-gpu-copy-space-v66/result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('ADMITTED commands body only after table/reader/recovery proof; entry must return false:',row['bytes'])
