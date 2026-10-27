"""Pinned GPU map batching with the v62 display/source-release checks."""
import json,re,shutil,struct
import lmi_display_v62_policy as prior
checked=prior.checked
KERNEL_SHA='baa6d3ef46691f8fbeb8fe93ffbbf31e2ebf6450bb4684e57d90873147d52ccc'
AUDIT_SHA='12980265443d6a57d270684880e145453d933c1bd6b87e7367534806b45e5c08'
HOST_SHA='6b515b726400f167ad426df9559dd3da24a61f8461e3f30dd7153c6190afc088'
NATIVE_HOST_SHA='32f600a1b11c9f4385da2abf63f9746d1c5389ca9352c70e2490498e43efd457'
PRIOR_SHA='1205788ac414c8f84be6c902e43f0397c6534e50537b977d2b780ece0d6569ec'
RANGES=[[5069960,5075016],[5038548,5038612],[5042720,5042788],[11381148,11381152],
 [5037684,5037688],[5038236,5038240],[5038544,5038548],[5040548,5040552],[5040628,5040632],
 [5040640,5040644],[5041788,5041792],[5042348,5042352],[5042464,5042468],[5042800,5042804],
 [5042840,5042844],[5042852,5042856],[5043448,5043452],[5044580,5044584],[5045328,5045332],
 [4574416,4574420]]

def stage(root,out):
    checked(root/'tools/lmi_display_v62_policy.py',PRIOR_SHA)
    baseline,meta=prior.stage(root,out)
    folder=root/'out/lmi-gpu-map-v63c'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-gpu-map-v63-host/result.json',HOST_SHA))
    assert host['result']=='PASS' and host['asan_ubsan'] and host['scenarios']==56
    assert len(host['mutations_caught'])==5 and not host['hardware_tested']
    native_host=json.loads(checked(root/'out/lmi-gpu-map-v63-native-host/result.json',NATIVE_HOST_SHA))
    assert native_host['result']=='PASS' and native_host['asan_ubsan'] and native_host['scenarios']==16
    assert native_host['native_page_table_routines_verbatim'] and native_host['cpu_device_memory_separate']
    assert not native_host['hardware_tested'] and '-fno-sanitize-recover=all' in native_host['command']
    for name,digest in native_host['inputs'].items():checked(root/name,digest)
    checked(root/'out/lmi-gpu-map-v63-native-host/check.c',native_host['generated_source_sha256'])
    for report in (audit,host):
        for name,digest in report['sources'].items():checked(root/'tools'/name,digest)
    for name,digest in audit['inputs'].items():checked(root/name,digest)
    for name,digest in audit['object_inputs'].items():checked(root/'out/lmi-kernel-ios-continue'/name,digest)
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    assert audit['allowed_file_ranges']==RANGES and len(audit['hooks'])==16
    for name in ['outside_edits_exact','display_fence_bytes_preserved','cleanup_rebound_to_v62',
                 'dma_attributes_unchanged','first_page_real_drain','commit_real_drain',
                 'native_map_batch_under_gpu_lock','single_outstanding']:
        assert audit[name]
    assert not audit['direct_surface_dma'] and not audit['hardware_tested']
    assert [(s['start'],s['bytes'],s['capacity']) for s in audit['sections']]==[
      ('0xfffffff0074d9c88',5056,5060),('0xfffffff0074d21d4',64,64),('0xfffffff0074d3220',68,72)]
    original=baseline.read_bytes();assert len(raw)==len(original)
    check=bytearray(raw)
    for a,b in RANGES:check[a:b]=original[a:b]
    assert check==original
    # Native ABI entries, the one relocated tile caller, and RAM return hook
    # are branches only, with aligned destinations in the three code regions.
    for a,b in RANGES[3:]:
        word=struct.unpack_from('<I',raw,a)[0]
        assert b-a==4 and word&0x7c000000==0x14000000
    target=out/'display-v63-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-gpu-map-v63-host/result.json',target/'map-host-check.json')
    shutil.copy2(root/'out/lmi-gpu-map-v63-native-host/result.json',target/'native-map-host-check.json')
    meta['display_v63']=meta.pop('display_v62');meta['sha256']=KERNEL_SHA
    meta['display_v63'].update(gpu_map_batch=True,map_boundary_real_drains=True,
        direct_surface_dma=False,wifi_integrated=False,performance_verified=False)
    meta['lmi_gpu_desktop'].update(source='tools/lmi-gpu-desktop-v63.c',
        source_sha256=audit['sources']['lmi-gpu-desktop-v63.c'])
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def map_batch(log):
    rows=re.findall(r'(?m)^LMI_GPU_MAP_BATCH\n([0-9a-f]{16})\n([0-9a-f]{16})\n([0-9a-f]{16})\n(?=LMI_GPU_ASYNC_DRAINED\n)',log)
    values=[int(v,16) for v in rows[0]] if len(rows)==log.count('LMI_GPU_MAP_BATCH')==1 else None
    markers=['LMI_SWAP_FENCE ','LMI_GPU_MAP_BATCH\n','LMI_GPU_ASYNC_DRAINED\n','LMI_RAM_ONLY_TIMER_EXPIRED\n']
    ordered=all(log.count(m)==1 for m in markers) and all(log.index(a)<log.index(b) for a,b in zip(markers,markers[1:]))
    valid=bool(values and ordered and values[1]>=values[0]>0 and values[2]==0 and
               prior.retirement(log)['counts_valid'] and prior.observe(log)['async_gpu']['exit_gpu_drain_verified'])
    return dict(counts_valid=valid,batches=values[0] if values else None,
        page_map_attempts=values[1] if values else None,uncommitted=values[2] if values else None,
        batching_exercised=bool(valid and values[1]>values[0]),
        mapping_safety_scope='First page and commit use real idle/fence; native gGPULock covers intervening pages',
        performance_verified=False)

def observe(log):
    result=prior.observe(log);result['gpu_map_batch']=map_batch(log)
    result['performance_verified']=False
    return result

def validate_run(observation):
    """Require the v63 experiment to run, independently of the legacy verifier.

    Keep this report separate: display admission and DMA retirement do not
    establish animation FPS, pixel equivalence or wireless connectivity.
    """
    required_true=[
        'normalized_experiment_qualified','desktop_pipeline_enabled','return_restored',
        'fast_path.counts_valid','fast_path.fast_path_exercised','fast_path.matches_desktop_frames',
        'producer_retirement.counts_valid','producer_retirement.source_release_verified',
        'producer_retirement.producer_wait_exercised','producer_retirement.matches_desktop_frames',
        'async_gpu.exit_gpu_drain_verified','gpu_map_batch.counts_valid','gpu_map_batch.batching_exercised',
    ]
    def field(path):
        value=observation
        for part in path.split('.'):
            if not isinstance(value,dict) or part not in value:return None
            value=value[part]
        return value
    failed=[path for path in required_true if field(path) is not True]
    if field('async_gpu.fault_held') is not False:failed.append('async_gpu.fault_held')
    return dict(passed=not failed,failed_checks=failed,performance_verified=False,
        scope='v63 map/display/source-release integration; legacy verifier still required')
