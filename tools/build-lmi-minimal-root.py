"""Small APFS root for mount/EL0 path development; not the iOS system image."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-root-minimal';out.mkdir(exist_ok=True)
tree=out/'tree'
for folder in ('sbin','dev','bin','private/var','redwood'):(tree/folder).mkdir(parents=True,exist_ok=True)
hello=root/'userland-source/prebuilt/userland/hello'
checks=(hello.parent/'SHA256SUMS').read_text()
digest=hashlib.sha256(hello.read_bytes()).hexdigest()
assert any(line.split()==[digest,'prebuilt/userland/hello'] for line in checks.splitlines()), 'Pinned hello checksum mismatch'
aligned=root/'out/lmi-user-entry-fix/hello'
aligned_meta=json.loads((aligned.parent/'manifest.json').read_text())
assert hashlib.sha256(aligned.read_bytes()).hexdigest()==aligned_meta['sha256']
shutil.copy2(aligned,tree/'sbin/launchd')
manifest=out/'tree.manifest'
manifest.write_bytes((''.join(f'040755\t0\t0\t{p}\n' for p in ('sbin','dev','bin','private','private/var','redwood'))+'0100755\t0\t0\tsbin/launchd\n').encode())
image=out/'root.apfs'
subprocess.run([sys.executable,str(root/'userland-source/tools/apfs/mkapfs.py'),'-o',str(image),f'lmi-test={tree},manifest={manifest}'],check=True)
assert image.stat().st_size<40*1024*1024
meta=dict(image=str(image),bytes=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),upstream_hello_sha256=digest,aligned_hello_sha256=aligned_meta['sha256'],
    scope='Read-only APFS mount test containing the stack-aligned raw-syscall hello as /sbin/launchd. No Apple iOS files; not proof of iOS userspace.',tree=str(tree))
(out/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps(meta,indent=2))
