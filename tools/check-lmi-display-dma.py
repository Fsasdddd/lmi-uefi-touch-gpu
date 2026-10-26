"""Host-only adverse MMIO/owned-memory checks for the measured lmi adapter."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--evidence-dir',default='out/lmi-display-dma-host')
args=parser.parse_args()
out = root / args.evidence_dir
out.mkdir(exist_ok=True)
names = ['lmi-display-dma.c', 'lmi-display-dma.h', 'check-lmi-display-dma.c',
         'lmi-display-pipeline.c', 'lmi-display-pipeline.h', 'check-lmi-display-dma.py',
         'lmi-display-probe.c', 'lmi-display-probe.h']
subprocess.run(['clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(root / 'tools/check-lmi-display-dma.c'),
                str(root / 'tools/lmi-display-pipeline.c'), str(root / 'tools/lmi-display-probe.c'),
                '-o', str(out / 'check')], check=True)
result = subprocess.run([str(out / 'check')], text=True, capture_output=True)
(out / 'host.log').write_text(result.stdout + result.stderr)
report = dict(result='PASS' if result.returncode == 0 else 'FAIL',
              sources={n: hashlib.sha256((root / 'tools' / n).read_bytes()).hexdigest() for n in names},
              asan_ubsan=True, hardware_tested=False, desktop_integrated=False,
              scaler_pixel_validated=False)
(out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(result.stdout + result.stderr)
result.check_returncode()
print(json.dumps(report))
