"""Resolve bounded ustacks evidence with the verified ipsw tool (WSL only)."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
log = Path(sys.argv[1]).resolve()
out = log.parent / 'ustacks-symbolized.json'
tool = repo / 'out/ipsw-tools/v3.1.739/ipsw'
cache = repo / 'out/ipsw-tools/cache-ios165/dyld_shared_cache_arm64'
assert hashlib.sha256(tool.read_bytes()).hexdigest() == '7f22f07821cd964c0333172ef9bac734b53df5035a5e7c8ce9ec1580891f6d4c'
assert not out.exists(), 'Keep completed evidence immutable'
snapshots = []
symbols = {}
for n, line in enumerate(log.read_text(errors='replace').splitlines(), 1):
    header = re.search(r'ustacks: (\S+)\[(\d+)\] (\d+) threads, shared cache slide (0x[0-9a-f]+)', line)
    if header:
        snapshot = dict(line=n, header=line, process=header[1], pid=int(header[2]),
                        slide=header[4], threads=[])
        snapshots.append(snapshot)
        continue
    thread = re.search(r'ustacks:  thread (0x[0-9a-f]+)(.*?): (.*)', line)
    if not thread:
        continue
    assert snapshots
    frames = []
    for address in re.findall(r'0x[0-9a-f]+', thread[3]):
        unslid = hex(int(address, 16) - int(snapshot['slide'], 16))
        if unslid not in symbols:
            if not 0x180000000 <= int(unslid, 16) < 0x280000000:
                symbols[unslid] = dict(stdout='Outside shared cache: ' + address, stderr='', returncode=0)
            else:
                p = subprocess.run([str(tool), 'dyld', 'a2s', '--image', str(cache), unslid],
                                   capture_output=True, text=True, timeout=60)
                symbols[unslid] = dict(stdout=p.stdout, stderr=p.stderr, returncode=p.returncode)
                print(unslid, p.stdout.strip().splitlines()[-1:] or p.stderr[:150], flush=True)
        frames.append(dict(runtime=address, unslid=unslid))
    snapshot['threads'].append(dict(line=n, raw=line, tid=thread[1], name=thread[2], frames=frames))
assert snapshots, 'No ustacks records'
out.write_text(json.dumps(dict(log=str(log), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
                               snapshots=snapshots, symbols=symbols), indent=2) + '\n')
text = []
for snapshot in snapshots:
    text.append(snapshot['header'])
    for thread in snapshot['threads']:
        text.append(thread['raw'])
        for i, frame in enumerate(thread['frames']):
            # Keep the usually stale LR in JSON; omit it from the readable frame chain.
            if i == 1:
                continue
            sym = symbols[frame['unslid']]
            text.append(sym['stdout'].strip() or sym['stderr'].strip())
(log.parent / 'ustacks-symbolized.txt').write_text('\n\n'.join(text) + '\n')
