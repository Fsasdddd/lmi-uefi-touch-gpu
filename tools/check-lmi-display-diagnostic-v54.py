from pathlib import Path
import subprocess,json,hashlib
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-diagnostic-v54-host';out.mkdir(exist_ok=True)
names=['check-lmi-display-diagnostic-v54.c','check-lmi-display-dma-v54.c','lmi-display-dma-v54.c','lmi-display-diagnostic-v54.c','lmi-display-pipeline-v51.c','lmi-display-probe.c','lmi-display-pipeline.h','lmi-display-dma.h','lmi-display-probe.h','check-lmi-display-diagnostic-v54.py']
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(root/'tools/check-lmi-display-diagnostic-v54.c'),str(root/'tools/lmi-display-pipeline-v51.c'),str(root/'tools/lmi-display-probe.c'),str(root/'tools/lmi-display-diagnostic-v54.c'),'-o',str(out/'check')],check=True)
p=subprocess.run([str(out/'check')],text=True,capture_output=True)
(out/'host.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr);p.check_returncode()
(out/'result.json').write_text(json.dumps(dict(result='PASS',asan_ubsan=True,hardware_tested=False,pixel_validated=False,desktop_pipeline_enabled=False,sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names}),indent=2)+'\n')
