"""Temporary-boot the guarded lmi loader and verify RAM/USB only; no flashing."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import struct
import subprocess
import time
import zlib

root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-loader-test'
meta=json.loads((out/'manifest.json').read_text())
image=out/'lmi-diagnostics.img'
assert meta['full_source_loader'] and hashlib.sha256(image.read_bytes()).hexdigest()==meta['sha256']
profile=json.loads((root/'out/lmi-loader/manifest.json').read_text())
assert not profile['persistent_storage_writes'] and not profile['kernel_execution_enabled']
adb=['D:/Gaoji/adb.exe','-s','YOUR_ADB_SERIAL']
fb=['D:/Gaoji/fastboot.exe']
records=[]
result=dict(started=datetime.datetime.now().astimezone().isoformat(),image_sha256=meta['sha256'],records=records)

def run(args,timeout=12,check=True):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    record=dict(command=args,returncode=p.returncode,output=p.stdout+p.stderr)
    records.append(record)
    print(p.stdout+p.stderr,flush=True)
    if check and p.returncode:raise RuntimeError(record)
    return p.stdout+p.stderr

try:
    assert run(adb+['shell','getprop','ro.product.device']).strip()=='lmi'
    run(adb+['reboot','bootloader'])
    for i in range(20):
        p=subprocess.run(fb+['devices'],capture_output=True,text=True,timeout=6)
        if 'YOUR_ADB_SERIAL' in p.stdout:break
        time.sleep(1)
    else:raise RuntimeError('lmi bootloader did not enumerate')
    for key,value in [('product','product: lmi'),('unlocked','unlocked: yes')]:
        assert value in run(fb+['-s','YOUR_ADB_SERIAL','getvar',key])
    run(fb+['-s','YOUR_ADB_SERIAL','boot',str(image)],timeout=45)
    for i in range(25):
        p=subprocess.run(fb+['devices'],capture_output=True,text=True,timeout=6)
        if 'xnuloader' in p.stdout:break
        time.sleep(1)
    else:raise RuntimeError('loader USB did not enumerate; phone should auto-reset')
    target=fb+['-s','xnuloader']
    assert 'product: lmi-xnuloader-readonly' in run(target+['getvar','product'])
    result['platform']=run(target+['getvar','platform'])
    assert 'platform: lmi' in result['platform']
    result['payload_base']=run(target+['getvar','payload-base'])
    result['screen']=run(target+['getvar','screen'])
    run(target+['oem','memmap'])
    run(target+['oem','log'])
    run(target+['get_staged',str(out/'loader-before-download.log')])
    # Deterministic 512 KiB data, wrapped in a valid XNUP container. No kernel.
    data=bytes(range(256))*2048
    body=struct.pack('<16sII',b'check',len(data),0)+data+bytes(24)
    payload=struct.pack('<II',0x50554e58,len(body))+body
    (out/'ram-transfer-check.bin').write_bytes(payload)
    run(target+['stage',str(out/'ram-transfer-check.bin')])
    text=run(target+['getvar','payload-crc32'])
    got=int(re.search(r'payload-crc32:\s*([0-9a-fA-F]+)',text)[1],16)
    expected=zlib.crc32(payload)&0xffffffff
    assert got==expected,(hex(got),hex(expected))
    result['ram_transfer']=dict(bytes=len(payload),crc32=hex(got),verified=True)
    rejected=run(target+['oem','run'],check=False)
    assert 'kernel execution disabled' in rejected
    result['kernel_execution_guard_verified']=True
    run(target+['oem','log'])
    run(target+['get_staged',str(out/'loader-after-download.log')])
    result['result']='PASS: complete-source lmi loader USB/RAM bring-up; no kernel execution'
except Exception as e:
    result['result']='INCOMPLETE'
    result['error']=str(e)
    print('Test stopped:',e,flush=True)
finally:
    (out/'hardware-test.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        p=subprocess.run(fb+['-s','xnuloader','getvar','product'],capture_output=True,text=True,timeout=3)
        if 'product: lmi-xnuloader-readonly' in p.stdout+p.stderr:
            run(fb+['-s','xnuloader','reboot'])
    except subprocess.TimeoutExpired:
        pass
print(result['result'],flush=True)
