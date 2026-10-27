"""New GPU/CPU accounting, with unchanged display and DMA safety requirements.

The frozen v61 fast-copy equation intentionally does not describe v67.
This policy parses original records directly; it never rewrites logs or
pretends a GPU copy was a CPU copy. Legacy verification remains separate.
"""
import json,re,shutil
import lmi_display_v66_policy as ancestor
import lmi_display_v58_policy as display
checked=ancestor.checked
KERNEL_SHA='4b339b0a8ebf3bc1ca38ef68475bd22282a51cf98c3830e7420a34d9bf9d1cb5'
AUDIT_SHA='1f639ae649866a8f6ca0212928e6fe14cc058d2af8f14705a6273b02cbfbb55f'
HOST_SHA='84fe02cf7ac6a14c97712189679db83e613145a428cc2e1fc62d46b471d18893'
LINK_SHA='9ebc80169983bb67198bfeb1a0b42222c79e0916049983d220ad7817d34e8eba'
def stage(root,out):
    checked(root/'tools/lmi_display_v66_policy.py','e0c8b3134547bb411015928a3bcda68843677e1daa512423bd6fb92a6f4ee463')
    baseline,meta=ancestor.stage(root,out)
    folder=root/'out/lmi-gpu-frame-v67'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host_path=root/'out/lmi-gpu-frame-v67-host/result.json'
    host=json.loads(checked(host_path,HOST_SHA))
    link_path=root/'out/lmi-gpu-frame-v67-link-review/result.json'
    link=json.loads(checked(link_path,LINK_SHA))
    assert host['result']=='PASS' and host['scenarios']==21 and len(host['mutations_caught'])==11
    for flag in ['asan_ubsan','actual_v64_backend','original_compositor_pipeline','separate_cpu_dma_views','independent_packet_decode','static_analysis']:assert host[flag]
    assert link['result']=='PASS' and link['kernel_sha256']==KERNEL_SHA
    for flag in ['object_reproduced','link_reproduced','placed_sections_verified','hooks_verified','outside_edits_exact',
        'full_rx_space_audit','obsolete_entries_disabled','loaded_entry_pointers_preserved','no_writable_globals',
        'correct_native_gpu_lock','frozen_backend_and_dpu_preserved']:assert link[flag]
    for report in (audit,host):
        for n,d in report['sources'].items():checked(root/'tools'/n,d)
    for n,d in host['generated_sources'].items():checked(host_path.parent/n,d)
    for report in (audit,link):
        for n,d in report['inputs'].items():checked(root/n,d)
    assert audit['base_sha256']==meta['sha256'] and audit['sha256']==KERNEL_SHA and len(audit['hooks'])==5
    for flag in ['outside_edits_exact','journal_prefix_preserved','desktop_gpu_copy','partial_cpu_compositor_preserved',
        'source_retirement_unchanged','touch_unchanged','dpu_pipeline_unchanged','allocations_retained_until_ram_return']:assert audit[flag]
    old=baseline.read_bytes();restored=bytearray(raw);assert len(old)==len(raw)
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=old[a:z]
    assert restored==old and not audit['hardware_tested'] and not audit['performance_verified']
    target=out/'display-v67-candidate';assert not target.exists();shutil.copytree(folder,target)
    for path,name in [(host_path,'frame-host-check.json'),(link_path,'frame-link-review.json')]:shutil.copy2(path,target/name)
    meta['display_v67']=meta.pop('display_v66');meta['sha256']=KERNEL_SHA
    meta['display_v67'].update(desktop_gpu_copy=True,cpu_full_frame_copy_fallback=True,partial_cpu_compositor=True,
        all_cpu_copies_removed=False,
        bounded_source_mappings=8,direct_surface_scanout=False,wifi_integrated=False,performance_verified=False)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta
def record(log,tag,count,hex_lines=False):
    token=r'([0-9a-f]{16})\n' if hex_lines else r'(\d+)'
    pattern=r'(?m)^'+re.escape(tag)+(r'\n'+token*count if hex_lines else ' '+r' '.join([token]*count)+r'$')
    rows=re.findall(pattern,log)
    lines=[l for l in log.splitlines() if tag in l and (l==tag or l.startswith(tag+' '))]
    if len(rows)!=len(lines) or len(rows)!=1:return None
    row=(rows[0],) if count==1 else rows[0]
    values=[int(n,16 if hex_lines else 10) for n in row]
    return values if all(0<=v<1<<64 for v in values) else None
def observe(log):
    result=display.observe(log);result['copy_probe']=ancestor.copy_probe(log)
    v=record(log,'LMI_GPU_FRAME',7);life=record(log,'LMI_GPU_FRAME_LIFETIME',7)
    fast=record(log,'LMI_DPU_FAST',3);stride=record(log,'LMI_FRAME_STRIDE',1)
    pre=record(log,'LMI_DPU_PRECLEAN',6);ret=record(log,'LMI_SWAP_FENCE',10)
    q=record(log,'LMI_GPU_QUEUE',8,True);mapping=record(log,'LMI_GPU_MAP_BATCH',3,True)
    markers=['LMI_DPU_PROBE_RETURN restored=1\n','LMI_DPU_FAST ','LMI_FRAME_STRIDE ',
        'LMI_SWAP_FENCE ','LMI_DPU_PRECLEAN ','LMI_GPU_FRAME ','LMI_GPU_FRAME_LIFETIME ',
        'LMI_GPU_QUEUE\n','LMI_GPU_MAP_BATCH\n','LMI_GPU_ASYNC_DRAINED\n','LMI_RAM_ONLY_TIMER_EXPIRED\n']
    ordered=all(log.count(m)==1 for m in markers) and all(log.index(a)<log.index(b) for a,b in zip(markers,markers[1:]))
    stats=result.get('desktop_stats',[]);total=stats[0]['frames'] if len(stats)==1 else None
    names=['draws','frames','bytes','linear','strided','map_hits','map_new',
           'evicted','retained','released','fallback','skipped_clean','copy_ticks','held']
    c=dict(zip(names,(v or [])+(life or [])))
    gpu_ok=bool(v and life and ordered and v[0]==v[1]>0 and v[2]==v[1]*4544*2436 and v[3]+v[4]==v[1] and
        life[6]==0 and life[4]==v[1] and life[5]>0 and life[1]>=life[2]>=life[0] and 0<life[1]-life[2]<=8 and
        1<=v[6]-life[1]-1<=2 and v[5]<=v[0])
    fast_ok=bool(gpu_ok and fast and stride and fast[0]==fast[1]+v[1] and fast[0]+fast[2]==total and
        stride[0]<=fast[1] and life[3]>=fast[1] and fast[0]+fast[2]>0)
    result['gpu_frame']=dict(counts_valid=gpu_ok,counts=c,exercised=bool(gpu_ok),
        cpu_gpu_accounting_valid=fast_ok,persistent_mappings_exercised=bool(gpu_ok and v[5]>0),performance_verified=False)
    result['fast_path']=dict(counts_valid=fast_ok,fast_frames=fast[0] if fast else None,
        cpu_copy_calls=fast[1] if fast else None,ordinary_frames=fast[2] if fast else None,
        cpu_strided_frames=stride[0] if stride else None,matches_desktop_frames=fast_ok,
        scope='Fast qualified frames = actual CPU copies + completed GPU frames; ordinary frames use native compositor')
    ret_ok=bool(ret and ordered and fast_ok and ret[0]==ret[1]>=total>0 and ret[8]==0 and ret[9]>=ret[1] and
        sum(ret[n] for n in [4,5,6,7])<=ret[2])
    result['producer_retirement']=dict(counts_valid=ret_ok,source_release_verified=ret_ok,
        producer_wait_exercised=bool(ret_ok and ret[2]>0),matches_desktop_frames=ret_ok,counts=ret)
    map_ok=bool(mapping and ordered and mapping[1]>mapping[0]>0 and not mapping[2] and ret_ok and
                result['async_gpu']['exit_gpu_drain_verified'])
    result['gpu_map_batch']=dict(counts_valid=map_ok,batching_exercised=map_ok,counts=mapping)
    queue_ok=bool(q and ordered and q[0]==4 and 1<=q[1]<=4 and q[1]<=q[5]<1<<32 and q[5]==q[6] and
        q[4]>=q[5] and q[3]<=q[5] and q[1]-1<=q[2]<q[5] and q[7]==2 and
        (q[1]>1)==(q[2]>0) and map_ok and re.search(r'(?m)^LMI_GPU_QUEUE\n'+r'[0-9a-f]{16}\n'*8+r'(?=LMI_GPU_MAP_BATCH\n)',log) and
        re.search(r'(?m)^LMI_GPU_MAP_BATCH\n'+r'[0-9a-f]{16}\n'*3+r'(?=LMI_GPU_ASYNC_DRAINED\n)',log))
    result['gpu_queue']=dict(counts_valid=queue_ok,counts=q,overlap_exercised=bool(queue_ok and q[1]>1),
                             real_completion_drained=queue_ok)
    pre_ok=bool(pre and ordered and fast_ok and pre[0]==total and 0<pre[2]<=pre[0] and
        pre[1]<=pre[0] and pre[3]==pre[4]==0 and pre[5]>0)
    result['preclean']=dict(counts_valid=pre_ok,matches_desktop_frames=pre_ok,
        preclean_exercised=bool(pre_ok and pre[1]>0),counts=pre)
    result['qualification_metadata']=__import__('lmi_display_v61_policy').qualification_metadata(log)
    result['record_order_valid']=ordered;result['performance_verified']=False
    return result
def validate_run(o):
    paths=['normalized_experiment_qualified','desktop_pipeline_enabled','return_restored','record_order_valid',
        'async_gpu.exit_gpu_drain_verified','gpu_frame.counts_valid','gpu_frame.exercised',
        'gpu_frame.cpu_gpu_accounting_valid','gpu_frame.persistent_mappings_exercised',
        'fast_path.counts_valid','fast_path.matches_desktop_frames','qualification_metadata.valid',
        'producer_retirement.counts_valid','producer_retirement.source_release_verified',
        'producer_retirement.producer_wait_exercised','producer_retirement.matches_desktop_frames',
        'gpu_map_batch.counts_valid','gpu_map_batch.batching_exercised','gpu_queue.counts_valid',
        'gpu_queue.overlap_exercised','gpu_queue.real_completion_drained',
        'preclean.counts_valid','preclean.matches_desktop_frames','preclean.preclean_exercised',
        'copy_probe.counts_valid','copy_probe.fresh_completion_verified','copy_probe.before_service_result']
    def field(path):
        value=o
        for part in path.split('.'):
            if not isinstance(value,dict) or part not in value:return None
            value=value[part]
        return value
    failed=[path for path in paths if field(path) is not True]
    if field('async_gpu.fault_held') is not False:failed.append('async_gpu.fault_held')
    return dict(passed=not failed,failed_checks=failed,performance_verified=False,
        scope='v67 GPU/CPU frame accounting, unchanged scaler/retirement/queue/map safety; separate legacy verifier retained')
