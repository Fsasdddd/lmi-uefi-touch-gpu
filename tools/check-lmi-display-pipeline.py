"""Compile and run production buffer lifecycle checks with ASan and UBSan."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-pipeline-host'
out.mkdir(exist_ok=True)
names=['lmi-display-pipeline.c','lmi-display-pipeline.h','check-lmi-display-pipeline.c']
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
    str(root/'tools/lmi-display-pipeline.c'),str(root/'tools/check-lmi-display-pipeline.c'),
    '-o',str(out/'check')],check=True)
result=subprocess.run([str(out/'check')],text=True,capture_output=True)
(out/'host.log').write_text(result.stdout+result.stderr)
result.check_returncode()
report=dict(result='PASS',sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names},
    asan_ubsan=True,hardware_tested=False,desktop_integrated=False,scaler_pixel_validated=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(result.stdout);print(json.dumps(report))
