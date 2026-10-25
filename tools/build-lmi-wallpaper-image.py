"""Independent md1 wallpaper PNG overlay; original system and executables kept."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,zlib,struct
parser=argparse.ArgumentParser()
parser.add_argument('--output-name',default='lmi-ios-images-wallpaper-png-pid1')
args=parser.parse_args()
assert args.output_name.startswith('lmi-ios-images-') and '/' not in args.output_name and '\\' not in args.output_name
repo=Path(__file__).resolve().parents[1]
work=Path('/root/hackios-lmi/hackios')
base=repo/'out/lmi-ios-images-lslog'
out=repo/'out'/args.output_name
snap=Path('/root/hackios-lmi/out')/args.output_name/'root'
assert not (out/'root.apfs').exists(), 'Preserve completed/partial image'
out.mkdir(exist_ok=True);snap.parent.mkdir(parents=True,exist_ok=True)
if not snap.exists():shutil.copytree('/root/hackios-lmi/out/lmi-ios-images-lslog/root',snap,symlinks=True)
assets=repo/'out/lmi-wallpaper-png-resources'
shutil.copytree(assets,snap/'Wallpaper/iOS_16~iphone.wallpaperCollection',dirs_exist_ok=True)
# Keep the conversion audit on host only, outside Apple's collection bundle.
(snap/'Wallpaper/iOS_16~iphone.wallpaperCollection/conversion-audit.json').unlink()
objects=[]
for name,source in [('mount',repo/'tools/lmi-wallpaper-mount.c'),('mini',work/'userland/libmini/mini.c'),('start',work/'userland/libmini/start.S')]:
    obj=out/(name+'.o');objects.append(str(obj))
    subprocess.run(['clang','-target','arm64-apple-ios16.5','-Os','-ffreestanding','-fno-stack-protector','-fno-builtin',
        '-I'+str(work/'userland/libmini'),'-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-18','-arch','arm64','-platform_version','ios','16.5','16.5','-e','_start',
    '-pagezero_size','0x100000000','-o',str(out/'mount.linked'),*objects],check=True)
# Same reviewed static LC_UNIXTHREAD conversion as build-lmi-aligned-hello.py.
b=bytearray((out/'mount.linked').read_bytes());assert struct.unpack_from('<I',b)[0]==0xfeedfacf
ncmds,oldsize=struct.unpack_from('<II',b,16);commands=[];p=32;text_va=entryoff=first_section=None
for _ in range(ncmds):
    cmd,size=struct.unpack_from('<II',b,p)
    if cmd==0x19 and b[p+8:p+24].rstrip(b'\0')==b'__TEXT':
        text_va=struct.unpack_from('<Q',b,p+24)[0];nsects=struct.unpack_from('<I',b,p+64)[0]
        first_section=min(struct.unpack_from('<I',b,p+72+j*80+48)[0] for j in range(nsects))
    if cmd==0x80000028:entryoff=struct.unpack_from('<Q',b,p+8)[0]
    if cmd not in (0xe,0x80000028,0x80000022,0x1d):commands.append(bytes(b[p:p+size]))
    p+=size
assert text_va and entryoff and first_section
state=[0]*34;state[32]=text_va+entryoff
commands.append(struct.pack('<IIII',5,288,6,68)+struct.pack('<34Q',*state))
header=b''.join(commands);assert 32+len(header)<first_section
struct.pack_into('<II',b,16,len(commands),len(header))
struct.pack_into('<I',b,24,struct.unpack_from('<I',b,24)[0]&~(0x200000|4))
b[32:32+max(oldsize,len(header))]=bytes(max(oldsize,len(header)));b[32:32+len(header)]=header
executable=snap/'bin/lmi-wallpaper-mount';executable.write_bytes(b);executable.chmod(0o755)
rc=snap/'etc/rc';old=rc.read_text()
assert old.count('exec /sbin/launchd.ios')==1
rc.write_text(old.replace('exec /sbin/launchd.ios','exec /redwood/bin/lmi-wallpaper-mount'))
def run(name,args):
    print(name,flush=True)
    with (out/name).open('w') as f:subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,check=True)
run('build.log',['python3',str(work/'tools/apfs/mkapfs.py'),'-z','--plain','fw','-o',str(out/'root.apfs'),'redwood='+str(snap)])
run('apfs-check.log',['python3',str(repo/'tools/check-lmi-apfs-image.py'),str(out/'root.apfs'),'redwood='+str(snap)])
os.link(base/'system.apfs',out/'system.apfs')
meta=json.loads((base/'manifest.json').read_text())
def record(path):
    sha=hashlib.sha256();crc=0;size=0
    with path.open('rb') as f:
        while b:=f.read(16<<20):sha.update(b);crc=zlib.crc32(b,crc);size+=len(b)
    return dict(sha256=sha.hexdigest(),crc32=f'{crc:08x}',bytes=size)
meta['images']['root.apfs']=dict(**record(out/'root.apfs'),source=str(snap),local=str(out/'root.apfs'))
meta['wallpaper_overlay']=dict(assets=str(assets),mounted_before_launchd=True,source_collection_preserved=True,hardware_verified=False)
(out/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
shutil.copy2(base/'download-verification.json',out/'download-verification.json')
print(json.dumps(meta['images'],indent=2))
