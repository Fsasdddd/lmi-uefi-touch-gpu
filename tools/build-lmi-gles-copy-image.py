"""Freeze and build one GLES copy fix over the verified v31 touch image.

Runs in WSL; does not access a device or alter the baseline image/build outputs.
"""
from pathlib import Path
import hashlib,json,shutil,subprocess

r=Path(__file__).resolve().parents[1]
o=r/'out/lmi-gles-copy-v35'
candidate=r/'out/lmi-gpu-gl-copy-v35'
src=r/'userland-source/userland/src'
baseline=r/'out/lmi-gpu-gl-hid-usage-recheck-v31'
baseline_root=Path('/root/hackios-lmi/out/lmi-gpu-gl-hid-usage-recheck-v31/root')
snapshot=Path('/root/hackios-lmi/out/lmi-gpu-gl-copy-v35/root')
mesa=Path('/root/hackios-lmi/hackios/xnu-deps/build/mesa/out')
cc='/root/hackios-lmi/hackios/xnu-deps/host/bin/xnu-clang'
sdk='/root/hackios-lmi/gpu-build-env/theos/sdks/iPhoneOS16.5.sdk'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not candidate.exists() and not snapshot.exists(), 'Preserve existing candidates'
assert digest(baseline/'root.apfs')=='ca19afa138cd253132c7e0d761a14f56c0c66fce8f850209ae3aa54037de9416'
bm=json.loads((baseline/'manifest.json').read_text())
for name,sha in bm['files'].items(): assert digest(baseline_root/name)==sha,name

for name in ['eagl.c','gl_osmesa.c','redwood_gl.h']:
    shutil.copy2(src/name,o/name)
shutil.copy2(r/'tools/lmi-gl-copy-probe.c',o/'lmi-gl-copy-probe.c')
def function(text):
    marker='static void\ntarget_to_surface('
    start=text.index(marker)
    end=text.index('\n/*',start)
    return text[start:end]
old=function((o/'before-eagl.c').read_text())
new=function((o/'eagl.c').read_text())
assert 'glDisable(GL_SCISSOR_TEST)' not in old and 'glDisable(GL_SCISSOR_TEST)' in new
(o/'copy-production.inc').write_text(old.replace('target_to_surface(', 'control_target_to_surface(',1)+'\n'+new)
with (o/'eagl_gen.h').open('w') as f:
    subprocess.run(['python3',str(r/'userland-source/userland/mkeagl.py'),
        str(src/'eagl_slots.txt'),str(mesa/'gl.xml'),str(mesa/'exported-gl.txt'),str(o/'eagl.c')],stdout=f,check=True)
common=[cc,'-arch','arm64','-isysroot',sdk,'-O1','-I'+str(o)]
def build(name,args):
    with (o/(name+'.log')).open('w') as f:
        subprocess.run(common+args,stdout=f,stderr=subprocess.STDOUT,check=True)
build('shim',['-dynamiclib','-install_name','/redwood/lib/libredwood-gl.dylib',
    '-framework','CoreFoundation','-framework','IOKit','-framework','IOSurface','-lobjc',
    str(mesa/'libOSMesa.8.dylib'),'-o',str(o/'libredwood-gl.dylib'),str(o/'eagl.c'),str(o/'gl_osmesa.c')])
build('probe',['-framework','CoreFoundation','-framework','IOKit','-framework','IOSurface',
    str(mesa/'libOSMesa.8.dylib'),'-o',str(o/'lmi-gl-copy-probe'),str(o/'lmi-gl-copy-probe.c'),str(o/'gl_osmesa.c')])

candidate.mkdir();snapshot.parent.mkdir(parents=True,exist_ok=True)
shutil.copytree(baseline_root,snapshot,symlinks=True)
for p in baseline.iterdir():
    if p.is_file() and p.name not in ['root.apfs','manifest.json','build.log','check.log']:
        shutil.copy2(p,candidate/p.name)
shutil.copy2(o/'libredwood-gl.dylib',snapshot/'lib/libredwood-gl.dylib')
shutil.copy2(o/'lmi-gl-copy-probe',snapshot/'bin/lmi-gl-copy-probe')
jobs=snapshot/'etc/rc.jobs'
assert jobs.read_text().startswith('/redwood/bin/lmi-gpu-gl-probe\n')
jobs.write_text(jobs.read_text().replace('/redwood/bin/lmi-gpu-gl-probe\n',
    '/redwood/bin/lmi-gpu-gl-probe\n/redwood/bin/lmi-gl-copy-probe\n',1))
changed=[]
for p in snapshot.rglob('*'):
    if not p.is_file() or p.is_symlink(): continue
    rel=p.relative_to(snapshot);bp=baseline_root/rel
    if not bp.is_file() or digest(p)!=digest(bp):changed.append(str(rel))
assert sorted(changed)==['bin/lmi-gl-copy-probe','etc/rc.jobs','lib/libredwood-gl.dylib'],changed
image=candidate/'root.apfs'
with (candidate/'build.log').open('w') as f:
    subprocess.run(['python3','/root/hackios-lmi/hackios/tools/apfs/mkapfs.py','-z','--plain','fw',
        '-o',str(image),'redwood='+str(snapshot)],stdout=f,stderr=subprocess.STDOUT,check=True)
with (candidate/'check.log').open('w') as f:
    subprocess.run(['python3',str(r/'tools/check-lmi-apfs-image.py'),str(image),'redwood='+str(snapshot)],
        stdout=f,stderr=subprocess.STDOUT,check=True)
inputs=['before-eagl.c','eagl.c','gl_osmesa.c','redwood_gl.h','eagl_gen.h',
    'copy-production.inc','lmi-gl-copy-probe.c','libredwood-gl.dylib','lmi-gl-copy-probe']
sources={str((o/name).relative_to(r)):digest(o/name) for name in inputs}
sources[str(Path(__file__).resolve().relative_to(r))]=digest(Path(__file__).resolve())
bm.update(image=str(image),bytes=image.stat().st_size,sha256=digest(image),source=str(snapshot),
    gles_copy_regression=dict(source_sha256=sources,baseline_image_sha256=digest(baseline/'root.apfs'),
        changed_files=changed,reference_commit='dc773d94ce482d9b544accd62d82a5d1f8457e44',hardware_verified=False))
for name in changed:bm['files'][name]=digest(snapshot/name)
(candidate/'manifest.json').write_text(json.dumps(bm,indent=2)+'\n')
print(json.dumps({'image':str(image),'sha256':bm['sha256'],'changed_files':changed},indent=2))
