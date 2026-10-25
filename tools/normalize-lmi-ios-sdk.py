"""Normalize Theos SDK text stubs for LLVM18's TAPI magic recognition."""
from pathlib import Path
import argparse,json
p=argparse.ArgumentParser();p.add_argument('sdk',type=Path);a=p.parse_args()
assert a.sdk.name=='iPhoneOS16.5.sdk' and (a.sdk/'SDKSettings.json').exists()
n=0
for path in a.sdk.rglob('*.tbd'):
    if path.is_symlink():continue
    b=path.read_bytes()
    if b'\r\n' in b:
        assert b.startswith(b'--- !tapi-tbd')
        path.write_bytes(b.replace(b'\r\n',b'\n'));n+=1
print(json.dumps(dict(tapi_stubs_normalized=n,sdk=str(a.sdk))))
