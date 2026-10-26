"""Isolated link experiment for a resident lmi DPU source section. WSL only.

No device access. First re-link the frozen source baseline from its existing
objects. Then add a dedicated TEXT_EXEC section and report symbol/layout drift.
This deliberately does not apply the old address-pinned runtime adapter.
"""
from pathlib import Path
import argparse, hashlib, json, os, runpy, shlex, shutil, struct, subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--resume-baseline', action='store_true')
parser.add_argument('--attempt', default='v41', choices=['v40','v40b','v40c','v41'])
args = parser.parse_args()

repo = Path(__file__).resolve().parents[1]
base = Path('/root/hackios-lmi/kernel-build-v36')
obj = base / 'xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837'
out = Path('/root/hackios-lmi/out/lmi-display-extension-'+args.attempt)
evidence = repo / ('out/lmi-display-extension-'+args.attempt)
if args.resume_baseline:
    assert (out/'baseline').is_file() and (evidence/'input-sha256.json').is_file()
    assert not (out/'extension.unstripped').exists(), 'Do not overwrite an extension'
else:
    assert not out.exists() and not evidence.exists(), 'Preserve previous link experiments'
    out.mkdir(parents=True)
    evidence.mkdir()
toolbin = base / 'xnu-deps/host/bin'
env = dict(os.environ, THEOS='/root/hackios-lmi/gpu-build-env/theos',
    XNUDEPS=str(base/'xnu-deps'), XNU_SDK_PATH=str(base/'xnu-deps/sdk/iPhoneOS16.5.xnu.sdk'),
    XNU_SDK_VERSION='16.5', XNU_PLATFORM_PATH=str(base/'xnu-deps/sdk/Platforms/iPhoneOS.platform'))
env['PATH'] = str(toolbin) + ':' + env['PATH']

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args, log):
    with (evidence/log).open('w') as stream:
        stream.write(shlex.join(map(str,args))+'\n'); stream.flush()
        subprocess.run(list(map(str,args)),cwd=obj,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)

flags = shlex.split((obj/'.LDFLAGS').read_text().rstrip('\0\n'))
assert flags.pop(0) == 'xnu-clang++'
objects = [Path(p) for p in (obj/'link.filelist').read_text().splitlines() if p]
extras = [obj/name for name in ['version.o','lastkerneldataconst.o','lastkernelconstructor.o','nonlto.o']]
objects += extras
archive_file = obj/'mach.development.bcm2837.link/mach.development.bcm2837.linkarchives'
archives = shlex.split(archive_file.read_text())
inputs = objects + [obj/'.LDFLAGS', obj/'link.filelist',
    obj/'all-alias.exp', obj/'symbolsets.plist',archive_file]
inputs += [Path(p) for p in archives if not p.startswith('-')]
initial = {str(p):sha(p) for p in inputs}
if args.resume_baseline:
    assert initial == json.loads((evidence/'input-sha256.json').read_text())
else:
    (evidence/'input-sha256.json').write_text(json.dumps(initial,indent=2)+'\n')
link = [toolbin/'xnu-clang++',*flags,'-filelist',obj/'link.filelist',
    *extras,*archives]
baseline = out/'baseline.unstripped'
if not args.resume_baseline:
    run([*link,'-o',baseline], 'baseline-link.log')
    run([toolbin/'strip','-S',baseline,'-o',out/'baseline'], 'baseline-strip.log')
baseline_sha = sha(out/'baseline')
expected = repo/'out/lmi-kernel-source-build-v36/reconstruct-base/mach.development.bcm2837'
audit = runpy.run_path(str(repo/'tools/build-lmi-source-runtime.py'))
old_symbols = audit['symbols']((expected.parent/'kernel-symbols.txt').read_text())
nm = subprocess.check_output([str(toolbin/'nm'),'-n',str(baseline)],env=env,text=True)
(evidence/'baseline-symbols.txt').write_text(nm)
rebuilt_symbols = audit['symbols'](nm)
expected_segments = audit['segments'](expected.read_bytes())
old_code = [(va,name) for va,kind,name in old_symbols if expected_segments['__TEXT_EXEC'][0] <= va < 0xfffffff007ae0000]
new_code = [(va,name) for va,kind,name in rebuilt_symbols if expected_segments['__TEXT_EXEC'][0] <= va < 0xfffffff007ae0000]
comparison = dict(baseline_sha256=baseline_sha,expected_sha256=sha(expected),
    executable_symbol_addresses_unchanged=sorted(old_code)==sorted(new_code),
    baseline_segments_unchanged=audit['segments']((out/'baseline').read_bytes())==audit['segments'](expected.read_bytes()),
    hardware_ready=False)
# ld64 gives the output a fresh UUID. Admit precisely that 16-byte LC_UUID
# payload, verifying every other header, section, symbol and byte is identical.
old_raw, new_raw = expected.read_bytes(), (out/'baseline').read_bytes()
pos = 32
uuid_ranges = []
for _ in range(struct.unpack_from('<I',old_raw,16)[0]):
    command,size = struct.unpack_from('<II',old_raw,pos)
    if command==0x1b:
        assert size==24
        uuid_ranges.append((pos+8,pos+24))
    pos += size
assert len(uuid_ranges)==1
start,end = uuid_ranges[0]
comparison['baseline_uuid_only_difference'] = (
    len(old_raw)==len(new_raw) and old_raw[:start]==new_raw[:start] and old_raw[end:]==new_raw[end:])
comparison['uuid_field_offset'] = hex(start)
(evidence/'baseline-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
assert comparison['executable_symbol_addresses_unchanged'], 'Cannot extend an unrecognized executable layout'
assert comparison['baseline_segments_unchanged'], 'Baseline re-link has unexpected segment layout'
assert comparison['baseline_uuid_only_difference'], 'Baseline may differ only in its LC_UUID payload'
source = repo/'tools/lmi-dpu-snapshot.c'
shutil.copy2(source,evidence/source.name)
run([toolbin/'xnu-clang','-arch','arm64','-O2','-ffreestanding',
    '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
    '-c',source,'-o',out/'lmi-dpu-snapshot.o'], 'extension-compile.log')
trampoline = '''.section __TEXT_EXEC,__lmi_dpu,regular,pure_instructions
.p2align 2
.globl _lmi_dpu_original_show
_lmi_dpu_original_show:
    .long 0xd10703ff
    b __ZN19IOMobileFramebuffer4showEPKhPP13MiniIOSurface+4
'''
(evidence/'show-trampoline.S').write_text(trampoline)
run([toolbin/'xnu-clang','-arch','arm64','-c',evidence/'show-trampoline.S',
    '-o',out/'show-trampoline.o'], 'trampoline-compile.log')
run([*link,out/'lmi-dpu-snapshot.o',out/'show-trampoline.o','-o',out/'extension.unstripped'], 'extension-link.log')
run([toolbin/'strip','-S',out/'extension.unstripped','-o',out/'extension'], 'extension-strip.log')
assert {str(p):sha(p) for p in inputs}==initial, 'Source build inputs changed during isolated link'
nm = subprocess.check_output([str(toolbin/'nm'),'-n',str(out/'extension.unstripped')],env=env,text=True)
(evidence/'extension-symbols.txt').write_text(nm)
symbols = dict((name,va) for va,kind,name in audit['symbols'](nm))
moved = [dict(symbol=name,before=hex(va),after=hex(symbols[name]))
    for va,kind,name in old_symbols if name in symbols and symbols[name]!=va]
report = dict(result='LINKED_UNINTEGRATED',source_sha256=sha(source),
    kernel_sha256=sha(out/'extension'),new_entry=hex(symbols['_lmi_dpu_read_snapshot']),
    moved_symbols=moved,segments={name:[hex(v) for v in data]
        for name,data in audit['segments']((out/'extension').read_bytes()).items()},
    hardware_ready=False,device_access=False,
    next_step='Audit relocated runtime dependencies and explicit hook preimages before any device run')
(evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('moved_symbols','segments')},indent=2))
