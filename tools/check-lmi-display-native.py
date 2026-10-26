"""Compile the new modules only; reject code/constants outside the RX extension.

This is not a kernel link, a runnable image or validation of native services.
General-register-only compilation also avoids unowned SIMD state and compiler
literal sections that would otherwise move the frozen kernel's original data.
"""
from pathlib import Path
import hashlib
import json
import struct
import subprocess

root = Path(__file__).resolve().parents[1]
out = root / 'out/lmi-display-dma-host'
out.mkdir(exist_ok=True)
compiler = Path('/root/hackios-lmi/kernel-build-v36/xnu-deps/host/bin/xnu-clang')
flags = ['-arch', 'arm64', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
         '-ffreestanding', '-mgeneral-regs-only', '-fno-jump-tables',
         '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
         '-DLMI_PIPELINE_NATIVE']
reports, defined, undefined = {}, set(), set()
for name in ('pipeline', 'dma'):
    source = root / f'tools/lmi-display-{name}.c'
    obj = out / f'{name}.arm64.o'
    result = subprocess.run([str(compiler), *flags, '-c', str(source), '-o', str(obj)],
                            text=True, capture_output=True)
    (out / f'{name}.arm64.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    raw = obj.read_bytes()
    magic, cpu, _, kind, ncmd, _, _, _ = struct.unpack_from('<8I', raw)
    assert (magic, cpu, kind) == (0xfeedfacf, 0x100000c, 1)
    at, sections, symtab = 32, [], None
    for _ in range(ncmd):
        cmd, size = struct.unpack_from('<II', raw, at)
        if cmd == 0x19:
            count, = struct.unpack_from('<I', raw, at + 64)
            for n in range(count):
                section = struct.unpack_from('<16s16sQQIIIIIIII', raw, at + 72 + 80*n)
                sect, seg = [s.rstrip(b'\0').decode() for s in section[:2]]
                length = section[3]
                assert not length or (seg == '__TEXT_EXEC' and sect in ('__lmi_dpu', '__lmi_ro')), (seg, sect)
                sections.append(dict(segment=seg, section=sect, bytes=length))
        if cmd == 2:
            symtab = struct.unpack_from('<4I', raw, at + 8)
        at += size
    assert symtab
    symoff, count, stroff, _ = symtab
    for n in range(count):
        string, typ, section, _, _ = struct.unpack_from('<IBBHQ', raw, symoff + 16*n)
        symbol = raw[stroff+string:raw.index(b'\0', stroff+string)].decode()
        if (typ & 0x0e) == 0 and symbol:
            undefined.add(symbol)
        elif (typ & 0x0e) == 0x0e:
            assert 0 < section <= len(sections)
            defined.add(symbol)
    reports[name] = dict(sha256=hashlib.sha256(raw).hexdigest(), sections=sections,
                         source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
assert not undefined - defined, undefined - defined
total = sum(s['bytes'] for r in reports.values() for s in r['sections'])
assert total < 16384, 'Modules alone exhaust the reserved RX page'
report = dict(result='PASS', modules=reports, module_section_bytes=total,
              reserved_page_bytes=16384, compile_flags=flags,
              headers={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (root/'tools/lmi-display-pipeline.h', root/'tools/lmi-display-dma.h')},
              extension_linked=False, original_layout_verified=False, hardware_tested=False,
              desktop_integrated=False, scaler_pixel_validated=False)
(out/'native-result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
