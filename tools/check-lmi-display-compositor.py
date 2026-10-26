"""Host checks of the full-frame adapter, separate from real scanout evidence."""
from pathlib import Path
import argparse,hashlib,json,subprocess
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--evidence-dir',default='out/lmi-display-compositor-host-v47')
args=parser.parse_args()
out=root/args.evidence_dir
out.mkdir(exist_ok=True)
names=['lmi-display-compositor.c','lmi-display-compositor.h','lmi-display-compositor-abi.h',
       'lmi-display-pipeline.c','lmi-display-pipeline.h','check-lmi-display-compositor.c',
       'check-lmi-display-compositor.py']
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
    *[str(root/'tools'/n) for n in ('check-lmi-display-compositor.c','lmi-display-compositor.c','lmi-display-pipeline.c')],
    '-o',str(out/'check')],check=True)
r=subprocess.run([str(out/'check')],text=True,capture_output=True)
(out/'host.log').write_text(r.stdout+r.stderr)
r.check_returncode()
report=dict(result='PASS',sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names},
    asan_ubsan=True,hardware_tested=False,desktop_integrated=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(r.stdout)
