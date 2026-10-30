"""Combine v77's verified CPU lifecycle with one native GPU wait immediate."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'out/lmi-cpu-epss-v77e/mach.development.bcm2837'
BASE_SHA = 'ca0b8c221f8318f1447b043e7e31bf944a6baadfa9647a83afb409b2bad4a901'
PC = 0xfffffff0079e5a7c
OFFSET = PC - 0xfffffff007004000
OLD, NEW = 0x52801900, 0x52800640


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    folder = ROOT / 'out/lmi-render-cpu-v79'
    assert not folder.exists(), 'Preserve previous build attempts'
    original = BASE.read_bytes()
    assert sha(BASE) == BASE_SHA
    assert struct.unpack_from('<I', original, OFFSET)[0] == OLD
    raw = bytearray(original)
    struct.pack_into('<I', raw, OFFSET, NEW)
    restored = bytearray(raw)
    struct.pack_into('<I', restored, OFFSET, OLD)
    assert restored == original
    folder.mkdir()
    candidate = folder / 'mach.development.bcm2837'
    candidate.write_bytes(raw)
    audit = dict(
        result='HOST_BUILT_ONLY', base_sha256=BASE_SHA, sha256=sha(candidate),
        patch_pc=hex(PC), allowed_file_ranges=[[OFFSET, OFFSET + 4]],
        old_word=hex(OLD), new_word=hex(NEW), original_gpu_poll_us=200,
        native_gpu_poll_us=50, outside_edits_exact=True,
        cpu_request_and_restore_exact=True, v72_touch_preserved=True,
        dpu_and_cache_ownership_exact=True, smp_and_cleanup_exact=True,
        original_fence_deadline_recovery_exact=True,
        v75_statistics_included=False, v74_busy_spin_included=False,
        hardware_tested=False, performance_verified=False, wifi_integrated=False,
        inputs={p.relative_to(ROOT).as_posix(): sha(p) for p in [Path(__file__), BASE]},
    )
    (folder / 'build-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps({k: audit[k] for k in ['result', 'sha256', 'native_gpu_poll_us']}, indent=2))
