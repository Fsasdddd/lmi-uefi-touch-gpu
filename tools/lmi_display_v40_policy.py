"""Pinned admission policy for the v40 read-only DPU RAM candidate.

The v36 execution profile is inherited only after checking its immutable
provenance and v40's relocation proofs. No old-layout hash gate is relaxed.
"""
from pathlib import Path
import hashlib
import json
import shutil

KERNEL_SHA = '3f33d8891b3e3640d7c5b834ee487eeaa0f561e5c835b6a10b9b733608d9c42c'
BASE_SHA = '98ef20d5c5bf4a902982840ee0529f36c0594995e7d2ed6c1caed93e4798b8fc'
MANIFEST_SHA = 'abaabb1ac8fb9ecbd3f2a9122c6156475d224da36c742f683bfaa8a434f1f314'
BASE_MANIFEST_SHA = '4362d4473f0728fbf50eaf7e72e639d0eee8f3cbeb1de21887f4d437fa8c978a'
IMAGE_SHA = '8077295ddfd9eb16e05aa73e47c5ae9d8ecbcaf78cf2023b813a395edd8f9cc9'


def checked(path, expected):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected, 'Changed v40 input: ' + str(path)
    return raw


def validate(root, sealed=None):
    root = Path(root)
    sealed = Path(sealed) if sealed is not None else root/'out/lmi-display-v40-paused'
    manifest = json.loads(checked(sealed/'manifest.json', MANIFEST_SHA))
    for name, digest in manifest['files'].items():
        checked(sealed/Path(name.replace('\\', '/')), digest)
    assert manifest['kernel_sha256'] == KERNEL_SHA
    assert manifest['kernel_bytes'] == (sealed/'mach.development.bcm2837').stat().st_size
    assert not manifest['persistent_storage_writes']
    host = json.loads((sealed/'host-check.json').read_text())
    assert host['result'] == 'PASS' and host['kernel_sha256'] == KERNEL_SHA
    assert host['readonly_dpu_observer'] and host['relinked_early_thunks'] == 7
    assert host['moved_runtime_bindings'] == 16
    for name, digest in host['source_sha256'].items():
        checked(root/'tools'/name, digest)
    audit = json.loads((sealed/'integration-audit.json').read_text())
    assert audit['result'] == 'INTEGRATED_HOST_ONLY'
    assert audit['sha256'] == KERNEL_SHA and audit['runtime_sha256'] == BASE_SHA
    assert audit['runtime_bindings_relinked'] and audit['executable_symbol_addresses_unchanged']
    assert audit['show_hook']['register_writes'] is False
    assert len(audit['accepted_abi_relocations']) == 6
    relocation = json.loads((sealed/'runtime-relocation.json').read_text())
    early = json.loads((sealed/'early-thunk-relocation.json').read_text())
    assert relocation['extension_sha256'] == audit['source_sha256']
    assert len(early['thunks']) == 7
    for proof in list(relocation['runtime'].values()) + list(early['thunks'].values()):
        assert proof['baseline_allocated_bytes_exact']
    base = root/'out/lmi-kernel-source-runtime-v36'
    meta = json.loads(checked(base/'manifest.json', BASE_MANIFEST_SHA))
    checked(base/'mach.development.bcm2837', BASE_SHA)
    rebuild = meta['source_rebuild']
    old_audit = json.loads(checked(base/'source-runtime-audit.json', rebuild['audit_sha256']))
    checked(root/'tools/build-lmi-source-runtime.py', rebuild['builder_sha256'])
    assert old_audit['result'] == 'PASS' and old_audit['candidate_sha256'] == BASE_SHA
    assert old_audit['runtime_sha256'] == rebuild['baseline_runtime_sha256']
    checked(root/manifest['input_image'], IMAGE_SHA)
    # Preserve all existing feature/return constraints, but identify this as a
    # distinct candidate rather than claiming it is the fixed-layout rebuild.
    del meta['source_rebuild']
    meta['sha256'] = KERNEL_SHA
    meta['display_v40'] = dict(
        sealed_manifest_sha256=MANIFEST_SHA, baseline_sha256=BASE_SHA,
        baseline_runtime_sha256=rebuild['baseline_runtime_sha256'],
        readonly=True, synchronized_present=False, hardware_verified=False)
    return sealed, meta


def stage(root, out):
    sealed, meta = validate(root)
    folder = out/'display-v40-candidate'
    assert not folder.exists(), 'Preserve existing v40 staging directory'
    shutil.copytree(sealed, folder)
    # Keep the original sealed manifest and write the inherited execution
    # profile separately for the generic checkpoint tester.
    (folder/'execution-profile.json').write_text(json.dumps(meta, indent=2)+'\n')
    return folder/'mach.development.bcm2837', meta
