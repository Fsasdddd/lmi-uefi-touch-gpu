"""Verify retained Apple DMGs against the official IPSW ZIP CRCs and record provenance."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,struct,subprocess,zlib
workspace=Path('/root/hackios-lmi/hackios')
spec=importlib.util.spec_from_file_location('ios_fetch',workspace/'ios165/fetch-from-ipsw.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
tail=m.fetch(m.SIZE-65536,m.SIZE-1).read();at=tail.rfind(b'PK\x06\x06');assert at>=0
size,offset=struct.unpack('<QQ',tail[at+40:at+56]);cd=m.fetch(offset,offset+size-1).read()
crcs={};p=0
while cd[p:p+4]==b'PK\x01\x02':
    nl,el,cl=struct.unpack_from('<HHH',cd,p+28)
    name=cd[p+46:p+46+nl].decode();crcs[name]=struct.unpack_from('<I',cd,p+16)[0]
    p+=46+nl+el+cl
entries={name:(method,csize,usize) for name,method,csize,usize,pos in m.directory()}
records=[]
for member,local in [('096-04088-077.dmg','rootfs.dmg'),('096-04666-078.dmg','cryptex-os.dmg'),('096-03536-083.dmg','cryptex-app.dmg')]:
    path=workspace/'ios165'/local;crc=0;sha=hashlib.sha256();count=0
    with path.open('rb') as f:
        while chunk:=f.read(16*1024*1024):
            count+=len(chunk);crc=zlib.crc32(chunk,crc);sha.update(chunk)
    assert count==entries[member][2] and crc==crcs[member], f'Archive mismatch: {local}'
    records.append(dict(member=member,local=str(path),bytes=count,crc32=f'{crc:08x}',sha256=sha.hexdigest(),verified=True))
    print(local,count,'ZIP CRC verified',flush=True)
original=workspace/'ios165/rootfs/sbin/launchd';image=workspace/'userland/system.apfs'
embedded=subprocess.check_output([str(workspace/'apfs-work/apfs-tool'),'cat',str(image),'/sbin/launchd.ios'])
assert original.read_bytes()==embedded
report=dict(checked_at=datetime.datetime.now().astimezone().isoformat(),source=m.URL,dmgs=records,
    apple_launchd=dict(original=str(original),system_image=str(image),image_path='/sbin/launchd.ios',sha256=hashlib.sha256(embedded).hexdigest(),unmodified=True),
    note='Source TLS URL and ZIP CRC/length checked; no claim of Apple cryptographic signature validation or runtime success.')
Path('/mnt/f/PersonaLive/out/ios165-download-verification.json').write_text(json.dumps(report,indent=2)+'\n')
