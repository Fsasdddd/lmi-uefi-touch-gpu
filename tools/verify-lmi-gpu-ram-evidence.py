"""Replay current RAM assertions against frozen evidence, never touch USB.
Writes a separate report and leaves the original hardware verdict intact.
"""
from pathlib import Path
import ast,hashlib,json,re,struct,sys,zlib
root=Path(__file__).resolve().parents[1]
evidence=Path(sys.argv[1]).resolve()
result=json.loads((evidence/"hardware-test.json").read_text())
kernel_meta=json.loads((evidence/"diagnostic-kernel/manifest.json").read_text())
assert kernel_meta["lmi_gpu_ram_plan"]["enabled"]
profile=dict(lmi_gpu_ram_plan=True,lmi_gpu_ram_hfi=kernel_meta.get("lmi_gpu_ram_hfi",{}).get("enabled",False))
log=(evidence/"checkpoint-63.log").read_text(errors="strict")
source=root/"tools/test-lmi-checkpoints.py"
tree=ast.parse(source.read_text())
blocks=[n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=="label == 'checkpoint-63' and profile.get('lmi_gpu_ram_plan')"]
assert len(blocks)==1
exec(compile(ast.Module(body=blocks[0].body,type_ignores=[]),str(source),"exec"))
assert "LMI_RAM_ONLY_TIMER_EXPIRED"+chr(10) in log
assert "=== 36 checks, 0 failed ===" in log and "panic(cpu" not in log
returned=json.loads((evidence/"android-return.json").read_text())
assert returned["android_boot_completed"]
assert all(returned["original_partition_hashes_match"].values())
report=dict(result="PASS: frozen RAM/HFI assertions and Android return",original_verdict=result.get("result"),
    log_sha256=hashlib.sha256((evidence/"checkpoint-63.log").read_bytes()).hexdigest(),
    verifier_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),gpu_ram_plan=result["gpu_ram_plan"],
    android_return=returned,hardware_acceleration_verified=False)
target=evidence/"ram-evidence-replay.json"
assert not target.exists(), "Preserve previous replay report"
target.write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
