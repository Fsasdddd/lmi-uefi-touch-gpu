from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-probe-v55-host';out.mkdir(exist_ok=True)
names=['check-lmi-display-probe-v55.c','check-lmi-display-dma-v55.c','lmi-display-probe-v55.c','lmi-display-dma-v55.c','lmi-display-probe.h','lmi-display-dma.h','lmi-display-pipeline-v51.c','lmi-display-pipeline.h','check-lmi-display-probe-v55.py']
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
    *[str(root/'tools'/n) for n in ['check-lmi-display-probe-v55.c','lmi-display-probe-v55.c','lmi-display-pipeline-v51.c','lmi-display-probe.c']],'-o',str(out/'check')],check=True)
p=subprocess.run([str(out/'check')],capture_output=True,text=True);(out/'host.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr);p.check_returncode()
(out/'result.json').write_text(json.dumps(dict(result='PASS',asan_ubsan=True,hardware_tested=False,
    bypass_pixel_equivalence=False,experimental_only=True,sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names}),indent=2)+'\n')
