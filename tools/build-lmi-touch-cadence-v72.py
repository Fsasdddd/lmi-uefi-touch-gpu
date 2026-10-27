"""Three guarded immediate changes on the exact reviewed v71 image.

No code relocation or change to FT3518 wire timing, parsing, chip-ID gates,
power/reset sequencing, error thresholds, HID init, GPU or DPU ownership.
"""
from pathlib import Path
import argparse, hashlib, json, re, runpy, struct

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'out/lmi-gpu-deferred-cache-v71/mach.development.bcm2837'
BASE_SHA = 'be0c25e5e871fe0b1d7f8378ec72eaf7b89414bcd675e07fc8219e4e18d9cf40'
# PC, exact preimage, replacement, purpose. CMP has an explicit 12-bit shift.
PATCHES = [
    (0xfffffff0074c2cb0, 0x713e827f, 0x7141927f, 'Finite loop limit 4000 -> 409600; minimum 1ms yielding pause prevents early expiry during the RAM run'),
    (0xfffffff0074c2d28, 0x52986a00, 0x5280fa00, 'Idle/header retry pause 50000us -> 2000us'),
    (0xfffffff0074c2ec8, 0x5289c400, 0x52807d00, 'Valid report pause 20000us -> 1000us'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(raw):
    assert hashlib.sha256(raw).hexdigest() == BASE_SHA
    segs = runpy.run_path(str(ROOT/'tools/build-lmi-source-runtime.py'))['segments'](raw)
    output = bytearray(raw)
    edits = []
    for pc, old, new, purpose in PATCHES:
        hits = [s[2]+pc-s[0] for s in segs.values() if s[0] <= pc and pc+4 <= s[0]+s[3]]
        assert len(hits) == 1
        at = hits[0]
        assert struct.unpack_from('<I', raw, at)[0] == old
        struct.pack_into('<I', output, at, new)
        edits.append(dict(pc=hex(pc), file_offset=at, old=hex(old), new=hex(new), purpose=purpose))
    restored = bytearray(output)
    for edit in edits:
        at = edit['file_offset']
        restored[at:at+4] = raw[at:at+4]
    assert restored == raw and len(output) == len(raw)
    return bytes(output), edits


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', default='v72b')
    args = parser.parse_args()
    assert re.fullmatch(r'v72[a-z]', args.attempt)
    out = ROOT/('out/lmi-touch-cadence-'+args.attempt)
    assert not out.exists(), 'Preserve existing candidates'
    raw, edits = apply(BASE.read_bytes())
    out.mkdir()
    (out/'mach.development.bcm2837').write_bytes(raw)
    report = dict(result='HOST_BUILT_ONLY', base_sha256=BASE_SHA,
        sha256=hashlib.sha256(raw).hexdigest(), edits=edits, outside_edits_exact=True,
        changed_instruction_bytes=12, active_pause_us=1000, idle_pause_us=2000,
        iteration_limit=409600, error_pause_us=20000, cold_invalid_pause_us=200000,
        min_valid_loop_lifetime_seconds=409.6, bus_edges_unchanged=True,
        touch_parser_unchanged=True, init_and_chip_id_gates_unchanged=True,
        gpu_and_dpu_unchanged=True, hardware_tested=False, performance_verified=False,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in
            [Path(__file__), BASE, ROOT/'tools/lmi-touch.c', ROOT/'tools/lmi-touch-timing.h',
             ROOT/'out/lmi-kernel-ios-continue/touch.elf', ROOT/'out/lmi-kernel-ios-continue/touch-disassembly.txt']})
    (out/'build-audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
