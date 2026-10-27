"""Pin v71 and distinguish GPU ownership from outstanding DMA."""
from pathlib import Path
import hashlib,re
r=Path(__file__).resolve().parents[1];t=r/'tools'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,s):
    p=t/n;assert not p.exists(),p;p.write_text(s)
s=(t/'lmi_display_v70_policy.py').read_text().split('record=prior.record',1)[0]
s=s.replace('v70','v71').replace('gpu-overlap','gpu-deferred-cache')
s=s.replace('import lmi_display_v69_policy as prior','import lmi_display_v70_policy as prior')
pins={'KERNEL_SHA':r/'out/lmi-gpu-deferred-cache-v71/mach.development.bcm2837',
      'AUDIT_SHA':r/'out/lmi-gpu-deferred-cache-v71/build-audit.json',
      'HOST_SHA':r/'out/lmi-gpu-deferred-cache-v71-host/result.json',
      'LINK_SHA':r/'out/lmi-gpu-deferred-cache-v71-link-review/result.json'}
for key,p in pins.items():s=re.sub(key+r"='[0-9a-f]+'",key+'='+repr(sha(p)),s)
s=s.replace("host['scenarios']==29 and len(host['mutations_caught'])==17", "host['scenarios']==32 and len(host['mutations_caught'])==20")
s=s.replace("'native_tail_submission']:assert host[flag]", "'native_tail_submission','deferred_cpu_ownership','actual_cpu_preservation_observed']:assert host[flag]")
s=s.replace("'unlocked_delay_binding','no_direct_queue_drain'", "'unlocked_delay_binding','actual_full_frame_helper_binding','no_direct_queue_drain'")
s=s.replace("'post_invalidate_preserved',", "'deferred_target_cpu_invalidate','state_post_invalidate_preserved','cpu_preservation_requires_ownership_transfer',")
s=s.replace("    checked(root/'tools/lmi_display_v69_policy.py'", f"    assert audit['post_invalidate_preserved'] is False\n    checked(root/'tools/lmi_display_v70_policy.py',{sha(t/'lmi_display_v70_policy.py')!r})\n    checked(root/'tools/lmi_display_v69_policy.py'")
stop=r/'out/lmi-gpu-deferred-cache-v71-stop/result.json'
s=re.sub(r"checked\(stop_path,'[0-9a-f]+'\)",f"checked(stop_path,{sha(stop)!r})",s)
s=s.replace('post_invalidate_preserved=True', 'post_invalidate_preserved=False,deferred_target_cpu_invalidate=True,cpu_transition_invalidate_required=True')
s+='''record=prior.record

def observe(log):
    result=prior.observe(log)
    values=record(log,'LMI_GPU_CPU_TRANSFER',4)
    owned=record(log,'LMI_GPU_CPU_OWNED',1)
    tags=['LMI_GPU_COPY_PENDING ','LMI_GPU_CPU_TRANSFER ','LMI_GPU_CPU_OWNED ','LMI_GPU_QUEUE\\n']
    ordered=all(log.count(tag)==1 for tag in tags) and all(log.index(a)<log.index(b) for a,b in zip(tags,tags[1:]))
    draws=result.get('gpu_frame',{}).get('counts',{}).get('draws')
    valid=bool(values and owned and 0<=owned[0]<=3 and ordered and result['gpu_copy_overlap']['counts_valid'] and
        values[0]==draws and 0<=values[1]<values[0] and values[2]==values[1]*((4544*2436+16383)&~16383) and
        (values[1]>0)==(values[3]>0))
    result['deferred_cpu_cache']=dict(counts_valid=valid,record_order_valid=ordered,
        counts=dict(zip(['post_deferred','cpu_sync_targets','cpu_sync_bytes','cpu_sync_ticks'],values or [])),
        gpu_owned_mask=owned[0] if owned else None,
        skipped_full_target_traversals=values[0]-values[1] if valid else None,
        pending_copy_zero=result['gpu_copy_overlap']['pending_zero'],performance_verified=False,
        scope='A GPU-owned target may retain stale clean CPU cache until an explicit CPU access transition; this is separate from pending DMA.')
    result['target_cache']['post_invalidate_preserved']=False
    result['target_cache']['cpu_transition_invalidate_required']=True
    return result

def validate_run(observation):
    result=prior.validate_run(observation)
    for name in ['counts_valid','record_order_valid','pending_copy_zero']:
        if observation.get('deferred_cpu_cache',{}).get(name) is not True:result['failed_checks'].append('deferred_cpu_cache.'+name)
    result['passed']=not result['failed_checks']
    result['scope']='v71 deferred CPU cache transfers, actual copy-fence completion and unchanged strict display/source/queue safety; legacy verification separate'
    return result
'''
write('lmi_display_v71_policy.py',s)
s=(t/'test-lmi-checkpoints-v70.py').read_text().replace('v70','v71').replace('gpu-overlap','gpu-deferred-cache')
s=s.replace('[*range(40,67),70]', '[*range(40,67),71]')
s=s.replace('check-lmi-gpu-deferred-cache-stop-v71.py','check-lmi-gpu-deferred-stop-v71.py')
s=s.replace("'lmi_display_v69_policy.py')", "'lmi_display_v69_policy.py','lmi_display_v70_policy.py')")
write('test-lmi-checkpoints-v71.py',s)
s=(t/'check-lmi-display-v70-policy.py').read_text().replace('v70','v71')
at=s.index('good=policy.observe(fixture)')
s=s[:at]+'''transfer='LMI_GPU_CPU_TRANSFER 2000 7 '+str(7*((4544*2436+16383)&~16383))+' 100000\\n'
owned='LMI_GPU_CPU_OWNED 3\\n'
fixture=fixture.replace(pending,pending+transfer+owned)
'''+s[at:]
s=s.replace("'LMI_GPU_COPY_PENDING']", "'LMI_GPU_COPY_PENDING','LMI_GPU_CPU_TRANSFER','LMI_GPU_CPU_OWNED']")
at=s.index("(out/'synthetic-fixture.log')")
s=s[:at]+'''for index,value in [(0,1999),(1,2000),(2,1),(3,0)]:
    row=transfer.strip().split();row[index+1]=str(value)
    reject('cpu-transfer-'+str(index),fixture.replace(transfer,' '.join(row)+'\\n'))
reject('owned-mask-invalid',fixture.replace(owned,'LMI_GPU_CPU_OWNED 4\\n'))
reject('cpu-transfer-order',fixture.replace(transfer+owned,owned+transfer))
reject('cpu-transfer-overflow',fixture.replace(transfer,transfer.replace(' 2000 ',' '+str(1<<64)+' ')))
for mask in range(4):
    trial=fixture.replace(owned,'LMI_GPU_CPU_OWNED '+str(mask)+'\\n')
    assert policy.validate_run(policy.observe(trial))['passed'];cases+=1
trial=fixture.replace(transfer,'LMI_GPU_CPU_TRANSFER 2000 0 0 0\\n')
assert policy.validate_run(policy.observe(trial))['passed'];cases+=1
old=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v70-desktop-180/checkpoint-63.log').read_text(encoding='utf-8')
reject('v70-has-no-deferred-ownership-evidence',old)
for field in ['counts_valid','record_order_valid','pending_copy_zero']:
    trial=copy.deepcopy(good);trial['deferred_cpu_cache'][field]=False
    assert not policy.validate_run(trial)['passed'];cases+=1
'''+s[at:]
write('check-lmi-display-v71-policy.py',s)
