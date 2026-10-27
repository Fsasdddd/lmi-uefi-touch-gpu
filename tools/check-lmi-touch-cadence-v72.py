"""Emulate the actual patched ARM64 report loop; stub only external I/O.

This tests instruction/control flow and decoder semantics, not electrical I2C,
hardware report frequency, scheduler latency or physical touch-to-photon time.
"""
from pathlib import Path
import argparse, hashlib, json, re, struct, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'out/lmi-touch-v72-python'))
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm64_const as reg
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
import runpy
builder = runpy.run_path(str(ROOT/'tools/build-lmi-touch-cadence-v72.py'))
apply, BASE, BASE_SHA, PATCHES = (builder[k] for k in ('apply','BASE','BASE_SHA','PATCHES'))

parser = argparse.ArgumentParser()
parser.add_argument('--attempt', default='v72b')
args = parser.parse_args()
assert re.fullmatch(r'v72[a-z]', args.attempt)
OUT = ROOT/('out/lmi-touch-cadence-'+args.attempt+'-review')
OUT.mkdir(exist_ok=True)
assert not (OUT/'result.json').exists(), 'Preserve completed reviews'
attempt = OUT/('attempt-'+str(1+len(list(OUT.glob('attempt-*')))))
attempt.mkdir()
(attempt/'check-source.py').write_bytes(Path(__file__).read_bytes())
candidate = ROOT/('out/lmi-touch-cadence-'+args.attempt)
base, raw = BASE.read_bytes(), (candidate/'mach.development.bcm2837').read_bytes()
audit = json.loads((candidate/'build-audit.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert hashlib.sha256(base).hexdigest() == BASE_SHA
assert apply(base)[0] == raw and sha(candidate/'mach.development.bcm2837') == audit['sha256']
for name, digest in audit['inputs'].items():
    assert sha(ROOT/name) == digest, name
segments = runpy.run_path(str(ROOT/'tools/build-lmi-source-runtime.py'))['segments'](raw)


def offset(pc):
    return next(s[2]+pc-s[0] for s in segments.values() if s[0] <= pc < s[0]+s[3])


dis = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
decoded = []
for pc, old, new, purpose in PATCHES:
    insn, = dis.disasm(raw[offset(pc):offset(pc)+4], pc)
    decoded.append(dict(pc=hex(pc), mnemonic=insn.mnemonic, operands=insn.op_str))
assert [(x['mnemonic'], x['operands']) for x in decoded] == [
    ('cmp', 'w19, #0x64, lsl #12'), ('mov', 'w0, #0x7d0'), ('mov', 'w0, #0x3e8')]
# Independent restoration of the whole kernel, including every wire-timing,
# power/ID, GPU, DPU and HID-related byte outside the three instruction words.
restored = bytearray(raw)
for edit in audit['edits']:
    at = edit['file_offset']
    restored[at:at+4] = base[at:at+4]
assert restored == base


def packet(contacts=(), count=None):
    data = bytearray([255]*63)
    data[0:3] = bytes([0, 0, len([x for x in contacts if x[1] != 1]) if count is None else count])
    for n, (finger, phase, x, y) in enumerate(contacts):
        at = 3+6*n
        data[at:at+6] = bytes([(phase<<6)|(x>>8), x&255, (finger<<4)|(y>>8), y&255, 0, 0])
    return bytes(data)


def emulate(image, frames, *, lifetime=False, boundary=False):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    lo = 0xfffffff0074c2000
    uc.mem_map(lo, 0x4000)
    uc.mem_write(lo, image[offset(lo):offset(lo)+0x4000])
    stack = 0x100000
    uc.mem_map(stack, 0x10000)
    uc.reg_write(reg.UC_ARM64_REG_SP, stack+0x8000)
    uc.reg_write(reg.UC_ARM64_REG_X29, stack+0x8100)
    # Dominating ID/mode gate sets w23=1 at 0x...2c5c before this loop entry.
    uc.reg_write(reg.UC_ARM64_REG_X23, 1)
    state = dict(index=0, ticks=0, loop=0, ended=False, stopped=False, reads=[], pauses=[], events=[])
    is_new = image == raw
    limit = 409600 if is_new else 4000

    def ret():
        uc.reg_write(reg.UC_ARM64_REG_PC, uc.reg_read(reg.UC_ARM64_REG_X30))

    def read(uc, pc, size, _):
        n = uc.reg_read(reg.UC_ARM64_REG_X3)
        assert n in (3, 63)
        frame = frames[state['index'] % len(frames)] if lifetime else frames[state['index']]
        state['reads'].append(n)
        state['ticks'] += 600 if n == 3 else 10000  # modeled; not a hardware measurement
        full_failure = isinstance(frame, dict)
        if full_failure:
            frame = frame['full_failure']
        ok = frame is not None and not (full_failure and n == 63)
        if ok:
            uc.mem_write(uc.reg_read(reg.UC_ARM64_REG_X2), frame[:n])
        if not ok or n == 63 or not (frame[2]&15) or (frame[2]&15) > 10:
            state['index'] += 1
        uc.reg_write(reg.UC_ARM64_REG_X0, int(ok))
        ret()

    def pause(uc, pc, size, _):
        us = uc.reg_read(reg.UC_ARM64_REG_X0)
        state['pauses'].append(us)
        state['ticks'] += us
        ret()

    def post(uc, pc, size, _):
        state['events'].append([uc.reg_read(getattr(reg, 'UC_ARM64_REG_X'+str(i))) for i in range(4)])
        ret()

    def nop(uc, pc, size, _):
        ret()

    def loop(uc, pc, size, _):
        state['loop'] += 1
        if boundary and state['loop'] == 1:
            uc.reg_write(reg.UC_ARM64_REG_X19, limit-1)
        if lifetime:
            if state['ticks'] >= 185_000_000:
                state['stopped'] = True
                uc.emu_stop()
        elif state['index'] >= len(frames):
            uc.reg_write(reg.UC_ARM64_REG_X19, limit)

    def ended(uc, pc, size, _):
        state['ended'] = True
        uc.emu_stop()

    for pc, callback in [(0xfffffff0074c3b7c, read), (0xfffffff0074c3b34, pause),
        (0xfffffff0074c1a08, post), (0xfffffff00745a8d8, nop), (0xfffffff007472244, nop),
        (0xfffffff0074c2cb0, loop), (0xfffffff0074c2f20, ended)]:
        # Hooks can point to an external entry, so map each stub page as needed.
        page = pc & ~4095
        if not lo <= page < lo+0x4000:
            try:
                uc.mem_map(page, 4096)
            except Exception:
                pass
            uc.mem_write(pc, bytes.fromhex('c0035fd6'))
        uc.hook_add(UC_HOOK_CODE, callback, begin=pc, end=pc)
    uc.emu_start(0xfffffff0074c2c7c, 0, count=50_000_000)
    assert state['ended'] or state['stopped'], 'Emulation did not reach a defined stop'
    return state


cases = {
    'idle': [packet()]*3,
    'tap': [packet([(0,0,100,500)]), packet([(0,1,100,500)], count=0)],
    'swipe-final-position': [packet([(0,0,100,500)]), packet([(0,2,400,600)]), packet([(0,1,950,700)], count=0)],
    'missing-up': [packet([(0,0,123,456)]), packet()],
    'multitouch': [packet([(2,0,100,200),(5,0,300,400)]), packet([(2,1,800,200),(5,2,350,400)], count=1), packet()],
    'duplicate-live-id': [packet([(0,0,100,500)]), packet([(0,2,400,500),(0,2,800,500)]), packet()],
    'cold-ff': [bytes([255]*63), packet()],
    'read-failure': [None]*64,
    'transient-read-failure': [None, packet([(0,0,100,500)]), None, packet()],
    'first-full-read-failure': [{'full_failure': packet([(0,0,100,500)])}, packet()],
    'coordinate-clamp': [packet([(0,0,4095,4095)]), packet()],
    'cleanup-active-contact': [packet([(0,0,123,456)])],
}
results = {}
for name, frames in cases.items():
    before, after = emulate(base, frames), emulate(raw, frames)
    assert before['events'] == after['events'], name
    assert before['reads'] == after['reads'], name
    assert before['index'] == after['index'], name
    # Error and cold-report paths retain their original backoff durations.
    if name == 'read-failure':
        assert len(after['reads']) == 64 and set(after['pauses']) == {20000}
    if name == 'cold-ff':
        assert after['pauses'][0] == 200000
    if name == 'swipe-final-position':
        assert after['events'][-1] == [3, 0, 950*65535//1079, 700*65535//2399], after['events']
        assert after['pauses'] == [1000]*3
    if name == 'idle':
        assert after['pauses'] == [2000]*3 and not after['events']
    results[name] = dict(events=after['events'], read_lengths=after['reads'], pauses_us=after['pauses'])
for frames in ([packet()], [packet([(0,0,100,500)])]):
    # Execute the real final iteration, including release of an active contact.
    before, after = emulate(base, frames, boundary=True), emulate(raw, frames, boundary=True)
    assert before['ended'] and after['ended'] and before['events'] == after['events']
idle = emulate(raw, [packet()], lifetime=True)
assert idle['stopped'] and not idle['ended'] and idle['loop'] > 4000 and not idle['events']
results['185-second-idle-no-early-expiry'] = dict(modeled_time_us=idle['ticks'], loops=idle['loop'])
report = dict(result='PASS', scenarios=len(cases)+3, kernel_sha256=audit['sha256'],
    actual_arm64_loop_emulated=True, independent_instruction_decode=True,
    original_decoder_events_and_reads_equal=True, finite_loop_cleanup_verified=True,
    idle_185_seconds_without_expiry=True, outside_edits_exact=True,
    bus_edges_unchanged=True, gpu_and_dpu_unchanged=True, instructions=decoded, cases=results,
    hardware_tested=False, performance_verified=False,
    limitation='External report reads, yielding delays, posting and diagnostic calls are stubbed. Elapsed time is modeled and is not hardware performance evidence.',
    inputs={str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), candidate/'build-audit.json',
        ROOT/'tools/build-lmi-touch-cadence-v72.py']})
(OUT/'result.json').write_text(json.dumps(report, indent=2)+'\n')
print('PASS:', report['scenarios'], 'actual ARM64 loop scenarios, independent decode and exact untouched-kernel restoration')
