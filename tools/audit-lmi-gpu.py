"""Read-only Android GPU inventory and live-DT/vendor source audit."""
from pathlib import Path
import hashlib,json,struct,subprocess,urllib.request
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-gpu-hardware';out.mkdir(exist_ok=True)
adb=['D:/Gaoji/adb.exe','-s','YOUR_ADB_SERIAL']
def shell(command):
    return subprocess.check_output([*adb,'shell','su','-c',command],text=True).strip()
assert shell('getprop ro.product.device')=='lmi'
report={'device':'lmi','writes_to_device':False,'firmware':{},'vendor_sources':{}}
for name in ['gpu_model','gpuclk','max_gpuclk','num_pwrlevels','gpubusy','devfreq/available_frequencies']:
    try:report[name]=shell('cat /sys/class/kgsl/kgsl-3d0/'+name)
    except subprocess.CalledProcessError:pass
for name in ['a650_gmu.bin','a650_sqe.fw','a650_zap.mdt','a650_zap.b00','a650_zap.b01','a650_zap.b02','a650_zap.elf']:
    path=out/name
    path.write_bytes(subprocess.check_output([*adb,'exec-out','su','-c','cat /vendor/firmware/'+name]))
    value=path.read_bytes();sha=hashlib.sha256(value).hexdigest()
    remote=shell('sha256sum /vendor/firmware/'+name).split()[0]
    assert remote==sha
    report['firmware'][name]={'bytes':len(value),'sha256':sha,'android_sha256_matches':True}
data=(root/'device-info/live.dtb').read_bytes()
_,_,off,strings_off,_,_,_,_,strings_size,size=struct.unpack_from('>10I',data)
strings=data[strings_off:strings_off+strings_size];stack=[];nodes={};pos=off
while pos<off+size:
    token=struct.unpack_from('>I',data,pos)[0];pos+=4
    if token==1:
        stop=data.index(0,pos);stack.append(data[pos:stop].decode());pos=(stop+4)&~3
        nodes['/'+'/'.join(stack[1:])]={}
    elif token==2:stack.pop()
    elif token==3:
        length,nameoff=struct.unpack_from('>II',data,pos);pos+=8
        name=strings[nameoff:strings.index(0,nameoff)].decode()
        nodes['/'+'/'.join(stack[1:])][name]=data[pos:pos+length];pos=(pos+length+3)&~3
    elif token==9:break
    else:assert token==4
report['dt_sha256']=hashlib.sha256(data).hexdigest()
report['dt']={p:{k:v.hex() for k,v in props.items()} for p,props in nodes.items()
    if any(s in p for s in ['kgsl','gmu@','gpucc','clock-controller@3d9','gpu_speed_bin','pil_gpu_region'])}
gpu=nodes['/soc/qcom,kgsl-3d0@3d00000']
assert gpu['qcom,chipid']==bytes.fromhex('06050002')
assert gpu['qcom,highest-bank-bit']==bytes.fromhex('00000010')
for name,path in {
    'gpucc-kona.c':'drivers/clk/qcom/gpucc-kona.c',
    'gcc-kona.c':'drivers/clk/qcom/gcc-kona.c',
    'adreno_a6xx.c':'drivers/gpu/msm/adreno_a6xx.c',
    'adreno_a6xx_gmu.c':'drivers/gpu/msm/adreno_a6xx_gmu.c',
    'a6xx_reg.h':'drivers/gpu/msm/a6xx_reg.h',
}.items():
    url='https://raw.githubusercontent.com/MiCode/Xiaomi_Kernel_OpenSource/lmi-q-oss/'+path
    b=urllib.request.urlopen(url,timeout=40).read();(out/name).write_bytes(b)
    report['vendor_sources'][name]={'url':url,'sha256':hashlib.sha256(b).hexdigest()}
(out/'hardware-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='dt'},indent=2))
