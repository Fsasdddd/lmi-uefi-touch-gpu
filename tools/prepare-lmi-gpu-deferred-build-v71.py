"""Separate build/link audit for deferred CPU target cache ownership."""
from pathlib import Path
r=Path(__file__).resolve().parents[1];t=r/'tools'
def write(n,s):
    p=t/n;assert not p.exists(),p;p.write_text(s)
s=(t/'build-lmi-gpu-overlap-v70.py').read_text()
s=s.replace('gpu-overlap-v70','gpu-deferred-cache-v71').replace("default='v70'","default='v71'")
s=s.replace("r'v70[a-z]?'","r'v71[a-z]?'").replace('out/lmi-gpu-overlap-','out/lmi-gpu-deferred-cache-')
s=s.replace('prepare-lmi-gpu-overlap-build-v70.py','prepare-lmi-gpu-deferred-build-v71.py')
s=s.replace("host['scenarios']==29 and len(host['mutations_caught'])==17", "host['scenarios']==32 and len(host['mutations_caught'])==20")
s=s.replace("'native_tail_submission']:assert host[flag]", "'native_tail_submission','deferred_cpu_ownership','actual_cpu_preservation_observed']:assert host[flag]")
s=s.replace("bindings.update(lmi_frame_backend=", "bindings.update(lmi_frame_full_pixels=display['pixels'],lmi_fast_original_fields=display['lmi_fast_original_fields'])\nbindings.update(lmi_frame_backend=")
s=s.replace('post_invalidate_preserved=True', 'post_invalidate_preserved=False,deferred_target_cpu_invalidate=True,state_post_invalidate_preserved=True,cpu_preservation_requires_ownership_transfer=True')
write('build-lmi-gpu-deferred-cache-v71.py',s)
s=(t/'audit-lmi-gpu-overlap-v70-linked.py').read_text()
s=s.replace('gpu-overlap-v70','gpu-deferred-cache-v71').replace("default='v70'","default='v71'")
s=s.replace('out/lmi-gpu-overlap-','out/lmi-gpu-deferred-cache-')
s=s.replace("assert 'lmi_frame_drain' not in audit['bindings']", """assert 'lmi_frame_drain' not in audit['bindings']
display=json.loads((root/'out/lmi-display-fast-v62d/runtime-symbols.json').read_text())
assert int(audit['bindings']['lmi_frame_full_pixels'],16)==display['pixels']==0xfffffff0074d36b4
assert int(audit['bindings']['lmi_fast_original_fields'],16)==display['lmi_fast_original_fields']==0xfffffff007ae38ac""")
s=s.replace("assert gpu['drain'] not in calls", "assert gpu['drain'] not in calls\nassert display['pixels'] in calls and display['lmi_fast_original_fields'] in calls")
s=s.replace('unlocked_delay_binding=True,', 'unlocked_delay_binding=True,actual_full_frame_helper_binding=True,')
s=s.replace('actual v70 object/link','actual v71 object/link')
write('audit-lmi-gpu-deferred-cache-v71-linked.py',s)
