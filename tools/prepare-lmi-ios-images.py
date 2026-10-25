"""Copy verified local iOS RAM images to F: and record hashes/transfer CRCs."""
from pathlib import Path
import argparse,hashlib,json,shutil,zlib
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,default=Path('out/lmi-ios-images'),help='New image directory; existing images are never overwritten because evidence may hardlink them')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1];out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
assert not any((out/name).exists() for name in ('system.apfs','root.apfs','manifest.json')), f'Preserve existing image/evidence in {out}; select a new --output directory'
verification=json.loads((root/'out/ios165-download-verification.json').read_text())
assert len(verification['dmgs'])==3 and all(r['verified'] for r in verification['dmgs'])
assert verification['apple_launchd']['unmodified']
records={}
for name in ('system.apfs','root.apfs'):
    src=Path('/root/hackios-lmi/hackios/userland')/name;dest=out/name
    shutil.copyfile(src,dest)
    sha=hashlib.sha256();crc=0;size=0
    with dest.open('rb') as f:
        while chunk:=f.read(16*1024*1024):sha.update(chunk);crc=zlib.crc32(chunk,crc);size+=len(chunk)
    records[name]=dict(bytes=size,sha256=sha.hexdigest(),crc32=f'{crc:08x}',source=str(src),local=str(dest))
    print(name,size,sha.hexdigest(),flush=True)
(out/'manifest.json').write_text(json.dumps(dict(images=records,apple_launchd=verification['apple_launchd'],source=verification['source'],persistent_storage_writes=False),indent=2)+'\n')
shutil.copy2(root/'out/ios165-download-verification.json',out/'download-verification.json')
