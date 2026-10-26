"""Verify GPU pixel results from the frozen production GLES copy functions."""
import re

PASS='LMI_GL_COPY_PASS 8 cases, real shared IOSurface mirror, old-path negative control, state and readback guards'

def verify(log):
    lines=[s.strip() for s in log.replace('\r\n','\n').splitlines() if 'LMI_GL_COPY_' in s]
    assert len(lines)==10 and not any('LMI_GL_COPY_FAIL' in s for s in lines), 'Missing/failed/duplicate copy probe'
    renderer=re.fullmatch(r'LMI_GL_COPY_RENDERER (.+)',lines[0])
    assert renderer and re.search(r'\bFD650\b',renderer[1]), 'FD650 required'
    assert not re.search(r'software|softpipe|llvmpipe|swrast',renderer[1],re.I)
    for c,s in enumerate(lines[1:9]):
        m=re.fullmatch(r'LMI_GL_COPY_CASE (\d+) checked=(\d+) control_bad=(\d+) fixed_bad=(\d+) state_bad=(\d+) guard_bad=(\d+) error=([0-9a-fA-F]+)',s)
        assert m, 'Malformed copy case'
        values=[int(m[i],16 if i==7 else 10) for i in range(1,8)]
        old_bad=0 if c<2 else 733 if c<4 else 768
        assert values==[c,768,old_bad,0,0,0,0], 'Wrong copy pixels, control, state, guards or GL error'
    assert lines[9]==PASS, 'Incomplete copy probe'
    return dict(result='PASS',renderer=renderer[1],cases=8,pixels_per_case=768,
        old_path_negative_controls=6,real_shared_iosurface=True,state_restored=True,
        gpu_copy_correctness_verified=True,scanout_synchronization_verified=False)
