"""Rebind every retained early diagnostic ELF thunk after DATA relocation.

Only fully retained allocations are admitted; an overwritten thunk is rejected.
No device access, no production/source tree changes.
"""
from pathlib import Path
import argparse, bisect, hashlib, json, runpy, struct, subprocess

parser=argparse.ArgumentParser();parser.add_argument('--resume',action='store_true');args=parser.parse_args()

repo=Path(__file__).resolve().parents[1]
out=Path('/root/hackios-lmi/out/lmi-display-early-v41')
evidence=repo/'out/lmi-display-early-v41'
if args.resume:
    assert out.is_dir() and evidence.is_dir() and not (evidence/'result.json').exists()
else:
    assert not out.exists() and not evidence.exists()
    out.mkdir(parents=True);evidence.mkdir()
module=runpy.run_path(str(repo/'tools/build-lmi-source-runtime.py'))
old=sorted((va,name) for va,kind,name in module['symbols']((repo/'out/kernel-symbols.txt').read_text()))
addresses=[va for va,name in old]
new={}
for va,kind,name in module['symbols']((repo/'out/lmi-display-extension-v41/extension-symbols.txt').read_text()):
    new.setdefault(name,[]).append(va)
runtime=(repo/'out/lmi-kernel-source-runtime-v36/mach.development.bcm2837').read_bytes()
segments=module['segments'](runtime)
def allocated(raw):
    pos=struct.unpack_from('<Q',raw,40)[0];size,count=struct.unpack_from('<HH',raw,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,pos+i*size) for i in range(count)]
    return [(s[3],raw[s[4]:s[4]+s[5]]) for s in sections if s[2]&2 and s[5]]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
proof={}
paths=[repo/('out/lmi-kernel-'+name+'-probe') for name in ['preirq','bootstrap','irq','driver','bsd','root']]
paths.append(repo/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel')
for index,path in enumerate(paths):
    frozen=(path/'probe.elf').read_bytes();sections=allocated(frozen)
    assert len(sections)==1
    va,data=sections[0]
    segment=next(s for s in segments.values() if s[0]<=va and va+len(data)<=s[0]+s[3])
    offset=segment[2]+va-segment[0]
    assert runtime[offset:offset+len(data)]==data, ('Early thunk not exactly retained',path)
    aliases=module['elf_absolutes'](frozen);updated={};bindings=[]
    for alias,value in aliases.items():
        start,symbol=old[bisect.bisect_right(addresses,value)-1]
        assert len(new[symbol])==1, ('Ambiguous dependency',alias,symbol)
        updated[alias]=new[symbol][0]+value-start
        bindings.append(dict(alias=alias,symbol=symbol,offset=hex(value-start),before=hex(value),after=hex(updated[alias])))
    for suffix,targets in [('baseline',aliases),('relocated',updated)]:
        dest=out/(str(index)+'-'+suffix+'.elf')
        cmd=['ld.lld',f'-Ttext={va:#x}','--entry=_start',
             *[f'--defsym={k}={v:#x}' for k,v in targets.items()],str(path/'probe.o'),'-o',str(dest)]
        subprocess.run(cmd,check=True,capture_output=True)
        assert [(a,len(b)) for a,b in allocated(dest.read_bytes())]==[(va,len(data))]
        if suffix=='baseline':assert allocated(dest.read_bytes())==sections
    proof[str(index)]=dict(original_elf=str(path/'probe.elf'),
        original_sha256=sha(path/'probe.elf'),relocated_sha256=sha(out/(str(index)+'-relocated.elf')),
        address=hex(va),bytes=len(data),baseline_allocated_bytes_exact=True,dependencies=bindings)
(evidence/'result.json').write_text(json.dumps(dict(result='RELINKED_UNINTEGRATED',thunks=proof,hardware_ready=False),indent=2)+'\n')
print('PASS: 7 retained thunks reproduced byte-for-byte and relinked; hardware not tested')
