"""Decode the captured FDT without requiring dtc on Windows."""
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1] / "device-info"
data = (ROOT / "live.dtb").read_bytes()
magic, total, off_struct, off_strings, _, _, _, _, strings_size, struct_size = struct.unpack_from(">10I", data)
assert magic == 0xD00DFEED and total <= len(data)
strings = data[off_strings:off_strings + strings_size]
pos = off_struct
end = off_struct + struct_size
stack = []
nodes = {}
lines = ["/dts-v1/;", "// Decoded from live.dtb; property values are preserved as raw bytes."]
while pos < end:
    token = struct.unpack_from(">I", data, pos)[0]
    pos += 4
    if token == 1:
        stop = data.index(0, pos)
        name = data[pos:stop].decode()
        pos = (stop + 4) & ~3
        lines.append("    " * len(stack) + (name or "/") + " {")
        stack.append(name)
        nodes["/" + "/".join(stack[1:])] = {}
    elif token == 2:
        stack.pop()
        lines.append("    " * len(stack) + "};")
    elif token == 3:
        length, nameoff = struct.unpack_from(">II", data, pos)
        pos += 8
        value = data[pos:pos + length]
        pos = (pos + length + 3) & ~3
        name = strings[nameoff:strings.index(0, nameoff)].decode()
        path = "/" + "/".join(stack[1:])
        nodes[path][name] = value
        lines.append("    " * len(stack) + name + (" = [" + value.hex(" ") + "]" if value else "") + ";")
    elif token == 4:
        continue
    elif token == 9:
        break
    else:
        raise ValueError(f"Unexpected FDT token {token} at {pos - 4}")
(ROOT / "live.dts").write_text("\n".join(lines) + "\n", encoding="utf-8")
selected = {}
for path, props in nodes.items():
    comp = props.get("compatible", b"").replace(b"\0", b" ").decode(errors="replace")
    if path == "/" or path.startswith("/cpus/") or path.startswith("/memory") or any(
        term in (path + " " + comp).lower() for term in ("fts", "focal", "touch", "interrupt-controller", "psci", "framebuffer", "kgsl", "adreno", "dsi-panel")):
        selected[path] = {}
        for name, value in props.items():
            if name in ("compatible", "model", "status", "method", "qcom,mdss-dsi-panel-name"):
                selected[path][name] = value.rstrip(b"\0").decode(errors="replace").replace("\0", ", ")
            elif name in ("reg", "interrupts", "interrupt-parent", "capacity-dmips-mhz", "device_type", "focaltech,display-coords", "focaltech,reset-gpio", "focaltech,irq-gpio", "focaltech,name"):
                selected[path][name] = value.hex(" ")
(ROOT / "dt-summary.json").write_text(json.dumps(selected, indent=2), encoding="utf-8")
print(f"Decoded {len(nodes)} nodes; saved live.dts and dt-summary.json")
for path, props in selected.items():
    if path == "/" or any(term in path.lower() for term in ("focal", "fts", "interrupt-controller", "psci")):
        print(path, json.dumps(props))
