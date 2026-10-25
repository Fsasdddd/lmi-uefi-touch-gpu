"""Generate a non-bootable platform draft from captured DT properties."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dt = json.loads((root / "device-info/dt-summary.json").read_text())
cpus = [(int(path.rsplit("@", 1)[1], 16), int(props["capacity-dmips-mhz"].replace(" ", ""), 16))
        for path, props in dt.items() if path.startswith("/cpus/cpu@") and path.count("/") == 2]
assert len(cpus) == 8
shift = 8 if any(reg >= 0x100 for reg, _ in cpus) else 0
small = sum(1 << (reg >> shift) for reg, capacity in cpus if capacity == min(c for _, c in cpus))
gic = dt["/soc/interrupt-controller@17a00000"]
cells = [int.from_bytes(bytes.fromhex(gic["reg"])[i:i + 4], "big") for i in range(0, 16, 4)]
assert len(cells) == 4 and dt["/psci"]["method"] == "smc"
out = root / "port-drafts"
out.mkdir(exist_ok=True)
(out / "lmi.platform.c").write_text(f'''/* DRAFT ONLY. Not integrated into the loader. */
/* GIC, CPU numbering and capacity mask come from the captured live DT. */
/* IO mapping is an upstream template candidate; framebuffer is UNKNOWN. */
static const struct platform platform_lmi = {{
    .name = "lmi",
    .io_base = 0x00400000, .io_size = 0x3FC00000, /* TODO: review Kona MMIO coverage */
    .gic_dist = {cells[0]:#x}, .gic_redist = {cells[2]:#x},
    .uart = 0, .psci_hvc = 0,
    .log_other_cpu = 1,
    .cores = {len(cpus)}, .core_shift = {shift},
    .small_cores = {small:#x},
    .fb_base = 0, /* UNKNOWN: obtain actual GOP base from lmi UEFI; do not register yet */
}};
''', encoding="utf-8")
(out / "lmi.conf").write_text('''# DRAFT ONLY. Resolve the boot prerequisites before installing this profile.
# Guard deliberately prevents common/build.sh and common/run.sh from using it.
die "lmi is not boot-ready: UEFI migration, payload reservation and GOP base are unresolved"
NAME="Redmi K30 Pro (lmi)"
KIND=phone
SOC="Qualcomm SM8250"
UEFI_TARGET=lmi
UEFI_FD=TODO_LMI_BUILT_FD
DTB=../device-info/live.dtb
# Historical lmi v3.0 values; must be checked against the migrated port.
FD_BASE=0x9FC00000
FD_SIZE=0x300000
PAYLOAD_BASE=TODO_RESERVE_AND_VALIDATE
FB_BASE=TODO_MEASURE_GOP
WIFI_ATH11K=0
# First milestone is single-core framebuffer boot, without touch/GPU/radios.
BOOTARGS="-v cpus=1"
DEFAULT_SECS=60
USERLAND_VARS=""
FIRMWARE=""
''', encoding="utf-8")
print(f"Generated non-bootable lmi drafts: {len(cpus)} cores, shift {shift}, small mask {small:#x}")
