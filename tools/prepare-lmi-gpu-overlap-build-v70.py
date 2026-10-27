"""Create the independent v70 builder/reviewer without editing frozen v69."""
from pathlib import Path
r=Path(__file__).resolve().parents[1];t=r/'tools'
def write(name,text):
    p=t/name;assert not p.exists(),p;p.write_text(text)
s=(t/'build-lmi-gpu-cache-v69.py').read_text()
s=s.replace('gpu-cache-v69','gpu-overlap-v70').replace("default='v69'","default='v70'")
s=s.replace("r'v69[a-z]?'","r'v70[a-z]?'").replace("out/lmi-gpu-cache-","out/lmi-gpu-overlap-")
s=s.replace("host['scenarios']>=28 and len(host['mutations_caught'])==14", "host['scenarios']==29 and len(host['mutations_caught'])==17")
s=s.replace("'cache_ownership_transitions']:assert host[flag]", "'cache_ownership_transitions','delayed_gpu_execution','copy_fence_join','native_tail_submission']:assert host[flag]")
at=s.index("flags=['--target=")
s=s[:at]+'''stop_path=root/'out/lmi-gpu-overlap-v70-stop/result.json'
stop=json.loads(stop_path.read_text());assert stop['result']=='PASS'
for flag in ['actual_backend','asan_ubsan','outstanding_copy_stopped','backing_retained','no_service_lock_after_stop']:assert stop[flag]
for n,d in stop['inputs'].items():assert sha(root/n)==d,n
'''+s[at:]
s=s.replace("lmi_frame_drain=gpu['drain']", "lmi_frame_done=gpu['lmi_desktop_done'],lmi_frame_pause=gpu['delay']")
s=s.replace("inputs=[base,space_path,host_path,", "inputs=[Path(__file__),root/'tools/prepare-lmi-gpu-overlap-build-v70.py',base,space_path,host_path,stop_path,")
s=s.replace("allocations_retained_until_ram_return=True,target_cache_reuse=True", "allocations_retained_until_ram_return=True,async_copy_join=True,per_copy_fence=True,unlocked_copy_wait=True,stop_pending_backing_preserved=True,target_cache_reuse=True")
write('build-lmi-gpu-overlap-v70.py',s)
s=(t/'audit-lmi-gpu-cache-v69-linked.py').read_text()
s=s.replace('gpu-cache-v69','gpu-overlap-v70').replace("default='v69'","default='v70'")
s=s.replace('out/lmi-gpu-cache-','out/lmi-gpu-overlap-')
s=s.replace("assert int(audit['bindings']['lmi_frame_gpu_lock'],16)==0xfffffff007f269e8", """assert int(audit['bindings']['lmi_frame_gpu_lock'],16)==0xfffffff007f269e8
gpu=json.loads((root/'out/lmi-gpu-queue-v64b/runtime-symbols.json').read_text())
assert int(audit['bindings']['lmi_frame_done'],16)==gpu['lmi_desktop_done']
assert int(audit['bindings']['lmi_frame_pause'],16)==gpu['delay']
assert 'lmi_frame_drain' not in audit['bindings']
calls=[target(struct.unpack_from('<I',raw,off(pc))[0],pc)
       for row in audit['sections'] for pc in range(int(row['start'],16),int(row['start'],16)+row['bytes']-3,4)
       if struct.unpack_from('<I',raw,off(pc))[0]&0xfc000000==0x94000000]
assert gpu['lmi_desktop_done'] in calls and gpu['delay'] in calls
assert gpu['drain'] not in calls""")
s=s.replace('correct_native_gpu_lock=True,frozen_backend_and_dpu_preserved=True', 'correct_native_gpu_lock=True,real_copy_fence_binding=True,unlocked_delay_binding=True,no_direct_queue_drain=True,frozen_backend_and_dpu_preserved=True')
s=s.replace('actual v69 object/link','actual v70 object/link')
write('audit-lmi-gpu-overlap-v70-linked.py',s)
