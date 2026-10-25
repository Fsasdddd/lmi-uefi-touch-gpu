"""Read Android recovery evidence without clearing logs or writing to device."""
from pathlib import Path
from datetime import datetime
import hashlib,json,shlex,subprocess

r=Path(__file__).resolve().parents[1]
out=r/'out'/('lmi-v20-android-recovery-logs-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir()
adb=['D:/Gaoji/adb.exe','-s','YOUR_ADB_SERIAL','exec-out']
records={}
def collect(name,command,root=False,timeout=25):
    argv=adb+(['su','-c',command] if root else ['sh','-c',command])
    try:
        p=subprocess.run(argv,capture_output=True,timeout=timeout)
        data=p.stdout;error=p.stderr;code=p.returncode
    except subprocess.TimeoutExpired as exc:
        data=exc.stdout or b'';error=exc.stderr or b'';code='timeout'
    (out/name).write_bytes(data)
    if error:(out/(name+'.stderr')).write_bytes(error)
    records[name]=dict(command=command,root=root,returncode=code,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),stderr=error.decode(errors='replace')[:1500])
    (out/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
    print(f'{name}: status={code}, bytes={len(data)}',flush=True)
    return data

collect('boot-completed.txt','getprop sys.boot_completed')
collect('boot-identity.txt','cat /proc/sys/kernel/random/boot_id /proc/uptime /proc/version')
collect('properties.txt','getprop')
digests=collect('partition-digests.txt','sha256sum /dev/block/by-name/boot /dev/block/by-name/dtbo',root=True).decode()
expected={'boot':'ab6a887047f7f169bf2fc3e95e23dca929ba87ab4749d725e9bd4ebc4a38f662','dtbo':'41d5aa69150b084504081e6e4234317d8c8d1179e31b66e532eff0276b6c21e1'}
assert all(value in digests for value in expected.values()),'Original partition hashes differ or unavailable'
collect('dmesg.txt','dmesg',root=True)
collect('logcat-all.txt','logcat -b all -d -v threadtime',root=True,timeout=45)
collect('last-kmsg.txt','cat /proc/last_kmsg',root=True)
files=collect('pstore-files.txt','find /sys/fs/pstore -maxdepth 1 -type f -print',root=True).decode().splitlines()
(out/'pstore').mkdir()
for name in files:
    p=Path(name)
    assert name.startswith('/sys/fs/pstore/') and '/' not in name[len('/sys/fs/pstore/'):]
    collect('pstore/'+p.name,'cat '+shlex.quote(name),root=True)
collect('persistent-log-list.txt','ls -la /sys/fs/pstore /data/vendor/ramdump /data/vendor/ssrdump /data/misc/bootstat',root=True)
collect('input-state.txt','dumpsys input',root=True)
summary=dict(android_boot_completed=(out/'boot-completed.txt').read_text().strip()=='1',
    original_partition_hashes_match={key:value in digests for key,value in expected.items()},
    pstore_file_count=len(files),collection_read_only=True,logs_cleared=False,
    ios_ram_log_recovered=False,output=str(out))
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
