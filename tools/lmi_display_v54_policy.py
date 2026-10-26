"""Pin v54 and retain final diagnostics without substituting for spatial proof."""
import json,re,shutil,struct
from lmi_display_v40_policy import validate,checked,KERNEL_SHA as BASE_SHA
KERNEL_SHA='33da354aa8383e62834c37955f2c9bf2a0102778959dbb8c0e3df8b279aa569d'
AUDIT_SHA='4ab403b8b1592b71fcd4996d647f85206906451d8abc750f1fd5fb74ec6062dd'
HOST_SHA='71789af662c8e9abec1dbfdd724d3cd609ed743d91d2bc7e791edd59671572fe'
DIAGNOSTIC_SHA='408e50fb01a15002b4b9ef6fa187591415745b0003330e675dfcf54b243075b0'
NATIVE_SHA='30d4208b2299c0f6b5b2186526d941594e163c7ca284a9f76d5f017a232d844b'
ALLOWED=[(11386880,11403264),(10353136,10353140),(4574416,4574420),
         (13588952,13588960),(13964696,13964704),(13964712,13964720)]

def branch(raw,at,pc,kind):
    word=struct.unpack_from('<I',raw,at)[0];imm=word&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    assert word&0xfc000000==kind
    return pc+imm*4

def stage(root,out):
    sealed,meta=validate(root);folder=root/'out/lmi-display-probe-v54'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-dma-host-v54/result.json',HOST_SHA))
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==BASE_SHA
    assert all(audit[k] for k in ('layout_unchanged','original_source_bytes_exact','runtime_outside_extension_exact','automatic_pattern_probe'))
    assert audit['register_writes'] and not audit['desktop_pipeline'] and not audit['conditional_desktop_enable']
    assert audit['batched_scaler_diagnostic']
    assert host['v50_refusal_reproduced']
    assert host['result']=='PASS' and host['asan_ubsan'] and not host['hardware_tested']
    for name,digest in audit['sources'].items():
        checked(root/'tools'/name,digest);checked(folder/name,digest)
    for name,digest in host['sources'].items():checked(root/'tools'/name,digest)
    checked(root/'tools/build-lmi-display-v54.py',audit['builder_sha256'])
    checked(folder/'compositor-layout.json',audit['compositor_layout_sha256'])
    for report_path,expected in [('out/lmi-display-diagnostic-v54-host/result.json',DIAGNOSTIC_SHA),
                                 ('out/lmi-display-native-v54-host/result.json',NATIVE_SHA)]:
        report=json.loads(checked(root/report_path,expected))
        assert report['result']=='PASS' and report['asan_ubsan'] and not report['hardware_tested']
        for name,digest in report['sources'].items():checked(root/'tools'/name,digest)
    old=(sealed/'mach.development.bcm2837').read_bytes();assert len(raw)==len(old)
    assert audit['allowed_file_ranges']==[list(r) for r in ALLOWED]
    check=bytearray(raw)
    for lo,hi in ALLOWED:check[lo:hi]=old[lo:hi]
    assert check==old
    assert raw[0xb42fe0:0xb43000]==bytes(32)
    assert branch(raw,10353136,0xfffffff0079e39f0,0x14000000)==int(audit['observer'],16)
    assert branch(raw,4574416,0xfffffff007460cd0,0x94000000)==int(audit['cleanup'],16)
    trampoline=int(audit['trampoline'],16);at=11386880+trampoline-0xfffffff007ae0000
    assert struct.unpack_from('<I',raw,at)[0]==0xd10703ff
    assert branch(raw,at+4,trampoline+4,0x14000000)==0xfffffff0079e39f4
    meta['sha256']=KERNEL_SHA;meta['display_v54']=meta.pop('display_v40')
    meta['display_v54'].update(readonly=False,automatic_pattern_probe=True,desktop_pipeline=False,conditional_desktop_enable=False,batched_scaler_diagnostic=True,
        spatial_scaler_verified=False,dma_verified=False,return_restoration=True)
    target=out/'display-v54-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-dma-host-v54/result.json',target/'dma-host-check.json')
    shutil.copy2(root/'out/lmi-display-diagnostic-v54-host/result.json',target/'diagnostic-host-check.json')
    shutil.copy2(root/'out/lmi-display-native-v54-host/result.json',target/'native-host-check.json')
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta


def observe(log):
    lines=log.splitlines();rows=[];malformed=[]
    pattern=re.compile(r'LMI_DPU_PROBE stage=(\d+) ok=([01]) exp=([0-9a-f]+) got=([0-9a-f]+) ticks=(\d+)')
    for index,line in enumerate(lines):
        if 'LMI_DPU_PROBE stage=' not in line:continue
        m=pattern.fullmatch(line)
        if not m:malformed.append(line);continue
        s,ok,e,a,t=m.groups()
        rows.append(dict(stage=int(s),ok=bool(int(ok)),expected=int(e,16),actual=int(a,16),ticks=int(t),position=index))
    expected_stages=[1,2]
    for v in range(8):
        for k in range(5):expected_stages.extend(1000+v*100+k*20+n for n in range(13))
    expected_stages += [90,5,9000]
    markers=[[i for i,l in enumerate(lines) if l==m] for m in
        ['LMI_SMP_OTHER_CORES_OFF','LMI_DPU_PROBE_BEGIN live=1','LMI_DPU_PROBE_RETURN restored=1']]
    complete=(not malformed and [r['stage'] for r in rows]==expected_stages and all(len(m)==1 for m in markers) and
        markers[0][0]<markers[1][0]<rows[0]['position']<rows[-1]['position']<markers[2][0] and
        not any(m in log for m in ['LMI_DPU_PROBE_RETURN restored=0','LMI_DPU_DESKTOP','LMI_DPU_REFUSAL']))
    results=[];bitmap=0;bypass_references={}
    if complete:
        complete=rows[0]['ok'] and rows[1]['ok']
        for v in range(8):
            for k in range(5):
                at=2+13*(v*5+k);g=rows[at:at+13]
                bypass,identity,scaled,summary=g[:4],g[4:8],g[8:12],g[12]
                a,b=identity[0]['actual'],identity[1]['actual'];refs=[a,b,b,a]
                ba,bb=bypass[0]['actual'],bypass[1]['actual'];brefs=[ba,bb,bb,ba]
                stable=lambda samples,refs:all(r['ok'] and r['expected']==r['actual']==ref for r,ref in zip(samples,refs))
                valid=(a!=b and ba!=bb and stable(bypass,brefs) and stable(identity,refs) and
                    bypass_references.setdefault(k,(ba,bb))==(ba,bb) and
                    all(r['expected']==ref and r['ok']==(r['actual']==ref) for r,ref in zip(scaled,refs)))
                same=all(r['ok'] for r in scaled)
                valid=valid and summary['ok']==same and summary['expected']==a and summary['actual']==b and summary['ticks']==v+1
                if same:bitmap|=1<<(v*5+k)
                complete=complete and valid
                results.append(dict(variant=v,pattern=['flat','vertical_stripes','horizontal_stripes','grid','black_white'][k],
                    preload='5/3' if v&1 else '4/2',phase='zero' if v&2 else 'centered',dynamic_expansion=not bool(v&4),
                    evidence_consistent=valid,all_four_scaled_frames_match=same,
                    identity_matches_bypass=refs==brefs,scaled_matches_bypass=[r['actual'] for r in scaled]==brefs,
                    bypass_crc=[hex(r['actual']) for r in bypass],identity_crc=[hex(r['actual']) for r in identity],
                    scaled_crc=[hex(r['actual']) for r in scaled]))
        total,recovery,final=rows[-3:]
        complete=bool(complete and total['ok'] and total['expected']==total['actual']==480 and total['ticks']==bitmap and
            recovery['ok'] and recovery['expected']==recovery['actual']==recovery['ticks']==0 and
            not final['ok'] and final['expected']==480 and final['actual']==1)
    geometry=[v for v in range(8) if all(r['all_four_scaled_frames_match'] for r in results if r['variant']==v)] if complete else []
    exact=[v for v in range(8) if all(r['scaled_matches_bypass'] for r in results if r['variant']==v)] if complete else []
    return dict(probe_result='IDENTITY_DIAGNOSTIC_COMPLETE' if complete else 'IDENTITY_DIAGNOSTIC_INCOMPLETE',
        diagnostic_complete=complete,hardware_tested=True,hardware_scaling_verified=False,desktop_pipeline_enabled=False,
        performance_verified=False,desktop_average_fps=None,return_restored=len(markers[2])==1,
        matching_variants=[],geometry_matching_variants=geometry,bypass_matching_variants=exact,
        pattern_results=results,probe_samples=rows,malformed=malformed,
        submitted_frames=480 if complete else None,completed_frames=480 if complete else None)

