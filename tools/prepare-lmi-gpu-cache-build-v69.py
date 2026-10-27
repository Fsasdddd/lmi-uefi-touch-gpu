"""Create standalone v69 builder and final-image auditor."""
from pathlib import Path
root=Path(__file__).resolve().parents[1];t=root/'tools'
def write(n,s):
    p=t/n;assert not p.exists(),p;p.write_text(s)
s=(t/'build-lmi-gpu-frame-v68.py').read_text().replace('lmi-gpu-frame-v68','lmi-gpu-cache-v69')
s=s.replace("default='v68'","default='v69'").replace("r'v68[a-z]?'","r'v69[a-z]?'")
s=s.replace("out/lmi-gpu-frame-'+args.attempt","out/lmi-gpu-cache-'+args.attempt")
s=s.replace("host['scenarios']>=23 and len(host['mutations_caught'])==10", "host['scenarios']>=28 and len(host['mutations_caught'])==14")
s=s.replace("'state_readback_verified','static_analysis'", "'state_readback_verified','static_analysis','dirty_cacheline_eviction','cache_ownership_transitions'")
s=s.replace("allocations_retained_until_ram_return=True,direct_surface_scanout=False", "allocations_retained_until_ram_return=True,target_cache_reuse=True,post_invalidate_preserved=True,direct_surface_scanout=False")
s=s.replace("root/'tools/lmi-gpu-hfi-io.c']", "root/'tools/lmi-gpu-hfi-io.c',root/'tools/lmi-display-compositor-v56.c',root/'out/lmi-display-probe-v56f/lmi-display-compositor-v56.c',root/'tools/lmi-display-fast-v62.c',root/'hackios/xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp']")
write('build-lmi-gpu-cache-v69.py',s)
s=(t/'audit-lmi-gpu-frame-v68-linked.py').read_text().replace('lmi-gpu-frame-v68','lmi-gpu-cache-v69')
s=s.replace("default='v68'","default='v69'").replace("out/lmi-gpu-frame-'+args.attempt", "out/lmi-gpu-cache-'+args.attempt")
s=s.replace('actual v68 object/link', 'actual v69 object/link')
write('audit-lmi-gpu-cache-v69-linked.py',s)
