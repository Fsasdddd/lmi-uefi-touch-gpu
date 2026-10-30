"""Build a separate CPU-opt-in loader; verify the generated C's sole change."""
from pathlib import Path
import ast,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
original=ROOT/'tools/build-lmi-loader.py';variant=ROOT/'tools/build-lmi-loader-v77.py'
source=original.read_text()
needle="        + (' lmi_gpu_desktop=1' if args.lmi_gpu_desktop else '')"
assert source.count(needle)==1 and not variant.exists()
source=source.replace(needle,needle+"\n        + (' lmi_cpu=2' if args.lmi_gpu_desktop else '')")
needle="report['lmi_gpu_desktop']=args.lmi_gpu_desktop"
assert source.count(needle)==1
source=source.replace(needle,needle+"\nreport['lmi_cpu_requests']=2 if args.lmi_gpu_desktop else 0")
compile(source,str(variant),'exec');variant.write_text(source)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
profile=json.loads((ROOT/'out/lmi-loader/manifest.json').read_text())
# This live staging directory is mutable. Preserve its entire current contents
# independently; frozen historical packages and sources are never changed.
archive=ROOT/'out/lmi-cpu-epss/loader-before-v77';assert not archive.exists()
release=json.loads((ROOT/'out/lmi-render-minimal-v76/offline-release.json').read_text())
assert not any(name.startswith(('out/lmi-loader/','out/lmi-loader-test/','out/lmi-uefi-loader-test/')) for name in release['artifacts'])
shutil.copytree(ROOT/'out/lmi-loader',archive)
args=['--checkpoints','--max-checkpoint','63','--trace-return-stub']
for node in ast.walk(ast.parse(original.read_text())):
    if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute) or node.func.attr!='add_argument':continue
    if not node.args or not isinstance(node.args[0],ast.Constant):continue
    flag=node.args[0].value;dest=flag[2:].replace('-','_')
    if flag in args or dest in ['checkpoints','max_checkpoint','trace_return_stub']:continue
    if dest not in profile:continue
    value=profile[dest]
    if isinstance(value,dict):value=value.get('enabled',False)
    if isinstance(value,bool):
        if value:args.append(flag)
    elif value is not None:args.extend([flag,str(value)])
log=ROOT/'out/lmi-cpu-epss/loader-build-v77.log'
with log.open('w') as handle:subprocess.run([sys.executable,str(variant),*args],stdout=handle,stderr=subprocess.STDOUT,check=True)
before=(archive/'loader.c').read_text();after=(ROOT/'out/lmi-loader/loader.c').read_text()
assert after.count(' lmi_cpu=2')==1 and after.replace(' lmi_cpu=2','')==before
oldmeta=profile;newmeta=json.loads((ROOT/'out/lmi-loader/manifest.json').read_text())
for name,value in oldmeta.items():
    if name not in ['bytes','sha256']:assert newmeta[name]==value,(name,value,newmeta[name])
assert newmeta['lmi_cpu_requests']==2
report=dict(result='PASS_LOADER_C_ONLY_NEW_CPU_BOOT_ARG',args=args,original_builder_sha256=sha(original),
    variant_builder_sha256=sha(variant),parent_loader_sha256=oldmeta['sha256'],loader_sha256=newmeta['sha256'],
    original_generated_c_sha256=sha(archive/'loader.c'),new_generated_c_sha256=sha(ROOT/'out/lmi-loader/loader.c'),
    storage_commands_unchanged=True,other_boot_args_unchanged=True,device_access=False)
(ROOT/'out/lmi-cpu-epss/loader-variant-v77.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: loader C differs only by lmi_cpu=2; all existing profile fields preserved')
