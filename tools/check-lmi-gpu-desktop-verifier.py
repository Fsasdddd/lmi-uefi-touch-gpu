"""In-memory desktop extensions to real tile evidence, never hardware claims."""
from pathlib import Path
import hashlib,json,re,runpy
r=Path(__file__).resolve().parents[1];e=r/'out/lmi-checkpoint-63-ios-probe-test-a650-tile-seq-mode46-25'
parent=(e/'checkpoint-63.log').read_text();fw=(r/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
window=json.loads((e/'hardware-test.json').read_text())['kernel_window']
m=runpy.run_path(str(r/'tools/verify-lmi-gpu-desktop.py'));verify=m['verify']
tile=runpy.run_path(str(r/'tools/verify-lmi-gpu-tile.py'))['verify'](parent,fw,window)
def rows(marker,values):return marker+'\n'+''.join(f'{v:016x}\n' for v in values)
status=list(re.finditer(r'LMI_GPU_CP_STATUS\n(?:[0-9a-f]{16}\n){14}',parent))[-1][0]
extension=rows('LMI_GPU_DESKTOP_BEGIN',[0x7eabe052])+status+rows('LMI_GPU_DESKTOP_TABLES',tile['core_backing_pages'][17:20])+rows('LMI_GPU_DESKTOP_NC',[((0x3d00000+4*k)<<32)|v for k,v in m['CONFIG']])+rows('LMI_GPU_DESKTOP_BIND_FENCE',[72,0x650c0de4])+rows('LMI_GPU_DESKTOP_READY',[0x6050002,1179648,16,1,2])+rows('LMI_GPU_DESKTOP_RESULT',[1])
at=parent.index('LMI_GPU_CORE_MEMORY_RESULT\n');base=parent[:at]+extension+parent[at:]
assert verify(base,fw,window)['desktop_backend_adopted'] and not verify(base,fw,window)['desktop_acceleration_verified']
complete=rows('LMI_GPU_DESKTOP_COMPLETED',[1,86,1])+rows('LMI_GPU_DESKTOP_COMPLETED',[2,100,2])
sample=base[:at+len(extension)]+complete+base[at+len(extension):]
assert verify(sample,fw,window)['desktop_last_logged_fence']==2
cases={
    'missing desktop':parent,'duplicate desktop':base.replace(extension,extension+extension),
    'wrong canary':base.replace('000000007eabe052','000000007eabe053'),
    'wrong binding fence':base.replace('00000000650c0de4','00000000650c0de3'),
    'wrong binding rptr':base.replace(rows('LMI_GPU_DESKTOP_BIND_FENCE',[72,0x650c0de4]),rows('LMI_GPU_DESKTOP_BIND_FENCE',[71,0x650c0de4])),
    'failed result':base.replace(rows('LMI_GPU_DESKTOP_RESULT',[1]),rows('LMI_GPU_DESKTOP_RESULT',[0])),
    'wrong table':base.replace(rows('LMI_GPU_DESKTOP_TABLES',tile['core_backing_pages'][17:20]),rows('LMI_GPU_DESKTOP_TABLES',tile['core_backing_pages'][16:19])),
    'wrong params':base.replace(rows('LMI_GPU_DESKTOP_READY',[0x6050002,1179648,16,1,2]),rows('LMI_GPU_DESKTOP_READY',[0x6030500,524288,14,0,0])),
    'runtime failure':sample+'LMI_GPU_DESKTOP_FAULT_HELD\n',
    'held release':sample+'LMI_GPU_DESKTOP_RELEASE_HELD\n',
    'wrong completion':sample.replace(rows('LMI_GPU_DESKTOP_COMPLETED',[2,100,2]),rows('LMI_GPU_DESKTOP_COMPLETED',[2,100,1])),
    'reversed fences':sample.replace(complete,rows('LMI_GPU_DESKTOP_COMPLETED',[2,100,2])+rows('LMI_GPU_DESKTOP_COMPLETED',[1,86,1])),
    'malformed completion':sample+'LMI_GPU_DESKTOP_COMPLETED\n',
    'parent pixel CRC':base.replace('00000000f21d9405','00000000f21d9404'),
    'parent normal failure':base.replace(rows('LMI_GPU_NORMAL_RESULT',[1]),rows('LMI_GPU_NORMAL_RESULT',[0])),
    'wrong status snapshot':base.replace(extension,extension.replace('03d0201800000044','03d0201800000043')),
}
for k,v in m['CONFIG']:
    cases['register '+hex(k)]=base.replace(f'{((0x3d00000+4*k)<<32)|v:016x}',f'{((0x3d00000+4*k)<<32)|(v^1):016x}')
ram=re.search(r'LMI_GPU_RAM_SEGMENTS\n((?:[0-9a-f]{16}\n){5})LMI_GPU_RAM_SOFTWARE_WALK_OK\n',base)
assert ram
background='buttons: nothing that can be read: no buttons\n'
interleaved=base.replace(ram[0],ram[0].replace('SEGMENTS\n','SEGMENTS\n'+background))
assert verify(interleaved,fw,window)['interleaved_buttons_records']==1
assert verify(base,fw,window)['interleaved_buttons_records']==0
values=ram[1].splitlines(keepends=True)
bad_records={
    'unknown background':'buttons: unknown failure\n'+ram[1],
    'partial background':background[:-1]+ram[1],
    'altered background':background.upper()+ram[1],
    'duplicate background':background*2+ram[1],
    'missing RAM value':background+''.join(values[:-1]),
    'extra RAM value':background+ram[1]+values[-1],
    'corrupt RAM value':background+'z'+ram[1][1:],
    'split RAM value':ram[1][:8]+background+ram[1][8:],
    'duplicate RAM marker':background+'LMI_GPU_RAM_SEGMENTS\n'+ram[1],
    'GPU failure in RAM record':background+'LMI_GPU_RAM_FAILED\n'+ram[1],
    'wrong RAM CRC':background+f'{int(values[0],16)^1:016x}\n'+''.join(values[1:]),
}
for name,bad in bad_records.items():
    cases[name]=base.replace(ram[0],'LMI_GPU_RAM_SEGMENTS\n'+bad+'LMI_GPU_RAM_SOFTWARE_WALK_OK\n')
for name,changed in cases.items():
    assert changed!=base,name
    try:verify(changed,fw,window)
    except AssertionError:pass
    else:raise AssertionError('Accepted '+name)
names=['lmi-gpu-desktop.c','check-lmi-gpu-desktop.c','lmi-gpu-desktop-profile.py','verify-lmi-gpu-desktop.py','check-lmi-gpu-desktop-verifier.py','check-lmi-gpu-desktop-source.py','audit-lmi-gpu-desktop-region.py','check-lmi-gpu-desktop-region.py']
report=dict(result='PASS',negative_cases=list(cases),synthetic_positive_in_memory_only=True,hardware_verified=False,
    source_sha256={name:hashlib.sha256((r/'tools'/name).read_bytes()).hexdigest() for name in names},
    host_log_sha256=hashlib.sha256((r/'out/lmi-gpu-desktop-host.log').read_bytes()).hexdigest())
assert 'PASS: adoption guards' in (r/'out/lmi-gpu-desktop-host.log').read_text()
(r/'out/lmi-gpu-research/mode46-desktop-offline-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'PASS: desktop adoption/IB parser; {len(cases)} negative cases; tile and normal proof preserved; desktop claim remains false')
