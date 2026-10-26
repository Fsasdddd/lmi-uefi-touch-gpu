"""Reject incomplete and contradictory userland hardware rendering evidence."""
from pathlib import Path
import runpy

module = runpy.run_path(str(Path(__file__).with_name('verify-lmi-gpu-gl.py')))
verify = module['verify']
lines = ['LMI_GL_RENDERER FD650'] + [
    f'LMI_GL_FRAME {n} checked=4032 bad=0 error=0' for n in range(8)] + [module['PASS']]
valid = '\n'.join(lines) + '\n'
assert verify(valid)['hardware_shader_readback_verified']
assert verify(valid.replace('\n', '\r\n'))['shader_frames_verified'] == 8
notice='com.apple.xpc.launchd|1970-01-01 08:03:10.087453 <Notice>: Last log repeated 1 times'
joined=valid[:-1]+notice+'\n\n'
assert verify(joined)['joined_launchd_notices']==1
copy_module=runpy.run_path(str(Path(__file__).with_name('verify-lmi-gl-copy.py')))
copy_lines=['LMI_GL_COPY_RENDERER FD650']+[
    f'LMI_GL_COPY_CASE {n} checked=768 control_bad={0 if n<2 else 733 if n<4 else 768} fixed_bad=0 state_bad=0 guard_bad=0 error=0'
    for n in range(8)]+[copy_module['PASS']]
combined=valid+'\n'.join(copy_lines)+'\n'
assert verify(combined)['shader_frames_verified']==8
assert copy_module['verify'](combined)['gpu_copy_correctness_verified']
interleaved='\n'.join(item for pair in zip(lines,copy_lines) for item in pair)+'\n'
assert verify(interleaved)['shader_frames_verified']==8
assert copy_module['verify'](interleaved)['gpu_copy_correctness_verified']
cases = [valid.replace('FD650', name) for name in ['softpipe', 'llvmpipe', 'FD650 software', 'FD6500']]
cases += ['\n'.join(lines[:n] + lines[n+1:]) for n in range(10)]
cases += [valid + line + '\n' for line in [*lines, 'LMI_GL_FAIL pixels', 'LMI_GL_UNKNOWN']]
cases += [valid.replace('FRAME 3 checked=4032 bad=0 error=0', replacement) for replacement in [
    'FRAME 2 checked=4032 bad=0 error=0', 'FRAME 3 checked=4096 bad=0 error=0',
    'FRAME 3 checked=4032 bad=1 error=0', 'FRAME 3 checked=4032 bad=0 error=502',
    'FRAME 3 checked=4032 bad=0 error=garbage']]
cases += ['\n'.join([lines[0], lines[2], lines[1], *lines[3:]]), valid + valid, '']
cases += [valid[:-1]+suffix+'\n\n' for suffix in [
    'LMI_GL_FAIL pixels',notice+'LMI_GL_FAIL pixels',notice[:-1],
    notice.replace('1 times','2 times'),notice.replace('<Notice>','<Error>'),
    notice.replace('repeated','failed'),notice.replace('08:03:10.087453','bad time'),
    'unexpected suffix',notice+notice]]
cases += [joined.replace('both CPU readback guards','both CPU readback guard'),
          joined.replace('FRAME 7 checked=4032 bad=0','FRAME 7 checked=4032 bad=1'),
          joined.replace(notice+'\n\n',notice+'\n'),joined+joined]
cases += [combined+'LMI_GL_COPY_UNKNOWN LMI_GL_FAIL pixels\n',
          combined.replace('LMI_GL_FRAME 3','LMI_GL_COPY_FRAME 3'),
          combined.replace(module['PASS'],module['PASS']+'LMI_GL_COPY_PASS garbage'),
          interleaved+'LMI_GL_RENDERER FD650\n']
for n, candidate in enumerate(cases):
    try:
        verify(candidate)
    except AssertionError:
        continue
    raise AssertionError(f'Accepted negative case {n}')
print(f'PASS: GL verifier, 5 positive controls, {len(cases)} negative cases')
