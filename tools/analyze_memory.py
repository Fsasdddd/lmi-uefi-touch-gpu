"""Inspect memory regions from the captured FDT; never selects a boot address."""
import contextlib
import io
import json
from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):
    nodes = runpy.run_path(str(root / "tools/inspect_dtb.py"))["nodes"]


def cell_count(path, name, default):
    raw = nodes.get(path, {}).get(name)
    return int.from_bytes(raw, "big") if raw else default


def registers(path, props):
    parent = path.rsplit("/", 1)[0] or "/"
    ac = cell_count(parent, "#address-cells", 2)
    sc = cell_count(parent, "#size-cells", 1)
    raw = props.get("reg", b"")
    stride = 4 * (ac + sc)
    if not stride or len(raw) % stride:
        raise ValueError(f"Unexpected reg encoding: {path}")
    return [(int.from_bytes(raw[i:i + 4 * ac], "big"),
             int.from_bytes(raw[i + 4 * ac:i + stride], "big")) for i in range(0, len(raw), stride)]


regions = []
for path, props in nodes.items():
    is_memory = path == "/memory" or path.startswith("/memory@")
    if is_memory or path.startswith("/reserved-memory/"):
        for start, size in registers(path, props):
            regions.append({"path": path, "start": hex(start), "size": hex(size),
                            "end_exclusive": hex(start + size), "kind": "ram" if is_memory else "reserved",
                            "status": props.get("status", b"okay").rstrip(b"\0").decode(errors="replace")})
report = {"regions": regions, "candidate_checks": {}}
for name, start, size in (("historical_lmi_uefi_fd", 0x9FC00000, 0x300000),
                          ("upstream_redwood_payload_candidate_ONLY", 0xF0000000, 0x4000000)):
    overlaps = [r for r in regions if r["kind"] == "reserved" and start < int(r["end_exclusive"], 16) and int(r["start"], 16) < start + size]
    in_ram = any(r["kind"] == "ram" and int(r["start"], 16) <= start and start + size <= int(r["end_exclusive"], 16) for r in regions)
    report["candidate_checks"][name] = {"start": hex(start), "size": hex(size), "inside_dt_ram": in_ram,
        "reserved_overlaps": overlaps, "boot_safe": "UNVERIFIED: DT alone cannot establish firmware/shim/loader ownership"}
(root / "device-info/memory-regions.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report["candidate_checks"], indent=2))
print(f"Decoded {len(regions)} RAM/reserved regions")
