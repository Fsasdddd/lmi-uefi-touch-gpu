#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mu_root="$HOME/hackios-lmi/mu-silicium"
mu_commit=e51cd877e31c8fbb322032dc4cb6715e83d25ad3
if [[ ! -d "$mu_root/.git" ]]; then
    git clone --no-hardlinks "$project_root/Mu-Silicium-v3.0" "$mu_root"
    # The source contains two independent shallow snapshots. Local clone copies
    # their objects but only records shallow boundaries reachable from refs.
    if [[ -f "$project_root/Mu-Silicium-v3.0/.git/shallow" ]]; then
        cp "$project_root/Mu-Silicium-v3.0/.git/shallow" "$mu_root/.git/shallow"
    fi
    git -C "$mu_root" checkout --detach "$mu_commit"
fi
[[ "$(git -C "$mu_root" rev-parse HEAD)" == "$mu_commit" ]]
patch_file="$project_root/hackios/uefi/mu-silicium.patch"
if git -C "$mu_root" apply --check "$patch_file" 2>/dev/null; then
    git -C "$mu_root" apply "$patch_file"
else
    git -C "$mu_root" apply --reverse --check "$patch_file"
fi
out="$project_root/out/lmi-shim"
mkdir -p "$out"
# Build a component only. Historical FD addresses and payload placement still
# require hardware validation before combining it into a phone boot image.
clang --target=aarch64-linux-gnu -c "$mu_root/BootShim/BootShim.S" \
    -o "$out/BootShim.elf" -DREQUIRES_KERNEL_HEADER=1 \
    -DFD_BASE=0x9fc00000 -DFD_SIZE=0x300000 -DPAYLOAD_BASE=0xf0000000
llvm-objcopy -O binary "$out/BootShim.elf" "$out/BootShim.bin"
llvm-objdump -dr "$out/BootShim.elf" > "$out/disassembly.txt"
python3 - "$out" <<'PY'
import hashlib, json, struct, sys
from pathlib import Path
p = Path(sys.argv[1])
b = (p / 'BootShim.bin').read_bytes()
assert b[56:60] == b'ARM\x64'
assert struct.unpack_from('<QQ', b, 8) == (0x9fc00000, 0x300000)
report = dict(fd_base='0x9fc00000', fd_size='0x300000',
              payload_base='0xf0000000', bytes=len(b),
              sha256=hashlib.sha256(b).hexdigest(),
              upstream_commit='e51cd877e31c8fbb322032dc4cb6715e83d25ad3',
              hardware_tested=False, standalone_boot_image=False)
(p / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
PY
