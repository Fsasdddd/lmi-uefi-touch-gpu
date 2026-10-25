"""Stage lmi's historical platform libraries against the pinned modern Mu API.

This does not install/register a platform or create any boot image.
"""
from pathlib import Path
import json
import re

root = Path(__file__).resolve().parents[1]
old = root / "Mu-Silicium-v3.0/Platforms/Xiaomi/lmiPkg/Library"
modern = root / "Mu-Silicium-base/Platforms/Xiaomi/aliothPkg/Library"
out = root / "port-drafts/uefi/Platforms/Xiaomi/lmiPkg/Library"
counts = {}
for old_name, new_name, ctype, array, function, argument in (
    ("DeviceMemoryMapLib", "MemoryMapLib", "EFI_MEMORY_REGION_DESCRIPTOR", "gMemoryDescriptor", "GetMemoryMap", "MemoryDescriptor"),
    ("DeviceConfigurationMapLib", "ConfigurationMapLib", "EFI_CONFIGURATION_ENTRY_DESCRIPTOR", "gConfigurationDescriptor", "GetConfigurationMap", "ConfigurationDescriptor"),
):
    original = (old / old_name / (old_name + ".c")).read_text()
    entries = []
    for line in original.splitlines():
        stripped = line.strip()
        if not stripped.startswith('{"') or stripped.startswith('{"Terminator"'):
            continue
        entries.append("  " + stripped.rstrip(",") + ",")
    assert entries, old_name
    if new_name == "MemoryMapLib":
        # The old descriptive comment is inaccurate; both actual struct definitions
        # use HobOption, ResourceType, ResourceAttribute, MemoryType, ArmAttributes.
        expected_fields = ["Name", "Address", "Length", "HobOption", "ResourceType", "ResourceAttribute", "MemoryType", "ArmAttributes"]
        for library_root, header_name in ((root / "Mu-Silicium-v3.0", "DeviceMemoryMapLib"), (root / "Mu-Silicium-base", "MemoryMapLib")):
            header = (library_root / f"Silicon/Silicium/SiliciumPkg/Include/Library/{header_name}.h").read_text()
            body = re.search(r"typedef struct \{(.*?)\}", header, re.S).group(1)
            names = re.findall(r"\b(\w+)(?:\[[^]]+\])?;", body)
            assert names == expected_fields, (header_name, names)
    assert len(entries) < 128
    counts[new_name] = len(entries)
    target = out / new_name
    target.mkdir(parents=True, exist_ok=True)
    source = f'''/* SPDX-License-Identifier: BSD-2-Clause */
/* Adapted from Mu-Silicium v3.0 lmiPkg. UNBUILT bring-up draft.
 * Values preserve the historical lmi map; firmware/runtime validation is pending.
 * New API uses an explicit count instead of a Terminator sentinel.
 */
#include <Library/{new_name}.h>

STATIC
{ctype}
{array}[] = {{
''' + "\n".join(entries) + f'''
}};

VOID
{function} (
  OUT {ctype} **{argument},
  OUT UINT8 *{argument}Count)
{{
  *{argument} = {array};
  *{argument}Count = ARRAY_SIZE ({array});
}}
'''
    (target / (new_name + ".c")).write_text(source, encoding="utf-8")
    inf = (modern / new_name / (new_name + ".inf")).read_text()
    guid = {"MemoryMapLib": "55F72038-82FA-4B18-9899-B66C72683E29", "ConfigurationMapLib": "35E23AC6-03C4-42F0-9F67-BC2C435FFCF0"}[new_name]
    inf = re.sub(r"(?m)^(\s*FILE_GUID\s*=\s*).*$", lambda m: m.group(1) + guid, inf)
    (target / (new_name + ".inf")).write_text(inf, encoding="utf-8")
(out.parents[4] / "library-migration.json").write_text(json.dumps({"counts": counts, "compiled": False,
    "installed_in_source_tree": False, "hardware_validated": False}, indent=2), encoding="utf-8")
print("Staged unbuilt lmi library migration:", counts)
