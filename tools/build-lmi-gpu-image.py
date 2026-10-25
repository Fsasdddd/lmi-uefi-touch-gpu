"""Build a separate RAM md1 image with this phone's verified A650 firmware.

Run under the configured WSL. Keep the baseline images and evidence immutable.
Firmware is plain APFS data so the early kernel image reader can find it.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,zlib

repo=Path(__file__).resolve().parents[1]
base=repo/'out/lmi-ios-images-lslog'
out=repo/'out/lmi-ios-images-a650-fw'
snap=Path('/root/hackios-lmi/out/lmi-ios-images-a650-fw/root')
assert not out.exists() and not snap.exists(), 'Preserve existing GPU image work'
audit=json.loads((repo/'out/lmi-gpu-hardware/hardware-audit.json').read_text())
out.mkdir();snap.parent.mkdir(parents=True)
shutil.copytree('/root/hackios-lmi/out/lmi-ios-images-lslog/root',snap,symlinks=True)
(snap/'fw').mkdir(exist_ok=True)
files={}
for name,entry in audit['firmware'].items():
    src=repo/'out/lmi-gpu-hardware'/name
    data=src.read_bytes()
    assert entry['android_sha256_matches'] and len(data)==entry['bytes']
    assert hashlib.sha256(data).hexdigest()==entry['sha256']
    shutil.copy2(src,snap/'fw'/name)
    files[name]=entry
for filename,command in [
    ('build.log',['python3','/root/hackios-lmi/hackios/tools/apfs/mkapfs.py','-z','--plain','fw','-o',str(out/'root.apfs'),'redwood='+str(snap)]),
    ('apfs-check.log',['python3',str(repo/'tools/check-lmi-apfs-image.py'),str(out/'root.apfs'),'redwood='+str(snap)])]:
    with (out/filename).open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
data=(out/'root.apfs').read_bytes()
assert len(data)<32*1024*1024
os.link(base/'system.apfs',out/'system.apfs')
meta=json.loads((base/'manifest.json').read_text())
meta['images']['root.apfs']=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
    crc32=f'{zlib.crc32(data):08x}',source=str(snap),local=str(out/'root.apfs'))
meta['gpu_firmware']=dict(files=files,plain_directory='fw',device='lmi',hardware_loaded=False)
(out/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
shutil.copy2(base/'download-verification.json',out/'download-verification.json')
print(json.dumps(meta['images']['root.apfs'],indent=2))
