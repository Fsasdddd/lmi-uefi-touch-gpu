"""Migrate the lmi package into the pinned Mu API for an offline FD build.

Run with Linux Python inside Ubuntu. No phone access or boot-image creation.
"""
from pathlib import Path
import json
import re
import shutil
import sys
import hashlib
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--patched', action='store_true', help='Use the reviewed local five-module patch set')
parser.add_argument('--usb-probe', action='store_true', help='Embed the transport-only USB diagnostic app')
parser.add_argument('--full-loader', action='store_true', help='Embed the guarded full-source lmi loader')
args = parser.parse_args()
assert not (args.usb_probe and args.full_loader)

project = Path(__file__).resolve().parents[1]
mu = Path.home() / 'hackios-lmi/mu-silicium'
target = mu / 'Platforms/Xiaomi/lmiPkg'
template = project / 'Mu-Silicium-base/Platforms/Xiaomi/aliothPkg'
firmware = project / 'firmware-extracted/xbl_4/BOOT.XF.3.2-00304-SM8250-2'
assert mu.is_dir() and firmware.is_dir()
target.mkdir(parents=True, exist_ok=True)
shutil.copytree(project / 'port-drafts/uefi/Platforms/Xiaomi/lmiPkg/Library',
                target / 'Library', dirs_exist_ok=True)
for name in ('DeviceBuild.py', 'alioth.dec', 'alioth.dsc', 'alioth.fdf',
             'Include/DXE.inc', 'Include/APRIORI.inc'):
    text = (template / name).read_text().replace('alioth', 'lmi')
    if name == 'DeviceBuild.py':
        # lmi's firmware comes from the owner's XBL capture, not the unrelated
        # upstream multi-device binary repository. Do not fetch/replace it.
        text = text.replace('            RequiredSubmodule ("Binaries", True),\n', '')
        # Pinned dependencies are imported by import-mu-dependencies.py. Avoid
        # fetching unrelated OpenSSL interop/fuzz test repositories recursively.
        text = text.replace(', True)', ', False)')
    if name.endswith('.dsc'):
        text = text.replace('7F67CDAE-8312-4ECC-B948-D86C870D04D9',
                            '28F1A3BF-193A-47E3-A7B9-5A435EAAB2EE')
        text = re.sub(r'(SOC_TYPE\s*=\s*)2', r'\g<1>0', text)
        start = text.index('!if $(DEVICE_MODEL) == 0')
        end = text.index('!endif', start) + len('!endif')
        text = text[:start] + '''  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"Redmi K30 Pro"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"lmi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"lmi"''' + text[end:]
        # XNU receives a generated Apple-style DT, not alioth's Windows ACPI.
        text = text[:text.index('[Components]')]
    if name.endswith('.fdf'):
        text = re.sub(r'  INF (?:RuleOverride = ACPITABLE )?lmi/AcpiTables.inf\n', '', text)
    output = target / name.replace('alioth', 'lmi')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
(target / 'Include/RAW.inc').write_text(
    '# SimpleFbDxe inherits the bootloader display; custom panel XML is omitted.\n')

# Device binaries are kept byte-for-byte as extracted. Required runtime patches
# must be reviewed separately; an FD build does not validate these modules.
shutil.copytree(firmware, mu / 'Binaries/lmi', dirs_exist_ok=True)
if args.patched:
    patch_root = project / 'out/lmi-firmware-patched'
    patch_report = json.loads((patch_root / 'manifest.json').read_text())
    for patch in patch_report['patches']:
        original = firmware / patch['path']
        candidate = patch_root / patch['path']
        assert hashlib.sha256(original.read_bytes()).hexdigest() == patch['original_sha256']
        assert hashlib.sha256(candidate.read_bytes()).hexdigest() == patch['patched_sha256']
        shutil.copy2(candidate, mu / 'Binaries/lmi' / patch['path'])
missing = []
for path in (target / 'Include').glob('*.inc'):
    for relative in re.findall(r'Binaries/lmi/([^\s]+)', path.read_text()):
        if not (mu / 'Binaries/lmi' / relative).is_file():
            missing.append(relative)
assert not missing, missing

loader_source = project / 'hackios/uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib'
loader_target = mu / 'Silicon/Silicium/SiliciumPkg/Library/BootManagerLib'
for name in ('XnuLoader.c', 'XnuLoader.h'):
    shutil.copy2(loader_source / name, loader_target / name)
shutil.copy2(project / 'port-drafts/uefi/XnuLoader-lmi-diagnostics.c', loader_target / 'XnuLoader.c')
if args.usb_probe or args.full_loader:
    assert args.patched
    probe=project/('out/lmi-loader' if args.full_loader else 'out/lmi-usb-probe')
    probe_meta=json.loads((probe/'manifest.json').read_text())
    assert hashlib.sha256((probe/probe_meta.get('application','probe.efi')).read_bytes()).hexdigest()==probe_meta['sha256']
    shutil.copy2(probe/'XnuLoader-lmi-usb-probe.c',loader_target/'XnuLoader.c')
    shutil.copy2(probe/'LmiUsbProbe.h',loader_target/'LmiUsbProbe.h')
inf_path = loader_target / 'BootManagerLib.inf'
inf = inf_path.read_text()
if '  UefiLib\n' not in inf:
    inf = inf.replace('[LibraryClasses]\n', '[LibraryClasses]\n  UefiLib\n')
if '  gEfiUsbFunctionIoProtocolGuid\n' not in inf:
    inf += '\n  gEfiUsbFunctionIoProtocolGuid\n'
inf_path.write_text(inf)

# No boot_image or payload stanza: build_uefi.py stops at the UEFI FD.
(mu / 'Resources/Configs/lmi.toml').write_text('''# Offline compilation profile. Hardware validation is pending.
[status]
model_count = 1
[uefi_fd]
base = 0x9fc00000
size = 0x300000
''')
report = dict(source=str(mu), soc='SM8250', soc_type=0,
              firmware_source=str(firmware), firmware_binary_patches_applied=args.patched,
              acpi_device_tables_included=False, boot_image_generation=False,
              entry_mode='Guarded lmi loader USB bring-up' if args.full_loader else 'RAM-only USB transport diagnostic' if args.usb_probe else 'lmi console diagnostics; no payload launch or raw partition log writes',
              hardware_validated=False, missing_firmware_paths=missing)
(project / 'out/lmi-uefi-staging.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
