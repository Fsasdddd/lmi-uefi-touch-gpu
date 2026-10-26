"""Relink frozen ELF runtime objects against the extended source kernel.

Host only. Proves allocated bytes reproduce the old ELF before changing any
bindings. Emits relocation evidence; does not produce a bootable kernel yet.
"""
from pathlib import Path
import argparse, bisect, hashlib, json, re, runpy, struct, subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--extension',choices=['v40c','v41'],default='v41')
args=parser.parse_args()

repo = Path(__file__).resolve().parents[1]
frozen = repo/'out/lmi-kernel-ios-continue'
version='v40' if args.extension=='v40c' else args.extension
out = Path('/root/hackios-lmi/out/lmi-display-runtime-'+version)
evidence = repo/('out/lmi-display-runtime-'+version)
assert not out.exists() and not evidence.exists(), 'Preserve prior relocation evidence'
out.mkdir(parents=True); evidence.mkdir()
adapter = runpy.run_path(str(repo/'tools/build-lmi-source-runtime.py'))
old_symbols = sorted((va,name) for va,kind,name in adapter['symbols'](
    (repo/'out/lmi-kernel-source-build-v36/reconstruct-base/kernel-symbols.txt').read_text()))
old_addresses = [va for va,name in old_symbols]
new_symbols = {}
extension=repo/('out/lmi-display-extension-'+args.extension)
extension_meta=json.loads((extension/'result.json').read_text())
for va,kind,name in adapter['symbols']((extension/'extension-symbols.txt').read_text()):
    new_symbols.setdefault(name,[]).append(va)

def allocated(raw):
    assert raw[:6]==b'\x7fELF\x02\x01'
    start=struct.unpack_from('<Q',raw,40)[0]
    size,count,strings=struct.unpack_from('<HHH',raw,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,start+i*size) for i in range(count)]
    names=sections[strings]; names=raw[names[4]:names[4]+names[5]]
    return {names[s[0]:names.index(b'\0',s[0])].decode():(s[3],raw[s[4]:s[4]+s[5]])
            for s in sections if s[2]&2 and s[5]}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

builder=(repo/'tools/build-lmi-ios-probe.py').read_text()
order=['touch.o']+re.findall(r"touch_objects\.append\(str\(out/'([^']+\.o)'\)\)",builder)
assert len(order)==len(set(order))
touch_objects=[frozen/name for name in order if (frozen/name).exists()]
# Include precisely the object set kept by the mode46 build; reject unknown ones.
assert {p.name for p in frozen.glob('*.o')}=={'probe.o',*[p.name for p in touch_objects]}
desktop=runpy.run_path(str(repo/'tools/lmi-gpu-desktop-profile.py'))
commands={
    'probe':['ld.lld','-Ttext=0xfffffff007460a40','--entry=_start',
             '--section-start=.return_trace=0xfffffff00745fd80',
             '--section-start=.smp_return=0xfffffff00745a800'],
    'touch':['ld.lld','-T',str(frozen/'touch.ld'),'--entry=lmi_touch_thread',
             '--gc-sections','--undefined=lmi_gpu_probe',
             *['--undefined=lmi_desktop_'+name for name in sorted({v[2] for v in desktop['ABI'].values()})]],
}
report={}
for name, command in commands.items():
    original=(frozen/(name+'.elf')).read_bytes()
    aliases=adapter['elf_absolutes'](original)
    updated={}; dependencies=[]
    for alias,va in aliases.items():
        pos=bisect.bisect_right(old_addresses,va)-1
        symbol_va,symbol=old_symbols[pos]
        candidates=new_symbols[symbol]
        assert len(candidates)==1, ('Ambiguous dependency',alias,symbol,candidates)
        updated[alias]=candidates[0]+va-symbol_va
        dependencies.append(dict(alias=alias,symbol=symbol,offset=hex(va-symbol_va),
            before=hex(va),after=hex(updated[alias])))
    objects=[frozen/'probe.o'] if name=='probe' else touch_objects
    for suffix,bindings in [('baseline',aliases),('relocated',updated)]:
        target=out/(name+'-'+suffix+'.elf')
        args=[*command,*[f'--defsym={key}={value:#x}' for key,value in bindings.items()],
              *map(str,objects),'-o',str(target)]
        with (evidence/(name+'-'+suffix+'-link.log')).open('w') as stream:
            subprocess.run(args,stdout=stream,stderr=subprocess.STDOUT,check=True)
        if suffix=='baseline':
            assert allocated(target.read_bytes())==allocated(original), ('Runtime baseline allocation mismatch',name)
        else:
            before,after=allocated(original),allocated(target.read_bytes())
            assert before.keys()==after.keys()
            for section,(address,data) in before.items():
                assert after[section][0]==address and len(after[section][1])==len(data), (name,section,'Runtime section moved/resized')
    report[name]=dict(baseline_allocated_bytes_exact=True,dependencies=dependencies,
        original_elf_sha256=sha(frozen/(name+'.elf')),
        relocated_elf_sha256=sha(out/(name+'-relocated.elf')),
        moved_bindings=sum(row['before']!=row['after'] for row in dependencies))
result=dict(result='RELINKED_UNINTEGRATED',runtime=report,
            extension_sha256=extension_meta['kernel_sha256'],
            hardware_ready=False,device_access=False)
(evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(result=result['result'],moved_bindings={k:v['moved_bindings'] for k,v in report.items()},hardware_ready=False),indent=2))
