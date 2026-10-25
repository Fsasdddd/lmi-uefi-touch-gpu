"""Build an isolated RAM root image with the GPU GLES shim and pixel probe."""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess

repo = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output-name', default='lmi-gpu-gl-test-v2')
parser.add_argument('--quiet-oslog', action='store_true')
parser.add_argument('--diagnostics', action='store_true', help='Bounded read-only wallpaper and kernel-log helpers')
parser.add_argument('--input-trace', action='store_true', help='First192 input records with original coordinates and timestamps')
parser.add_argument('--single-user-lsd', action='store_true', help='Opt-in lsd-only empty persona list for this single-user RAM port')
parser.add_argument('--hid-simple-retry', action='store_true', help='Retry the sending HID client during event-server startup; bounded dispatch diagnostics')
parser.add_argument('--hid-routing-log', action='store_true', help='Observe backboardd HID routing decisions through its original os_log output')
parser.add_argument('--hid-routing-trace', action='store_true', help='Bounded stock BackBoard processor and service-selection observers')
parser.add_argument('--hid-usage-recheck', action='store_true', help='Recheck zero cached usages for the identified Redwood touch screen before service matching')
args = parser.parse_args()
assert not args.hid_routing_log or (args.input_trace and args.quiet_oslog)
assert not args.hid_routing_trace or args.input_trace
assert args.output_name.startswith('lmi-gpu-gl-') and '/' not in args.output_name and '\\' not in args.output_name and '..' not in args.output_name
out = repo / 'out' / args.output_name
snapshot = Path('/root/hackios-lmi/out') / args.output_name / 'root'
base = Path('/root/hackios-lmi/out/lmi-ios-images-a650-fw/root')
baseline = repo / 'out/lmi-ios-images-a650-fw/root.apfs'
mesa = Path('/root/hackios-lmi/hackios/xnu-deps/build/mesa/out/libOSMesa.8.dylib')
shim = repo / 'out/lmi-gpu-research/gl-build/libredwood-gl.dylib'
probe = repo / 'out/lmi-gpu-research/gl-build/lmi-gpu-gl-probe'
mkapfs = Path('/root/hackios-lmi/hackios/tools/apfs/mkapfs.py')
assert not out.exists() and not snapshot.exists(), 'Preserve prior image work'
assert base.is_dir() and mesa.is_file() and shim.is_file() and probe.is_file() and mkapfs.is_file()
assert (base / 'etc/inject.conf').is_file() and (base / 'etc/rc.jobs').is_file()
out.mkdir()
snapshot.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(base, snapshot, symlinks=True)
shutil.copy2(mesa, snapshot / 'lib/libOSMesa.8.dylib')
shutil.copy2(shim, snapshot / 'lib/libredwood-gl.dylib')
shutil.copy2(probe, snapshot / 'bin/lmi-gpu-gl-probe')

# libredwood's opengl_es() loads the shim only after RedwoodGPU is present.
# Keep that gating and the existing injection mapping intact.
inject = snapshot / 'etc/inject.conf'
assert 'libredwood-gl.dylib' not in inject.read_text()

jobs = snapshot / 'etc/rc.jobs'
job_text = jobs.read_text()
assert 'lmi-gpu-gl-probe' not in job_text
jobs.write_text('/redwood/bin/lmi-gpu-gl-probe\n' + job_text)
diagnostic_files = []
if args.input_trace or args.single_user_lsd or args.hid_simple_retry or args.hid_usage_recheck:
    inject_source = out / 'inject.c'
    source_dir = repo / 'userland-source/userland/src'
    for name in ['inject.c', 'redwood_input.h', 'redwood_gl.h']:
        shutil.copy2(source_dir / name, out / name)
    subprocess.run(['/root/hackios-lmi/hackios/xnu-deps/host/bin/xnu-clang', '-arch', 'arm64',
        '-isysroot', '/root/hackios-lmi/gpu-build-env/theos/sdks/iPhoneOS16.5.sdk', '-O1',
        *(['-DLMI_INPUT_TRACE=1'] if args.input_trace else []),
        *(['-DLMI_LSD_SINGLE_USER=1'] if args.single_user_lsd else []),
        *(['-DLMI_HID_SIMPLE_RETRY=1'] if args.hid_simple_retry else []),
        *(['-DLMI_HID_ROUTING_TRACE=1'] if args.hid_routing_trace else []),
        *(['-DLMI_HID_USAGE_RECHECK=1'] if args.hid_usage_recheck else []),
        '-dynamiclib', '-install_name', '/redwood/lib/libredwood.dylib',
        '-framework', 'CoreFoundation', '-framework', 'IOKit', '-lobjc',
        '-o', str(out / 'libredwood.dylib'), str(inject_source)], check=True)
    shutil.copy2(out / 'libredwood.dylib', snapshot / 'lib/libredwood.dylib')
    diagnostic_files.append(snapshot / 'lib/libredwood.dylib')
    if args.input_trace:
        shutil.copy2(source_dir / 'inject_sb.c', out / 'inject_sb.c')
        subprocess.run(['/root/hackios-lmi/hackios/xnu-deps/host/bin/xnu-clang', '-arch', 'arm64',
            '-isysroot', '/root/hackios-lmi/gpu-build-env/theos/sdks/iPhoneOS16.5.sdk', '-O1',
            '-fblocks', '-DLMI_INPUT_TRACE=1', '-dynamiclib', '-install_name', '/redwood/lib/libredwood-sb.dylib',
            '-framework', 'CoreFoundation', '-framework', 'IOKit', '-lobjc',
            '-o', str(out / 'libredwood-sb.dylib'), str(out / 'inject_sb.c')], check=True)
        shutil.copy2(out / 'libredwood-sb.dylib', snapshot / 'lib/libredwood-sb.dylib')
        diagnostic_files.append(snapshot / 'lib/libredwood-sb.dylib')
if args.single_user_lsd:
    mapping = inject.read_text()
    before = '/redwood/lib/libredwood.dylib backboardd containermanagerd containermanagerd_system\n'
    assert mapping.count(before) == 1
    inject.write_text(mapping.replace(before, before.rstrip('\n') + ' lsd\n'))
if args.diagnostics:
    for name in ['lmi-wallpaper-probe', 'lmi-kernel-log']:
        source = out / (name + '.c')
        shutil.copy2(repo / 'tools' / (name + '.c'), source)
        command = ['/root/hackios-lmi/hackios/xnu-deps/host/bin/xnu-clang', '-arch', 'arm64',
            '-isysroot', '/root/hackios-lmi/gpu-build-env/theos/sdks/iPhoneOS16.5.sdk',
            '-O1', str(source), '-o', str(out / name)]
        if name == 'lmi-wallpaper-probe':
            command += ['-framework', 'Foundation', '-framework', 'UIKit',
                '-framework', 'ImageIO', '-framework', 'CoreGraphics', '-lobjc']
        subprocess.run(command, check=True)
        shutil.copy2(out / name, snapshot / 'bin' / name)
        diagnostic_files.append(snapshot / 'bin' / name)
    asset = repo / 'out/lmi-wallpaper-png-resources/Wallpapers/7400.WWDC_2022-375w-812h@3x~iphone.wallpaper/7400.WWDC_2022_Background-375w-812h@3x~iphone.ca/assets/Head.png'
    (snapshot / 'share').mkdir(exist_ok=True)
    shutil.copy2(asset, snapshot / 'share/lmi-wallpaper-head.png')
    diagnostic_files.append(snapshot / 'share/lmi-wallpaper-head.png')
    jobs.write_text('/redwood/bin/lmi-gpu-gl-probe\n'
        '/redwood/bin/lmi-wallpaper-probe /redwood/share/lmi-wallpaper-head.png &\n' + job_text)
    daemon = snapshot / 'LaunchDaemons/com.redwood.kernel-log.plist'
    daemon.write_bytes(plistlib.dumps(dict(Label='com.redwood.kernel-log',
        ProgramArguments=['/redwood/bin/lmi-kernel-log'], RunAtLoad=True, UserName='root',
        StandardOutPath='/dev/console', StandardErrorPath='/dev/console'), fmt=plistlib.FMT_BINARY))
    diagnostic_files.append(daemon)

quieted_jobs = []
if args.quiet_oslog:
    for job in (snapshot / 'LaunchDaemons').glob('*.plist'):
        config = plistlib.loads(job.read_bytes())
        env = config.get('EnvironmentVariables', {})
        if 'OS_ACTIVITY_DT_MODE' in env:
            del env['OS_ACTIVITY_DT_MODE']
            job.write_bytes(plistlib.dumps(config, fmt=plistlib.FMT_BINARY))
            quieted_jobs.append(job.name)
if args.hid_routing_log:
    job = snapshot / 'LaunchDaemons/com.apple.backboardd.plist'
    config = plistlib.loads(job.read_bytes())
    config.setdefault('EnvironmentVariables', {})['OS_ACTIVITY_DT_MODE'] = 'YES'
    job.write_bytes(plistlib.dumps(config, fmt=plistlib.FMT_BINARY))
    quieted_jobs.remove(job.name)
    diagnostic_files.append(job)

image = out / 'root.apfs'
with (out / 'build.log').open('w') as log:
    subprocess.run(['python3', str(mkapfs), '-z', '--plain', 'fw', '-o', str(image),
                    'redwood=' + str(snapshot)], stdout=log, stderr=subprocess.STDOUT, check=True)
with (out / 'check.log').open('w') as log:
    subprocess.run(['python3', str(repo / 'tools/check-lmi-apfs-image.py'), str(image),
                    'redwood=' + str(snapshot)], stdout=log, stderr=subprocess.STDOUT, check=True)

files = {str(path.relative_to(snapshot)): hashlib.sha256(path.read_bytes()).hexdigest()
         for path in (snapshot / 'lib/libOSMesa.8.dylib', snapshot / 'lib/libredwood-gl.dylib',
                      snapshot / 'bin/lmi-gpu-gl-probe', snapshot / 'etc/inject.conf',
                      snapshot / 'etc/rc.jobs', *diagnostic_files)}
manifest = dict(image=str(image), bytes=image.stat().st_size,
                sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                source=str(snapshot), files=files, apfs_checked=True,
                quieted_oslog_jobs=quieted_jobs,
                bounded_diagnostics=args.diagnostics,
                bounded_input_trace=args.input_trace,
                single_user_lsd=args.single_user_lsd,
                hid_simple_retry=args.hid_simple_retry,
                hid_routing_log=args.hid_routing_log,
                hid_routing_trace=args.hid_routing_trace,
                hid_usage_recheck=args.hid_usage_recheck,
                input_trace_source_sha256={name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                    for name in ['inject.c', 'redwood_input.h', 'redwood_gl.h', *(['inject_sb.c'] if args.input_trace else [])]} if args.input_trace or args.single_user_lsd or args.hid_simple_retry else {},
                diagnostic_source_sha256={name: hashlib.sha256((out / (name + '.c')).read_bytes()).hexdigest()
                    for name in ['lmi-wallpaper-probe', 'lmi-kernel-log']} if args.diagnostics else {},
                baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
                firmware_preserved=all(p.read_bytes() == (snapshot/'fw'/p.name).read_bytes()
                                       for p in (base/'fw').iterdir() if p.is_file()),
                purpose='RAM-only desktop GLES verification; no persistent storage writes')
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
