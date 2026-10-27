from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-fast-v61-host';out.mkdir(exist_ok=True)
names=['lmi-display-fast-v61.c','lmi-display-fast-v61.h','lmi-display-surface-abi.h','lmi-display-direct-plan-v61.c',
       'lmi-display-direct-plan-v61.h','lmi-display-compositor-v56.c','lmi-display-compositor.h','lmi-display-compositor-abi.h',
       'lmi-display-pipeline-v51.c','lmi-display-pipeline.h','check-lmi-display-fast-v61.c','check-lmi-display-fast-v61.py']
original=(root/'tools/lmi-display-compositor-v56.c').read_text()
assert original.count('FN int original_fields')==1
adapted=original.replace('FN int original_fields','int original_fields').replace('original_fields','lmi_fast_original_fields').replace('lmi_compositor_frame','lmi_fast_original_frame')
(out/'original-compositor.c').write_text(adapted)
command=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(root/'tools'),
         str(out/'original-compositor.c'),*[str(root/'tools'/n) for n in ['lmi-display-fast-v61.c','lmi-display-direct-plan-v61.c',
         'lmi-display-pipeline-v51.c','check-lmi-display-fast-v61.c']],'-o',str(out/'check')]
subprocess.run(command,check=True)
p=subprocess.run([str(out/'check')],capture_output=True,text=True);(out/'host.log').write_text(p.stdout+p.stderr)
print(p.stdout+p.stderr);p.check_returncode()
(out/'result.json').write_text(json.dumps(dict(result='PASS',scenarios=21,asan_ubsan=True,hardware_tested=False,
    original_compositor_used=True,sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names}),indent=2)+'\n')
