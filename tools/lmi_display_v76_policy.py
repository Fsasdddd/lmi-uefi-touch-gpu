"""v76: one native wait immediate, with the complete unchanged v73 admission."""
import hashlib, json, shutil
import lmi_display_v73_policy as prior

checked=prior.checked
KERNEL_SHA='95249539aab5a25759f3972ae2b59c8cd6e3494052c678ac6dfb6ad0aa2ff318'
AUDIT_SHA='ff4d744e01d9b3f40721a52be6f37d7fab1c42c49ac6b36bc413865ec1206f49'
HOST_SHA='25e24998c08074dc1f325bc5fda7d6d23e2ba1a1d9b046f8af439ad3cbbea540'
PRIOR_SHA='8cf330b0787fe9c4a8aa393e3d5a6237f07bee3ec97444f6015dae273b961ee3'
OFFSET=0xfffffff0079e5a7c-0xfffffff007004000

def verify_image(original,raw):
    assert hashlib.sha256(original).hexdigest()==prior.KERNEL_SHA
    assert hashlib.sha256(raw).hexdigest()==KERNEL_SHA
    assert len(raw)==len(original)
    assert original[OFFSET:OFFSET+4]==bytes.fromhex('00198052')
    assert raw[OFFSET:OFFSET+4]==bytes.fromhex('40068052')
    assert raw[:OFFSET]==original[:OFFSET] and raw[OFFSET+4:]==original[OFFSET+4:]

def stage(root,out):
    checked(root/'tools/lmi_display_v73_policy.py',PRIOR_SHA)
    folder=root/'out/lmi-render-minimal-v76'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host_path=root/'out/lmi-render-minimal-v76b-host/result.json'
    host=json.loads(checked(host_path,HOST_SHA))
    assert audit['base_sha256']==prior.KERNEL_SHA and audit['sha256']==KERNEL_SHA
    assert audit['allowed_file_ranges']==[[OFFSET,OFFSET+4]]
    assert host['result']=='PASS' and host['kernel_sha256']==KERNEL_SHA and host['scenarios']==15
    for key in ['original_native_function_executed','independent_instruction_decode',
            'one_instruction_only','whole_image_outside_word_exact','allocation_cleanup_and_journal_exact',
            'native_lock_fence_elapsed_timeout_recovery_verified','register_and_stack_abi_verified',
            'machine_code_mutation_rejected']:assert host[key]
    for report in [audit,host]:
        for name,digest in report['inputs'].items():checked(root/name,digest)
    verify_image(checked(root/'out/lmi-display-timing-v73/mach.development.bcm2837',prior.KERNEL_SHA),raw)
    baseline,meta=prior.stage(root,out)
    assert meta['sha256']==prior.KERNEL_SHA
    verify_image(baseline.read_bytes(),raw)
    target=out/'display-v76-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(host_path,target/'native-wait-host-review.json')
    meta['display_v76']=meta.pop('display_v73');meta['sha256']=KERNEL_SHA
    meta['display_v76'].update(performance_change=True,performance_verified=False,
        native_gpu_fence_poll_us=50,previous_native_gpu_fence_poll_us=200,
        v75_statistics_included=False,v74_busy_spin_included=False,
        v73_allocation_cleanup_and_journal_exact=True,all_prior_gpu_display_safety_required=True)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

# No v75 records are emitted or fabricated. Every v73 timing/fence/source/DPU
# check is used directly; the original legacy verification also remains separate.
observe=prior.observe
validate_run=prior.validate_run
