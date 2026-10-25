"""Read Apple executables back through the kernel APFS reader and compare originals.

Run in WSL; this reads local images only and does not access the phone.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--evidence',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
image=root/'out/lmi-ios-images/system.apfs'
meta=json.loads((image.parent/'manifest.json').read_text())
sha=hashlib.sha256()
with image.open('rb') as f:
    while block:=f.read(16*1024*1024):sha.update(block)
assert sha.hexdigest()==meta['images']['system.apfs']['sha256']
source=Path('/root/hackios-lmi/hackios/ios165/rootfs')
reader=Path('/root/hackios-lmi/hackios/apfs-work/apfs-tool')
paths=['/sbin/launchd.ios','/usr/libexec/backboardd','/usr/libexec/runningboardd',
       '/usr/libexec/containermanagerd','/usr/libexec/logd',
       '/System/Library/CoreServices/SpringBoard.app/SpringBoard']
records=[]
for path in paths:
    original=source/(path.lstrip('/') if path!='/sbin/launchd.ios' else 'sbin/launchd')
    data=subprocess.check_output([str(reader),'cat',str(image),path],timeout=60)
    digest=hashlib.sha256(data).hexdigest()
    assert data and digest==hashlib.sha256(original.read_bytes()).hexdigest(), path
    records.append(dict(image_path=path,original=str(original),bytes=len(data),sha256=digest,unmodified=True))
    print(path,len(data),digest,flush=True)
out=args.evidence.resolve()/'apple-services-verification.json'
assert not out.exists(), f'Preserve existing verification {out}'
out.write_text(json.dumps(dict(image_sha256=sha.hexdigest(),reader_sha256=hashlib.sha256(reader.read_bytes()).hexdigest(),executables=records,
    scope='Byte identity in the APFS image. Execution, injection and desktop status require separate live evidence.'),indent=2)+'\n')
