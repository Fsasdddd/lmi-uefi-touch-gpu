"""Create strict, separately pinned v69 runtime admission and tester."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1];t=root/'tools';candidate=root/'out/lmi-gpu-cache-v69'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,s):
    p=t/n;assert not p.exists(),p;p.write_text(s)
p=(t/'lmi_display_v68_policy.py').read_text().replace('v68','v69')
p=p.replace('lmi-gpu-frame-v69b','lmi-gpu-cache-v69').replace('lmi-gpu-frame-v69-host','lmi-gpu-cache-v69-host')
p=p.replace('lmi-gpu-frame-v69b-link-review','lmi-gpu-cache-v69-link-review')
# The first replacement may have already removed the b in link-review.
p=p.replace('lmi-gpu-cache-v69-link-review','lmi-gpu-cache-v69-link-review')
for key,path in [('KERNEL_SHA',candidate/'mach.development.bcm2837'),('AUDIT_SHA',candidate/'build-audit.json'),
                 ('HOST_SHA',root/'out/lmi-gpu-cache-v69-host/result.json'),('LINK_SHA',root/'out/lmi-gpu-cache-v69-link-review/result.json')]:
    import re
    p=re.sub(r"(?m)^"+key+r"='[a-f0-9]+'$",key+"='"+sha(path)+"'",p)
p=p.replace("host['scenarios']==24 and len(host['mutations_caught'])==10", "host['scenarios']==28 and len(host['mutations_caught'])==14 and host['dirty_cacheline_eviction'] and host['cache_ownership_transitions']")
p=p.replace("'LMI_GPU_BLIT_LIFETIME ',", "'LMI_GPU_BLIT_LIFETIME ','LMI_GPU_TARGET_CACHE ',")
p=p.replace("    result['record_order_valid']=ordered;",'''    cache=record(log,'LMI_GPU_TARGET_CACHE',5)
    cache_ok=bool(cache and gpu_ok and 0<cache[0]<=v[0] and cache[1]>0 and cache[0]+cache[1]==v[0] and
        cache[2]<=cache[0] and cache[3]==cache[1]*2*((4544*2436+16383)&~16383) and cache[4]>0)
    result['target_cache']=dict(counts_valid=cache_ok,reuse_exercised=bool(cache_ok and cache[1]>0),
        counts=cache,post_invalidate_preserved=True,performance_verified=False)
    result['record_order_valid']=ordered;''')
p=p.replace("'copy_probe.counts_valid','copy_probe.fresh_completion_verified'", "'target_cache.counts_valid','target_cache.reuse_exercised','copy_probe.counts_valid','copy_probe.fresh_completion_verified'")
p=p.replace("bounded_source_mappings=8,direct_surface_scanout=False", "bounded_source_mappings=8,target_cache_reuse=True,post_invalidate_preserved=True,direct_surface_scanout=False")
p=p.replace("'source_retirement_unchanged','touch_unchanged'", "'target_cache_reuse','post_invalidate_preserved','source_retirement_unchanged','touch_unchanged'")
write('lmi_display_v69_policy.py',p)
p=(t/'check-lmi-display-v68-policy.py').read_text().replace('v68','v69')
p=p.replace("good=policy.observe(fixture);", "cache='LMI_GPU_TARGET_CACHE 10 1990 9 '+str(1990*2*((4544*2436+16383)&~16383))+' 100000\\n'\nfixture=fixture.replace(last,last+cache)\ngood=policy.observe(fixture);")
p=p.replace("'LMI_GPU_BLIT_LIFETIME']", "'LMI_GPU_BLIT_LIFETIME','LMI_GPU_TARGET_CACHE']")
p=p.replace("reject('GPU-pretended-to-be-CPU'",'''for index,value in [(0,0),(0,11),(1,1989),(2,11),(3,1),(4,0)]:
    row=cache.strip().split();row[index+1]=str(value)
    reject('target-cache-'+str(index)+'-'+str(value),fixture.replace(cache,' '.join(row)+'\\n'))
old=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v68-desktop-180/checkpoint-63.log').read_text(encoding='utf-8')
assert not policy.validate_run(policy.observe(old))['passed'],'v68 lacks target-cache evidence'
cases+=1
reject('GPU-pretended-to-be-CPU' ''')
write('check-lmi-display-v69-policy.py',p)
p=(t/'test-lmi-checkpoints-v68.py').read_text().replace('display_v68','display_v69').replace('display-v68','display-v69').replace('v68 profile','v69 profile').replace("'v68'","'v69'")
p=p.replace('[*range(40,67),68]', '[*range(40,67),69]')
p=p.replace('lmi-gpu-frame-v68','lmi-gpu-cache-v69').replace('check-lmi-display-v68-policy','check-lmi-display-v69-policy')
p=p.replace("'test-lmi-checkpoints-v68.py'", "'test-lmi-checkpoints-v69.py'")
write('test-lmi-checkpoints-v69.py',p)
