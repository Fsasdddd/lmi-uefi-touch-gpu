"""Apply the frozen lmi runtime to one audited source reconstruction.

This first migration deliberately requires unchanged executable symbol addresses.
It rejects unrecognized source kernels and changes outside audited replacement
bodies. It does not infer that a linked kernel has passed a hardware run.
"""
from pathlib import Path
import bisect
import hashlib
import json
import runpy
import struct

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SHA = '9239d4adb7a2c433d7ed5729b47b63acc5281af73d8a81640ef3c678c8afd26c'
RUNTIME_SHA = '27a3a6a9eaf5a1f3e0b0a76cc19c5dbdce1ac6e879b59f7ec44e672b0288ed08'
SOURCE_SHA = '0a8e5f2be56ed8538d361cf570799b49792270f51383f8b71c584c96fca8e0d5'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def segments(raw):
    assert struct.unpack_from('<I', raw)[0] == 0xfeedfacf
    result = {}
    pos = 32
    for _ in range(struct.unpack_from('<I', raw, 16)[0]):
        command, size = struct.unpack_from('<II', raw, pos)
        assert 8 <= size <= len(raw)-pos
        if command == 25:
            name = raw[pos+8:pos+24].rstrip(b'\0').decode()
            result[name] = struct.unpack_from('<QQQQ', raw, pos+24)
        pos += size
    return result


def symbols(text):
    return [(int(v[0],16), v[1], v[2]) for line in text.splitlines()
            if len(v := line.split(maxsplit=2)) == 3]


def elf_absolutes(raw):
    assert raw[:6] == b'\x7fELF\x02\x01'
    at = struct.unpack_from('<Q', raw, 40)[0]
    size, count = struct.unpack_from('<HH', raw, 58)
    sections = [struct.unpack_from('<IIQQQQIIQQ',raw,at+i*size) for i in range(count)]
    result = {}
    for section in sections:
        if section[1] != 2:
            continue
        strings = sections[section[6]]
        names = raw[strings[4]:strings[4]+strings[5]]
        for pos in range(section[4], section[4]+section[5], section[9]):
            name, info, other, index, value, length = struct.unpack_from('<IBBHQQ',raw,pos)
            if index == 0xfff1 and value >= 0xfffffff007004000:
                result[names[name:names.index(b'\0',name)].decode()] = value
    return result


def migrate(original, runtime, source, original_symbols, source_symbols, regions):
    assert sha(original) == ORIGINAL_SHA and sha(runtime) == RUNTIME_SHA
    assert sha(source) == SOURCE_SHA
    oldseg, rtseg, newseg = map(segments, (original,runtime,source))
    assert oldseg == rtseg == newseg, 'Mach-O layout changed'
    # cctools nm labels even __TEXT_EXEC functions as S/s. Use the actual
    # executable segment's addresses instead of ELF-style T/t classification.
    a, b = symbols(original_symbols), symbols(source_symbols)
    text_va,text_size,_,_ = oldseg['__TEXT_EXEC']
    original_code = sorted((va,name) for va,kind,name in a if text_va <= va < text_va+text_size)
    candidate_code = sorted((va,name) for va,kind,name in b if text_va <= va < text_va+text_size)
    assert original_code and original_code == candidate_code, 'Executable symbols moved'
    result = bytearray(source)
    edits = []
    for name,(va,vs,fo,fs) in oldseg.items():
        if not fs or name in ('__LINKEDIT','__LINKINFO'):
            continue
        step = 4 if name == '__TEXT_EXEC' else 8
        for offset in range(0,fs,step):
            start = fo+offset
            before, after = original[start:start+step], runtime[start:start+step]
            if before == after:
                continue
            address = va+offset
            borrowed = any(begin <= address and address+step <= end for begin,end in regions)
            assert borrowed or source[start:start+step] == before, ('Source preimage changed',hex(address))
            result[start:start+step] = after
            edits.append(dict(va=hex(address),bytes=step,borrowed_body=borrowed))
    # Copy complete replacement bodies. A coincidentally equal old instruction
    # must not leave a source compiler's different instruction inside new code.
    for begin,end in regions:
        segment = next(s for s in oldseg.values() if s[0] <= begin and end <= s[0]+s[3])
        at = segment[2]+begin-segment[0]
        result[at:at+end-begin] = runtime[at:at+end-begin]
    assert len(result) == len(source)
    return bytes(result), edits


def main():
    baseline = ROOT/'out/lmi-kernel-source-build-v36/reconstruct-base'
    out = ROOT/'out/lmi-kernel-source-runtime-v36'
    assert not out.exists(), 'Preserve existing source runtime candidate'
    original = (ROOT/'hackios/prebuilt/mach.development.bcm2837').read_bytes()
    runtime_folder = ROOT/'out/lmi-kernel-ios-continue'
    runtime = (runtime_folder/'mach.development.bcm2837').read_bytes()
    source = (baseline/'mach.development.bcm2837').read_bytes()
    assert sha(source) == SOURCE_SHA
    oldtext = (ROOT/'out/kernel-symbols.txt').read_text()
    newtext = (baseline/'kernel-symbols.txt').read_text()
    newsymbols = {name:va for va,kind,name in symbols(newtext)}
    oldsymbols = sorted((va,name) for va,kind,name in symbols(oldtext))
    addresses = [va for va,name in oldsymbols]
    alias_checks = []
    for name in ['touch.elf','probe.elf']:
        for alias,value in elf_absolutes((runtime_folder/name).read_bytes()).items():
            index = bisect.bisect_right(addresses,value)-1
            va,symbol = oldsymbols[index]
            assert newsymbols[symbol] == va, ('Runtime dependency moved',alias,symbol)
            alias_checks.append(dict(image=name,alias=alias,symbol=symbol,offset=hex(value-va)))
    audits = []
    regions = [(newsymbols['_goodix_thread'],newsymbols['_redwood_spmi_lock'])]
    source_c = (ROOT/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text()
    for script in ['init-region','frame-region','unsecure-region','normal-diag-region','desktop-region']:
        module = runpy.run_path(str(ROOT/f'tools/audit-lmi-gpu-{script}.py'))
        audit = module['audit']
        # This adapter admits only SOURCE_SHA above. Canonical auditors keep
        # their original pin; all their reference/entry/table checks still run.
        audit.__globals__['KERNEL_SHA'] = SOURCE_SHA
        report = audit(source) if script == 'init-region' else audit(source,newtext,source_c)
        audits.append(report)
        regions.append((int(report['entry'],16),int(report['end'],16)))
    module = runpy.run_path(str(ROOT/'tools/audit-lmi-gpu-padding.py'))
    audit = module['audit']; audit.__globals__['KERNEL_SHA'] = SOURCE_SHA
    audits.append(audit(source,newtext,END=0xfffffff007ae0000))
    result, edits = migrate(original,runtime,source,oldtext,newtext,regions)
    assert result != runtime and result != source
    out.mkdir()
    (out/'mach.development.bcm2837').write_bytes(result)
    (out/'kernel-symbols.txt').write_text(newtext)
    audit_report = dict(result='PASS',original_sha256=ORIGINAL_SHA,runtime_sha256=RUNTIME_SHA,
        source_sha256=SOURCE_SHA,candidate_sha256=sha(result),
        executable_symbol_addresses_unchanged=True,runtime_dependencies=alias_checks,
        borrowed_regions=[dict(start=hex(a),end=hex(b)) for a,b in regions],
        region_audits=audits,edits=edits,hardware_tested=False,
        limitation='This migration is pinned to the reconstructed layout; new driver layout changes require a separate migration')
    (out/'source-runtime-audit.json').write_text(json.dumps(audit_report,indent=2)+'\n')
    meta = json.loads((runtime_folder/'manifest.json').read_text())
    meta.update(sha256=sha(result),source_sha256=SOURCE_SHA,hardware_tested=False)
    meta['source_rebuild'] = dict(enabled=True,baseline_runtime_sha256=RUNTIME_SHA,
        audit_sha256=sha((out/'source-runtime-audit.json').read_bytes()),
        builder_sha256=sha(Path(__file__).read_bytes()))
    (out/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps(dict(result='PASS',candidate_sha256=sha(result),modified_units=len(edits),
                         checked_runtime_aliases=len(alias_checks),hardware_tested=False),indent=2))


if __name__ == '__main__':
    main()
