"""Bind the current normal diagnostic sources, offline checks and RX payloads."""
from pathlib import Path
import hashlib,json,re,struct,runpy

r=Path(__file__).resolve().parents[1]
k=r/'out/lmi-kernel-ios-continue';l=r/'out/lmi-loader';im=r/'out/lmi-loader-test'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
km=json.loads((k/'manifest.json').read_text());lm=json.loads((l/'manifest.json').read_text());mm=json.loads((im/'manifest.json').read_text())
assert digest(k/'mach.development.bcm2837')==km['sha256']
assert digest(l/'loader.efi')==lm['sha256']==mm['loader_sha256']
assert digest(im/'lmi-diagnostics.img')==mm['sha256']
assert lm['lmi_gpu_unsecure'] and km['lmi_gpu_unsecure']['enabled'] and not lm['persistent_storage_writes']
smp_cpus=lm.get('smp_cpus',1)
fb_threads=lm.get('fb_threads',1)
fb_queue=lm.get('fb_queue',2)
fb_beat=lm.get('fb_beat',1)
assert fb_queue in (1,2) and fb_beat in (0,1)
if lm.get('lmi_gpu_desktop'):
    for key,value in [('fb_queue',fb_queue),('fb_beat',fb_beat)]:
        assert re.findall(rb'\b'+key.encode()+rb'=(\d+)\b',(l/'loader.efi').read_bytes())==[str(value).encode()]
    assert lm['desktop_framebuffer_threads']==fb_threads
assert 1<=fb_threads<=smp_cpus
assert re.findall(rb'\bfb_threads=(\d+)\b',(l/'loader.efi').read_bytes())==([str(fb_threads).encode()] if lm.get('lmi_gpu_desktop') else [])
assert smp_cpus==km.get('smp_cpus',1) and smp_cpus in (1,2,4,8)
assert re.findall(rb'\bcpus=(\d+)\b',(l/'loader.efi').read_bytes())==([b'1',str(smp_cpus).encode()] if smp_cpus>1 else [b'1'])
if smp_cpus>1:
    assert lm['smp_gic_sgis_restored'] and km['smp_return']['enabled']
    assert digest(r/km['smp_return']['source'])==km['smp_return']['source_sha256']
    assert km['smp_return']['other_cores_off_required'] and km['smp_return']['unknown_stop_retains_ram']
    smp_check=json.loads((r/'out/lmi-smp-return-host-check.json').read_text())
    assert smp_check['result']=='PASS' and smp_check['positive']==8 and smp_check['refused_return_cases']==280
    assert smp_check['atomic_hex_cases']==84 and smp_check['touch_poll_cases']==6
    assert smp_check['delayed_off_cases']==168 and smp_check['transition_error_cases']==224
    assert smp_check['deadline_frequency_wrap_cases']==40
    assert km['smp_return']['affinity_transition_wait_seconds']==1
    assert km['smp_return']['affinity_transition_states']==[0,2] and km['smp_return']['affinity_wait_shared_deadline']
    assert km['smp_touch_poll_diagnostics'] and km['smp_return']['atomic_hex_lines']
    assert smp_check['kernel_sha256']==km['sha256'] and smp_check['source_sha256']==km['smp_return']['source_sha256']
assert lm['ios_observe_seconds']==25 or (lm.get('lmi_gpu_desktop') and lm['ios_observe_seconds'] in (45,180))
assert re.findall(rb'\blmi_gpu=(\d+)\b',(l/'loader.efi').read_bytes())==[b'46']
for arg,expected in [('touchscreen',b'1'),('lmi_touch',b'6')]:
    assert re.findall(rb'\b'+arg.encode()+rb'=(\d+)\b',(l/'loader.efi').read_bytes())==([expected] if lm.get('lmi_touch_input') else [])
tile=bool(lm.get('lmi_gpu_tile'))
desktop=bool(lm.get('lmi_gpu_desktop'))
assert desktop==bool(km.get('lmi_gpu_desktop',{}).get('enabled')) and (not desktop or tile)
assert re.findall(rb'\blmi_gpu_desktop=(\d+)\b',(l/'loader.efi').read_bytes())==([b'1'] if desktop else [])
assert re.findall(rb'\bfb_threads=(\d+)\b',(l/'loader.efi').read_bytes())==([str(fb_threads).encode()] if desktop else [])
assert tile==bool(km.get('lmi_gpu_tile',{}).get('enabled'))
assert re.findall(rb'\blmi_gpu_tile=(\d+)\b',(l/'loader.efi').read_bytes())==([b'1'] if tile else [])
for key,value in km.items():
    if not isinstance(value,dict) or not value.get('enabled') or not value.get('source_sha256'):
        continue
    src=r/value['source'] if 'source' in value else r/('tools/'+key.replace('lmi_gpu_','lmi-gpu-').replace('_','-')+'.c')
    if src.exists():assert digest(src)==value['source_sha256'],str(src)
raw=(k/'mach.development.bcm2837').read_bytes();pos=32;segments=[]
touch=km.get('lmi_touch_driver',{})
if touch.get('timing_header'):assert digest(r/touch['timing_header'])==touch['timing_header_sha256']
for _ in range(struct.unpack_from('<I',raw,16)[0]):
    cmd,size=struct.unpack_from('<II',raw,pos)
    if cmd==0x19:
        va,vs,fo,fs=struct.unpack_from('<4Q',raw,pos+24);prot=struct.unpack_from('<I',raw,pos+60)[0]
        segments.append((va,fo,fs,prot))
    pos+=size
def at(va,n):
    s=next(s for s in segments if s[0]<=va and va+n<=s[0]+s[2]);assert s[3]==5
    return s[1]+va-s[0]
regions={}
for name in ['unsecure','normal-diag']+(['desktop'] if desktop else []):
    audit=json.loads((k/f'gpu-{name}-region-audit.json').read_text())
    src=r/f'tools/audit-lmi-gpu-{name}-region.py'
    assert audit['result']=='PASS' and audit['segment_initprot']==5
    entry,start,end=[int(audit[key],16) for key in ['entry','start','end']]
    code=(k/f'gpu-{name}.bin').read_bytes()
    assert start==entry+8 and 0<len(code)<=end-start
    assert struct.unpack_from('<II',raw,at(entry,8))==(0x52800000,0xd65f03c0)
    p=at(start,len(code));assert raw[p:p+len(code)]==code
    regions[name]=dict(bytes=len(code),bound=end-start,audit_sha256=digest(src))
    if name=='desktop':
        for slot in audit['table_slots']:assert struct.unpack_from('<Q',raw,int(slot,16))[0]==entry
        profile=runpy.run_path(str(r/'tools/lmi-gpu-desktop-profile.py'))
        symbols={v[2]:int(v[0],16) for line in (r/'out/kernel-symbols.txt').read_text().splitlines() if len(v:=line.split())==3}
        profile['bindings'](symbols)
        linked={m[2]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+) <([^>]+)>:',(k/'touch-disassembly.txt').read_text(),re.M)}
        for symbol,(pc,old,target) in profile['ABI'].items():
            word=struct.unpack_from('<I',raw,at(pc,4))[0];imm=word&0x3ffffff
            if imm&0x2000000:imm-=0x4000000
            assert word&0xfc000000==0x14000000 and pc+4*imm==linked['lmi_desktop_'+target]
            assert start<=pc+4*imm<start+len(code)
offline=json.loads((r/'out/lmi-gpu-research/mode46-diag-offline-validation.json').read_text())
negative=json.loads((r/'out/lmi-gpu-research/normal-diag-region-negative-check.json').read_text())
assert offline['result']==negative['result']=='PASS' and offline['host_scenarios']==44
assert len(offline['negative_cases'])==22 and len(negative['negative_cases'])==6
assert 'PASS:' in (r/'out/lmi-gmu-unsecure-diag-host.log').read_text()
sources=[r/'tools'/s for s in ['lmi-gpu-unsecure.c','check-lmi-gpu-unsecure.c','verify-lmi-gpu-unsecure.py',
    'lmi-gpu-core-memory.c','build-lmi-loader.py','build-lmi-gpu-mode.py',
    'audit-lmi-gpu-normal-diag-region.py','check-lmi-gpu-normal-diag-region.py','check-lmi-gpu-normal-verifier.py','build-lmi-ios-probe.py','test-lmi-checkpoints.py']]
sources += [r/'tools/lmi-gic-guard.c']
sources += [r/'tools/lmi_display_v40_policy.py']
sources += [r/'tools/lmi_display_v41_policy.py']
sources += [r/'tools/lmi_display_v42_policy.py']
if lm.get('display_census'):
    census=r/'tools/lmi-display-census.c'
    assert digest(census)==lm['display_census_source_sha256']
    check=json.loads((r/'out/lmi-display-census-host/result.json').read_text())
    assert check['result']=='PASS' and check['source_sha256']==digest(census)
    sources += [census,r/'tools/check-lmi-display-census.py']
if smp_cpus>1:sources += [r/'tools/lmi-smp-return.S',r/'tools/check-lmi-smp-return.py']
if tile:
    tr=json.loads((r/'out/lmi-gpu-research/mode46-tile-offline-validation.json').read_text())
    ts=json.loads((r/'out/lmi-gpu-research/mode46-tile-source-audit.json').read_text())
    assert tr['result']==ts['result']=='PASS' and tr['host_scenarios']==35 and len(tr['negative_cases'])==72
    for name,sha in tr['source_sha256'].items():assert digest(r/'tools'/name)==sha,name
    assert digest(r/'tools/lmi-gpu-tile.c')==ts['gpu_tile_source_sha256']
    assert digest(r/'tools/verify-lmi-gpu-tile.py')==ts['verifier_sha256']
    assert digest(r/'out/lmi-gpu-tile-host.log')==tr['host_log_sha256']
    sources += [r/'tools'/s for s in ['lmi-gpu-tile.c','check-lmi-gpu-tile.c','verify-lmi-gpu-tile.py',
        'check-lmi-gpu-tile-source.py','check-lmi-gpu-tile-verifier.py']]
if desktop:
    dr=json.loads((r/'out/lmi-gpu-research/mode46-desktop-offline-validation.json').read_text())
    ds=json.loads((r/'out/lmi-gpu-research/mode46-desktop-source-audit.json').read_text())
    dn=json.loads((r/'out/lmi-gpu-research/desktop-region-negative-check.json').read_text())
    assert dr['result']==ds['result']==dn['result']=='PASS' and len(dr['negative_cases'])==40 and len(dn['negative_cases'])==11
    for name,sha in dr['source_sha256'].items():assert digest(r/'tools'/name)==sha,name
    assert digest(r/'tools/lmi-gpu-desktop.c')==ds['source_sha256']
    assert digest(r/'out/lmi-gpu-desktop-host.log')==dr['host_log_sha256']
    sources += [r/'tools'/name for name in dr['source_sha256']]
    sources += [r/'tools'/name for name in ['verify-lmi-gpu-gl.py','check-lmi-gpu-gl-verifier.py','lmi-gpu-gl-probe.c']]
# Bind the full original RX padding, including fixed canary pages and aux.
for name,base,limit in [('boot',0xfffffff007adc200,0xfffffff007ae0000),
                       ('context',0xfffffff0074d4c4c,0xfffffff0074d59c4)]:
    code=(k/f'gpu-{name}.bin').read_bytes();assert 0<len(code)<=limit-base
    p=at(base,len(code));assert raw[p:p+len(code)]==code
    regions[name]=dict(bytes=len(code),bound=limit-base)
assert lm.get('lmi_cpu_requests')==2
assert re.findall(rb'\blmi_cpu=(\d+)\b',(l/'loader.efi').read_bytes())==[b'2']
sources += [r/'tools/build-lmi-loader-v77.py',r/'tools/check-lmi-gpu-normal-preflight-v77.py']
report=dict(result='PASS',mode=46,kernel_sha256=km['sha256'],loader_sha256=lm['sha256'],diagnostic_sha256=mm['sha256'],
    regions=regions,source_sha256={str(p.relative_to(r)):digest(p) for p in sources},
    snapshot_readonly=True,nonsecure_address_mode_writes=10,sp_force_exact_readback_required=True,
    disabled_hwcg_requires_zero_clock_control_and_SP_GX_on=True,host_scenarios=44,tile=tile,desktop=desktop,hardware_verified=False)
report['ios_observe_seconds']=lm['ios_observe_seconds']
report['touch_input_enabled']=bool(lm.get('lmi_touch_input'))
report['smp_cpus']=smp_cpus
report['fb_threads']=fb_threads
report['fb_queue']=fb_queue
report['fb_beat']=fb_beat
report['display_census']=bool(lm.get('display_census'))
if tile:report.update(tile_host_scenarios=35,tile_verifier_negative_cases=72)
(r/('out/lmi-gpu-research/mode46-desktop-preflight-v77.json' if desktop else 'out/lmi-gpu-research/mode46-tile-preflight.json' if tile else 'out/lmi-gpu-research/mode46-diag-preflight.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
