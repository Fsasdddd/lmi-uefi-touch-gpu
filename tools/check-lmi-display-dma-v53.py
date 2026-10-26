"""Host-only adverse MMIO/owned-memory checks for the measured lmi adapter."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--evidence-dir',default='out/lmi-display-dma-host-v53')
args=parser.parse_args()
out = root / args.evidence_dir
out.mkdir(exist_ok=True)
names = ['lmi-display-dma-v53.c', 'lmi-display-dma.h', 'check-lmi-display-dma-v53.c',
         'lmi-display-pipeline-v51.c', 'lmi-display-pipeline.h', 'check-lmi-display-dma-v53.py',
         'lmi-display-probe.c', 'lmi-display-probe.h', 'lmi-display-pipeline-v50.c']
subprocess.run(['clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(root / 'tools/check-lmi-display-dma-v53.c'),
                str(root / 'tools/lmi-display-pipeline-v51.c'), str(root / 'tools/lmi-display-probe.c'),
                '-o', str(out / 'check')], check=True)
result = subprocess.run([str(out / 'check')], text=True, capture_output=True)
(out / 'host.log').write_text(result.stdout + result.stderr)
# Reproduce the actual v50 readback refusal through the production adapter,
# using v50's unchanged plan and the measured bit31=0 register model.
regression=out/'v50-regression.c'
regression.write_text(r'''
#define main all_protocol_checks
#include "check-lmi-display-dma-v53.c"
#undef main
int main(void) {
 struct fake *f=setup();f->ignored_blend=1;
 assert(lmi_dma_prepare(f->d));unsigned before=f->starts;
 assert(!lmi_dma_set_scaling(f->d,1));
 assert(*reg(f,0,0x5a04)==0x20034401 && f->starts==before);
 assert(lmi_dma_restore(f->d));restored(f);destroy(f);
 puts("PASS: v50 blend readback refusal reproduced; no scaled START issued");
}
''')
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
 '-fsanitize=address,undefined','-I',str(root/'tools'),str(regression),
 str(root/'tools/lmi-display-pipeline-v50.c'),str(root/'tools/lmi-display-probe.c'),
 '-o',str(out/'v50-regression')],check=True)
prior=subprocess.run([str(out/'v50-regression')],capture_output=True,text=True)
(out/'v50-regression.log').write_text(prior.stdout+prior.stderr)
prior.check_returncode();print(prior.stdout)
report = dict(result='PASS' if result.returncode == 0 else 'FAIL',
              sources={n: hashlib.sha256((root / 'tools' / n).read_bytes()).hexdigest() for n in names},
              asan_ubsan=True, v50_refusal_reproduced=True, hardware_tested=False, desktop_integrated=False,
              scaler_pixel_validated=False)
(out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(result.stdout + result.stderr)
result.check_returncode()
print(json.dumps(report))
