"""Read-only diagnosis of ELF reconstruction differences."""
from pathlib import Path
import struct,json
root=Path(__file__).resolve().parents[1]
def elf(path):
    b=path.read_bytes();at=struct.unpack_from('<Q',b,40)[0];size,count,ns=struct.unpack_from('<HHH',b,58)
    hs=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*size) for i in range(count)]
    names=b[hs[ns][4]:hs[ns][4]+hs[ns][5]]
    return {names[s[0]:names.index(b'\0',s[0])].decode():(s[3],b[s[4]:s[4]+s[5]]) for s in hs if s[0] and s[2]&2 and s[5]}
a=elf(Path('/root/hackios-lmi/out/lmi-display-runtime-v41/touch-relocated.elf'))
b=elf(root/'out/lmi-gpu-async-v58/baseline.elf')
rows=[]
for n,(address,data) in a.items():
    other=b[n];diff=[i for i in range(min(len(data),len(other[1]))) if data[i]!=other[1][i]]
    rows.append(dict(section=n,old_address=hex(address),new_address=hex(other[0]),old_size=len(data),new_size=len(other[1]),
        differences=len(diff),first_offsets=[hex(v) for v in diff[:20]]))
print(json.dumps(rows,indent=2))
