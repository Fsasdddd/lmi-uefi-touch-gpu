from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-direct-plan-host';out.mkdir(exist_ok=True)
names=['lmi-display-direct-plan.c','lmi-display-direct-plan.h','check-lmi-display-direct-plan.c']
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
    *[str(root/'tools'/n) for n in names if n.endswith('.c')],'-o',str(out/'check')],check=True)
p=subprocess.run([str(out/'check')],capture_output=True,text=True)
(out/'host.log').write_text(p.stdout+p.stderr);p.check_returncode();print(p.stdout)
(out/'result.json').write_text(json.dumps(dict(result='PASS',asan_ubsan=True,hardware_tested=False,desktop_integrated=False,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names}),indent=2)+'\n')
