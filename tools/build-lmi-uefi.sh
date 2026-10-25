#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mu_root="$HOME/hackios-lmi/mu-silicium"
source "$HOME/hackios-lmi/mu-venv/bin/activate"
cd "$mu_root"
# The HackiOS UEFI README supports using distribution NASM instead of NuGet.
nasm_dir=Mu_Basecore/BaseTools/Bin/mu_nasm_extdep
mkdir -p "$nasm_dir/Linux-x86-64"
printf 'version: 20016.1.1\n' > "$nasm_dir/extdep_state.yaml"
ln -sf /usr/bin/nasm /usr/bin/ndisasm "$nasm_dir/Linux-x86-64/"
nasm -v > "$project_root/out/lmi-nasm-provenance.txt"
python Platforms/Xiaomi/lmiPkg/DeviceBuild.py --update -t RELEASE
# Do not use -u: all repositories must stay at their pinned commits.
python build_uefi.py -d lmi -r RELEASE
