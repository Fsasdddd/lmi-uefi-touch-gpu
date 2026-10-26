"""Reproduce the opt-in mode29/30 RAM-only diagnostic profile in WSL.

This builds pinned local inputs; it never accesses a device or updates deps.
"""
from pathlib import Path
import argparse,subprocess,os
p=argparse.ArgumentParser();p.add_argument('mode',type=int,choices=(29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46));p.add_argument('--package',action='store_true');p.add_argument('--tile',action='store_true');p.add_argument('--desktop',action='store_true')
p.add_argument('--ios-observe-seconds',type=int,choices=(25,45,180),default=25)
p.add_argument('--smp-cpus',type=int,choices=(1,2,4,8),default=1,help='Opt-in CPU count with matching lmi SMP RAM-return guard')
p.add_argument('--fb-threads',type=int,choices=range(1,9),default=1,help='Parallel desktop framebuffer scaling workers')
p.add_argument('--fb-queue',type=int,choices=(1,2),default=2)
p.add_argument('--fb-beat',type=int,choices=(0,1),default=1,help='Software pacing only, not hardware vsync')
p.add_argument('--display-census',action='store_true',help='Read-only DPU state before/after RAM run')
p.add_argument('--touch-input',action='store_true',help='Keep the verified FT3518 input path with desktop GLES')
p.add_argument('--cpu-profile',action='store_true',help='Collect two bounded native CPU snapshots in desktop180')
p.add_argument('--lsd-profile',action='store_true',help='Collect two bounded native lsd stacks in desktop180')
p.add_argument('--process-profile',choices=('Preferences','PosterBoard','backboardd','cfprefsd'),help='Collect two bounded service stacks at130/155 seconds in desktop180')
a=p.parse_args()
assert a.ios_observe_seconds==25 or a.desktop, 'Longer GPU run requires the mode46 desktop profile'
assert not a.touch_input or (a.desktop and a.ios_observe_seconds in (45,180))
assert not a.cpu_profile or (a.desktop and a.ios_observe_seconds==180)
assert not a.lsd_profile or (a.desktop and a.ios_observe_seconds==180 and not a.cpu_profile)
assert not a.process_profile or (a.desktop and a.ios_observe_seconds==180 and not a.cpu_profile and not a.lsd_profile)
assert not a.desktop or (a.tile and a.mode==46)
assert a.fb_threads<=a.smp_cpus and (a.fb_threads==1 or a.desktop)
assert a.desktop or (a.fb_queue==2 and a.fb_beat==1 and not a.display_census)
assert not a.tile or a.mode==46
r=Path(__file__).resolve().parents[1]
gpu=['cx-probe','clock-probe','gmu-readonly','smmu-readonly','arc-inventory','rscc-readonly','rpmh-probe',
     'rscc-sde-probe','rpmh-interface-probe','rpmh-bus-probe','rpmh-arc-slot-probe','rsc-init','rsc-sequence-probe',
     'pdc-enable-probe','rsc-pdc-vote-probe','gmu-200mhz-probe','gmu-route-probe','ram-plan','ram-hfi','gmu-boot','hfi-io']
if a.mode>=30:gpu+=['table-plan']
if a.mode>=31:gpu+=['hfi-perf']
if a.mode>=32:gpu+=['hfi-core']
if a.mode>=33:gpu+=['gx']
if a.mode>=34:gpu+=['cp-plan']
if a.mode>=35:gpu+=['core-memory']
if a.mode in (36,37,38,40,41,42,43,44,45,46):gpu+=['cp']
if a.mode in (37,38,40,41,42,43,44,45,46):gpu+=['cp-fence']
if a.mode==38:gpu+=['cp-sp-clock']
if a.mode==39:gpu+=['core-access']
if a.mode>=40:gpu+=['fal-veto']
if a.mode==41:gpu+=['cp-config-plan']
if a.mode>=42:gpu+=['cp-config-ready']
if a.mode==43:gpu+=['scm-query']
if a.mode>=44:gpu+=['zap-metadata']
if a.mode>=45:gpu+=['zap-load']
if a.mode==46:gpu+=['unsecure']
if a.tile:gpu+=['tile']
if a.desktop:gpu+=['desktop']
flags=['--lmi-gpu-'+v for v in gpu]
def run(label,cmd,cwd=r,env=None):
    print(label,flush=True)
    with (r/f'out/lmi-gpu-mode{a.mode}-{label}.log').open('w') as log:
        subprocess.run(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
run('source-check',['python3','tools/check-lmi-gpu-boot-source.py'])
run('kernel',['python3','tools/build-lmi-ios-probe.py','--continue-launchd','--normalize-return-tcr','--trace-return',
    '--return-stub-ro','--clean-return-tables','--trace-graphics','--release-graphics-console','--lmi-touch','--smp-cpus',str(a.smp_cpus),*flags])
if a.package:
    run('loader',['python3','tools/build-lmi-loader.py','--checkpoints','--max-checkpoint','63','--ios-observe-seconds',str(a.ios_observe_seconds),'--trace-return-stub','--smp-cpus',str(a.smp_cpus),'--fb-threads',str(a.fb_threads),'--fb-queue',str(a.fb_queue),'--fb-beat',str(a.fb_beat),*(['--display-census'] if a.display_census else []),*flags,*(['--lmi-touch-input'] if a.touch_input else []),*(['--ios-top-stacks'] if a.cpu_profile else []),*(['--ios-lsd-stacks'] if a.lsd_profile else []),*(['--ios-process-stacks',a.process_profile] if a.process_profile else [])])
    run('stage',['python3','tools/stage-lmi-uefi.py','--patched','--full-loader'])
    venv=Path('/root/hackios-lmi/mu-venv');env=dict(os.environ,VIRTUAL_ENV=str(venv),PATH=str(venv/'bin')+':'+os.environ['PATH'])
    run('uefi',[str(venv/'bin/python'),'build_uefi.py','-d','lmi','-r','RELEASE'],Path('/root/hackios-lmi/mu-silicium'),env)
    run('export',['python3','tools/export-lmi-uefi.py','--patched','--full-loader'])
    run('package',['python3','tools/package-lmi-diagnostics.py','--full-loader'])
