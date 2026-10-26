"""Require the real FD650 shader/readback probe; desktop proof is separate."""
import re

PASS = ('LMI_GL_PASS 8 hardware shader frames, 4032 exact RGBA pixels per frame, '
        'both CPU readback guards')


def verify(log):
    log = log.replace('\r\n', '\n')
    # puts() can write its newline separately. Recognize only the observed
    # complete launchd repeat notice appended to the complete PASS string;
    # retain both records and reject all other suffixes as before.
    joined=re.escape(PASS)+r'(com\.apple\.xpc\.launchd\|1970-01-01 \d{2}:\d{2}:\d{2}\.\d{6} <Notice>: Last log repeated 1 times)\n\n'
    log,joined_notices=re.subn('(?m)^'+joined,lambda m:PASS+'\n'+m[1]+'\n',log)
    assert joined_notices<=1, 'Duplicate joined GL completion'
    # COPY has its own strict verifier. A line containing any shader marker,
    # including a FAIL joined onto COPY output, must still be checked here.
    lines = [line.strip() for line in log.splitlines() if re.search(r'LMI_GL_(?!COPY_)', line)]
    assert not any('LMI_GL_FAIL' in line for line in lines), 'GL probe reported failure'
    assert len(lines) == 10, 'GL probe missing, truncated, duplicated, or unexpected records'
    renderer = re.fullmatch(r'LMI_GL_RENDERER (.+)', lines[0])
    assert renderer and re.search(r'\bFD650\b', renderer[1]), 'FD650 renderer required'
    assert not re.search(r'softpipe|llvmpipe|swrast|software', renderer[1], re.I), 'Software renderer refused'
    frames = []
    for frame, line in enumerate(lines[1:9]):
        match = re.fullmatch(r'LMI_GL_FRAME (\d+) checked=(\d+) bad=(\d+) error=([0-9a-fA-F]+)', line)
        assert match, 'Malformed GL frame record'
        values = [int(match[i], 16 if i == 4 else 10) for i in range(1, 5)]
        assert values == [frame, 4032, 0, 0], 'GL frame order, pixels, guards, or GL error failed'
        frames.append(dict(frame=frame, checked=4032, bad=0, error=0))
    assert lines[9] == PASS, 'GL probe did not finish'
    contexts = re.findall(r'redwood-gl: an OpenGL ES \d context for CoreAnimation, [^\n]*', log)
    ca_frames = [dict(frame=int(m[0]), calls=int(m[1]), draws=int(m[2]), triangles=int(m[3]),
                      clears=int(m[4]), copied=int(m[5]), in_place=int(m[6]))
                 for m in re.findall(r'redwood-gl: frame (\d+): (\d+) GL calls, (\d+) draws, '
                     r'(\d+) triangles, (\d+) clears; [^\n]*?; (\d+) pictures? copied out, '
                     r'(\d+) drawn in place;', log)]
    return dict(renderer=renderer[1], frames=frames, shader_frames_verified=8,
                joined_launchd_notices=joined_notices,
                hardware_shader_readback_verified=True, cpu_readback_guards_verified=True,
                coreanimation_fd650_context_observed=bool(contexts) and all('; FD650;' in c for c in contexts),
                coreanimation_frame_records=ca_frames,
                desktop_acceleration_verified=False)
