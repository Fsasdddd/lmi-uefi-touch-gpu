"""Decode the measured lmi GOP BGRX framebuffer into a lossless PNG."""
from pathlib import Path
import argparse,binascii,struct,zlib

p=argparse.ArgumentParser()
p.add_argument('raw',type=Path)
a=p.parse_args()
width,height,stride=1080,2400,4320
b=a.raw.read_bytes()
assert len(b)==stride*height
rows=[]
for y in range(height):
    row=b[y*stride:y*stride+width*4]
    rgb=bytearray(width*3)
    rgb[0::3]=row[2::4];rgb[1::3]=row[1::4];rgb[2::3]=row[0::4]
    rows.append(b'\0'+rgb)
def chunk(name,data):
    return struct.pack('>I',len(data))+name+data+struct.pack('>I',binascii.crc32(name+data)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))
png+=chunk(b'IDAT',zlib.compress(b''.join(rows),6))+chunk(b'IEND',b'')
dest=a.raw.with_suffix('.png');dest.write_bytes(png)
print(dest)
