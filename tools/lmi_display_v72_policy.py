"""Shorter input waits, with the exact v71 GPU/display admission unchanged."""
import json, shutil, struct
import lmi_display_v71_policy as prior
checked = prior.checked
KERNEL_SHA='1e76f68263c0e9c02d47fd2528f7f589087726f1d59fb96154e9b5c928077a8b'
AUDIT_SHA='4661701a99b1df1d90e785e300705960786a5f676e9d969d3262d88b94abe02d'
REVIEW_SHA='ef16b520ad7a52bbd11a34abb525481c10c01b1f4aa468c54725099517887105'
PRIOR_POLICY_SHA='2a5fb643808b90bbc42e69e3bff83190af5fa873248e84ea47b1793d43ec7c9e'


def stage(root, out):
    checked(root/'tools/lmi_display_v71_policy.py', PRIOR_POLICY_SHA)
    baseline, meta = prior.stage(root, out)
    folder = root/'out/lmi-touch-cadence-v72b'
    raw = checked(folder/'mach.development.bcm2837', KERNEL_SHA)
    audit = json.loads(checked(folder/'build-audit.json', AUDIT_SHA))
    review_path = root/'out/lmi-touch-cadence-v72b-review/result.json'
    review = json.loads(checked(review_path, REVIEW_SHA))
    assert review['result'] == 'PASS' and review['scenarios'] == 15
    for flag in ['actual_arm64_loop_emulated', 'independent_instruction_decode',
                 'original_decoder_events_and_reads_equal', 'finite_loop_cleanup_verified',
                 'idle_185_seconds_without_expiry', 'outside_edits_exact',
                 'bus_edges_unchanged', 'gpu_and_dpu_unchanged']:
        assert review[flag]
    for report in (audit, review):
        for name, digest in report['inputs'].items():
            checked(root/name, digest)
    original = baseline.read_bytes()
    assert audit['base_sha256'] == meta['sha256'] == prior.KERNEL_SHA
    assert audit['sha256'] == review['kernel_sha256'] == KERNEL_SHA
    assert len(raw) == len(original) and len(audit['edits']) == 3
    restored = bytearray(raw)
    expected = [(0xfffffff0074c2cb0, 0x713e827f, 0x7141927f),
                (0xfffffff0074c2d28, 0x52986a00, 0x5280fa00),
                (0xfffffff0074c2ec8, 0x5289c400, 0x52807d00)]
    # Independent checked PC-to-file mapping for the immutable native layout.
    for edit, (pc, old, new) in zip(audit['edits'], expected):
        at = edit['file_offset']
        assert int(edit['pc'], 16) == pc and at == pc-0xfffffff007004000
        assert struct.unpack_from('<I', original, at)[0] == old
        assert struct.unpack_from('<I', raw, at)[0] == new
        restored[at:at+4] = original[at:at+4]
    assert restored == original and not audit['hardware_tested'] and not audit['performance_verified']
    target = out/'display-v72-candidate'
    assert not target.exists()
    shutil.copytree(folder, target)
    shutil.copy2(review_path, target/'touch-loop-review.json')
    meta['display_v72'] = meta.pop('display_v71')
    meta['sha256'] = KERNEL_SHA
    meta['display_v72'].update(touch_cadence_changed=True, touch_parser_unchanged=True,
        touch_bus_edges_unchanged=True, touch_valid_pause_us=1000, touch_idle_pause_us=2000,
        touch_loop_limit=409600, gpu_and_dpu_unchanged_from_v71=True,
        touch_to_photon_measured=False, performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta, indent=2)+'\n')
    return target/'mach.development.bcm2837', meta

observe = prior.observe
validate_run = prior.validate_run
