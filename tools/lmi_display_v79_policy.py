"""One native wait immediate over v77, retaining its CPU and GPU admission."""
import hashlib
import json
import shutil
import lmi_display_v77_policy as prior

checked = prior.checked
KERNEL_SHA = 'e6f380af6a12a286caf5fbfdfa5cc62e040fd0a672107900ab17582a6cbc8ff4'
AUDIT_SHA = 'f9c5af7025978be3f43972b6d204a9d93441ccee65985a2256528c865753324b'
HOST_SHA = '4b8206d83112252135d8dc022a20543e5af1d0500f02708c54ff312afa6a76e8'
PRIOR_SHA = 'c6c86b633f0a83457630406fd25040d44a5af13c18fd173fe586bfa04bbc5b9c'
OFFSET = 0xfffffff0079e5a7c - 0xfffffff007004000


def verify_image(original, raw):
    assert hashlib.sha256(original).hexdigest() == prior.KERNEL_SHA
    assert hashlib.sha256(raw).hexdigest() == KERNEL_SHA
    assert len(raw) == len(original)
    assert original[OFFSET:OFFSET + 4] == bytes.fromhex('00198052')
    assert raw[OFFSET:OFFSET + 4] == bytes.fromhex('40068052')
    assert raw[:OFFSET] == original[:OFFSET] and raw[OFFSET + 4:] == original[OFFSET + 4:]


def stage(root, out):
    checked(root / 'tools/lmi_display_v77_policy.py', PRIOR_SHA)
    folder = root / 'out/lmi-render-cpu-v79'
    raw = checked(folder / 'mach.development.bcm2837', KERNEL_SHA)
    audit = json.loads(checked(folder / 'build-audit.json', AUDIT_SHA))
    host_path = root / 'out/lmi-render-cpu-v79-host/result.json'
    host = json.loads(checked(host_path, HOST_SHA))
    assert audit['base_sha256'] == prior.KERNEL_SHA and audit['sha256'] == KERNEL_SHA
    assert audit['allowed_file_ranges'] == [[OFFSET, OFFSET + 4]]
    assert audit['cpu_request_and_restore_exact'] and audit['native_gpu_poll_us'] == 50
    assert host['result'] == 'PASS' and host['kernel_sha256'] == KERNEL_SHA and host['scenarios'] == 15
    for key in ['original_native_function_executed', 'independent_instruction_decode',
                'one_instruction_only', 'whole_image_outside_word_exact',
                'allocation_cleanup_and_journal_exact',
                'native_lock_fence_elapsed_timeout_recovery_verified',
                'register_and_stack_abi_verified', 'machine_code_mutation_rejected']:
        assert host[key]
    for report in [audit, host]:
        for name, digest in report['inputs'].items():
            checked(root / name, digest)
    baseline, meta = prior.stage(root, out)
    assert meta['sha256'] == prior.KERNEL_SHA
    verify_image(baseline.read_bytes(), raw)
    target = out / 'display-v79-candidate'
    assert not target.exists()
    shutil.copytree(folder, target)
    shutil.copy2(host_path, target / 'native-wait-review.json')
    meta['display_v79'] = meta.pop('display_v77')
    meta['sha256'] = KERNEL_SHA
    meta['display_v79'].update(
        native_gpu_fence_poll_us=50, previous_native_gpu_fence_poll_us=200,
        independent_cpu_requests=True, original_cleanup_then_cpu_restore=True,
        v75_statistics_included=False, v74_busy_spin_included=False,
        all_prior_gpu_display_safety_required=True, performance_verified=False,
    )
    (target / 'execution-profile.json').write_text(json.dumps(meta, indent=2) + '\n')
    return target / 'mach.development.bcm2837', meta


observe = prior.observe
validate_run = prior.validate_run
