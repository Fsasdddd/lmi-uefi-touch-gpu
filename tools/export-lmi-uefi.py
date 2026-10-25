"""Validate and export the offline lmi UEFI FD build from WSL."""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--patched', action='store_true')
parser.add_argument('--usb-probe', action='store_true')
parser.add_argument('--full-loader', action='store_true')
args = parser.parse_args()

root = Path(__file__).resolve().parents[1]
mu = Path.home() / 'hackios-lmi/mu-silicium'
build = mu / 'Build/lmiPkg/RELEASE_CLANGPDB'
out = root / ('out/lmi-uefi-loader-test' if args.full_loader else 'out/lmi-uefi-usb-test' if args.usb_probe else 'out/lmi-uefi-patched' if args.patched else 'out/lmi-uefi')
out.mkdir(parents=True, exist_ok=True)
fd = (build / 'FV/SILICIUM_UEFI.fd').read_bytes()
assert len(fd) == 0x300000
assert fd[40:44] == b'_FVH'
fv_length = struct.unpack_from('<Q', fd, 32)[0]
header_length = struct.unpack_from('<H', fd, 48)[0]
assert 56 <= header_length <= len(fd) and header_length % 2 == 0
assert sum(struct.unpack_from(f'<{header_length//2}H', fd)) & 0xffff == 0
assert header_length <= fv_length <= len(fd)
bds = (build / 'AARCH64/BdsDxe.efi').read_bytes()
pe = struct.unpack_from('<I', bds, 60)[0]
assert bds[:2] == b'MZ' and bds[pe:pe+4] == b'PE\0\0'
assert struct.unpack_from('<H', bds, pe+4)[0] == 0xaa64
assert 'HackiOS lmi UEFI diagnostics'.encode('utf-16le') in bds
assert 'UsbFunctionIo: %r'.encode('utf-16le') in bds
if args.usb_probe or args.full_loader:
    assert 'USB probe LoadImage: %r'.encode('utf-16le') in bds
original = root / 'firmware-extracted/xbl_4/BOOT.XF.3.2-00304-SM8250-2'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
firmware_files = []
patched = {}
if args.patched:
    patched = {p['path']: p['patched_sha256'] for p in json.loads(
        (root / 'out/lmi-firmware-patched/manifest.json').read_text())['patches']}
for p in original.rglob('*'):
    if p.is_file():
        q = mu / 'Binaries/lmi' / p.relative_to(original)
        key = p.relative_to(original).as_posix()
        assert sha(q) == patched.get(key, sha(p)), str(p)
        firmware_files.append(str(p.relative_to(original)))
for name in ('FV/SILICIUM_UEFI.fd', 'BUILD_REPORT.TXT', 'BUILD_TOOLS_REPORT.json',
             'FD_REPORT.HTML', 'AARCH64/BdsDxe.efi'):
    shutil.copy2(build/name, out/Path(name).name)
shutil.copytree(mu / 'Platforms/Xiaomi/lmiPkg',
                root / 'port-drafts/uefi/Platforms/Xiaomi/lmiPkg', dirs_exist_ok=True)
shutil.copy2(mu / 'Resources/Configs/lmi.toml', root / 'port-drafts/uefi/lmi.toml')
(out / 'mu-source.patch').write_bytes(subprocess.check_output(['git', '-C', str(mu), 'diff', '--',
    'BootShim', 'Silicon/Silicium/SiliciumPkg/Library/BootManagerLib']))
report = dict(result='PASS: offline UEFI FD build and structural checks',
    mu_commit=subprocess.check_output(['git', '-C', str(mu), 'rev-parse', 'HEAD'], text=True).strip(),
    fd_bytes=len(fd), fd_sha256=hashlib.sha256(fd).hexdigest(),
    fd_base='0x9fc00000', fv_length=fv_length, fv_header_checksum_valid=True,
    bds_machine='ARM64', lmi_diagnostics_present=True,
    firmware_files_verified_unchanged=len(firmware_files)-len(patched),
    firmware_files_verified_patched=len(patched),
    firmware_binary_patches_applied=args.patched, standalone_boot_image=False,
    hardware_tested=False,
    usb_transport_probe=args.usb_probe,
    full_source_loader=args.full_loader,
    limitations=['Offline checks do not establish hardware results for this image; consult matching hardware-test.json',
        'Upstream HwResetSystemLib class declaration warning remains'])
if args.full_loader:
    profile=json.loads((root/'out/lmi-loader/manifest.json').read_text())
    report['loader_sha256']=profile['sha256']
    report['kernel_execution_enabled']=profile['kernel_execution_enabled']
    report['permitted_checkpoints']=profile['permitted_checkpoints']
    report['kernel_memory_floor']=profile.get('kernel_memory_floor','0x0')
(out / 'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
