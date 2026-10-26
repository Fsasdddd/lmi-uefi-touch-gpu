"""Host-only HFI cache/ACK/fault coverage for the stock-bin index7 request."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-gpu-gx-v57-host';out.mkdir(exist_ok=True)
cmd=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(root/'tools/check-lmi-gpu-gx-v57.c'),'-o',str(out/'check')]
subprocess.run(cmd,check=True)
p=subprocess.run([str(out/'check')],capture_output=True,text=True)
(out/'host.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr);p.check_returncode()
names=['check-lmi-gpu-gx-v57.py','check-lmi-gpu-gx-v57.c','lmi-gpu-gx-v57.c','lmi-gpu-hfi-perf.c','lmi-gpu-hfi-transfer.h','lmi-gpu-boot-regs.h']
report=dict(result='PASS',asan_ubsan=True,scenarios=34,requested_frequency_index=7,hardware_tested=False,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
