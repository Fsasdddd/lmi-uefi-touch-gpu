"""Build an isolated 50us native GPU wait from v73, with no new wrappers."""
from pathlib import Path
import hashlib, json, struct

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837'
BASE_SHA = '68ec1820fea704e99ab1ccac5d70f19670faa9428378f75592f251ff5ede56c2'
PC = 0xfffffff0079e5a7c
OFFSET = PC - 0xfffffff007004000
OLD, NEW = 0x52801900, 0x52800640

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

if __name__ == '__main__':
    out = ROOT/'out/lmi-render-minimal-v76'
    assert not out.exists(), 'Preserve all previous build attempts'
    original = BASE.read_bytes()
    assert sha(BASE) == BASE_SHA
    assert struct.unpack_from('<I', original, OFFSET)[0] == OLD
    raw = bytearray(original)
    struct.pack_into('<I', raw, OFFSET, NEW)
    restored = bytearray(raw)
    struct.pack_into('<I', restored, OFFSET, OLD)
    assert restored == original
    out.mkdir()
    (out/'mach.development.bcm2837').write_bytes(raw)
    audit = dict(result='HOST_BUILT_ONLY', base_sha256=BASE_SHA,
        sha256=hashlib.sha256(raw).hexdigest(), patch_pc=hex(PC),
        allowed_file_ranges=[[OFFSET, OFFSET+4]], old_word=hex(OLD), new_word=hex(NEW),
        original_gpu_poll_us=200, native_gpu_poll_us=50,
        v75_statistics_included=False, v74_busy_spin_included=False,
        outside_edits_exact=True, v73_alloc_cleanup_exact=True,
        v72_touch_preserved=True, dpu_and_cache_ownership_exact=True,
        original_fence_deadline_recovery_exact=True,
        hardware_tested=False, performance_verified=False, wifi_integrated=False,
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__), BASE]})
    (out/'build-audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    print(json.dumps({k:audit[k] for k in ['result','sha256','patch_pc','native_gpu_poll_us']}, indent=2))
