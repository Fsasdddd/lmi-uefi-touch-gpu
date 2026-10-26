"""Pin v53 and retain final diagnostics without substituting for spatial proof."""
import json,re,shutil,struct
from lmi_display_v40_policy import validate,checked,KERNEL_SHA as BASE_SHA
KERNEL_SHA='82a67d40e2691bb82b42c14831a49b4aa233f924838552cf0eda3beab03ff651'
AUDIT_SHA='1c869d51f45d476919e9d9b20c1d888d08b1ccc953c423307b8f222d362a31a2'
HOST_SHA='2f1fbb191b667227dd51c1da09f495e30c5a209ec00f6f79fe3cef71e0826022'
DIAGNOSTIC_SHA='982b3cc19eadac53a467cb3e54779d5809be407ea16b3cfe3796dc311986a674'
NATIVE_SHA='97bd2f6f9d7351ae25578423bfedfda9c4478a9078a5951b5ccaf8ba92d0f1e6'
ALLOWED=[(11386880,11403264),(10353136,10353140),(4574416,4574420),
         (13588952,13588960),(13964696,13964704),(13964712,13964720)]

def branch(raw,at,pc,kind):
    word=struct.unpack_from('<I',raw,at)[0];imm=word&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    assert word&0xfc000000==kind
    return pc+imm*4

def stage(root,out):
    sealed,meta=validate(root);folder=root/'out/lmi-display-probe-v53b'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-display-dma-host-v53/result.json',HOST_SHA))
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==BASE_SHA
    assert all(audit[k] for k in ('layout_unchanged','original_source_bytes_exact','runtime_outside_extension_exact','automatic_pattern_probe'))
    assert audit['register_writes'] and not audit['desktop_pipeline'] and not audit['conditional_desktop_enable']
    assert audit['batched_scaler_diagnostic']
    assert host['v50_refusal_reproduced']
    assert host['result']=='PASS' and host['asan_ubsan'] and not host['hardware_tested']
    for name,digest in audit['sources'].items():
        checked(root/'tools'/name,digest);checked(folder/name,digest)
    for name,digest in host['sources'].items():checked(root/'tools'/name,digest)
    checked(root/'tools/build-lmi-display-v53.py',audit['builder_sha256'])
    checked(folder/'compositor-layout.json',audit['compositor_layout_sha256'])
    for report_path,expected in [('out/lmi-display-diagnostic-v53-host/result.json',DIAGNOSTIC_SHA),
                                 ('out/lmi-display-native-v53-host/result.json',NATIVE_SHA)]:
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
    meta['sha256']=KERNEL_SHA;meta['display_v53']=meta.pop('display_v40')
    meta['display_v53'].update(readonly=False,automatic_pattern_probe=True,desktop_pipeline=False,conditional_desktop_enable=False,batched_scaler_diagnostic=True,
        spatial_scaler_verified=False,dma_verified=False,return_restoration=True)
    target=out/'display-v53-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-display-dma-host-v53/result.json',target/'dma-host-check.json')
    shutil.copy2(root/'out/lmi-display-diagnostic-v53-host/result.json',target/'diagnostic-host-check.json')
    shutil.copy2(root/'out/lmi-display-native-v53-host/result.json',target/'native-host-check.json')
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta


def observe(log):
    lines=log.splitlines();rows=[];malformed=[]
    pattern=re.compile(r'LMI_DPU_PROBE stage=(\d+) ok=([01]) exp=([0-9a-f]+) got=([0-9a-f]+) ticks=(\d+)')
    for index,line in enumerate(lines):
        if 'LMI_DPU_PROBE stage=' not in line:continue
        m=pattern.fullmatch(line)
        if not m:malformed.append(line);continue
        stage,ok,expected,actual,ticks=m.groups()
        rows.append(dict(stage=int(stage),ok=bool(int(ok)),expected=int(expected,16),actual=int(actual,16),ticks=int(ticks),position=index))
    expected_stages=[1,2]
    for variant in range(8):
        for kind in range(4):expected_stages.extend(1000+variant*100+kind*10+n for n in range(9))
    expected_stages += [90,5,9000]
    off=[i for i,l in enumerate(lines) if l=='LMI_SMP_OTHER_CORES_OFF']
    begin=[i for i,l in enumerate(lines) if l=='LMI_DPU_PROBE_BEGIN live=1']
    restored=[i for i,l in enumerate(lines) if l=='LMI_DPU_PROBE_RETURN restored=1']
    complete=(not malformed and [r['stage'] for r in rows]==expected_stages and len(off)==len(begin)==len(restored)==1 and
              off[0]<begin[0]<rows[0]['position']<rows[-1]['position']<restored[0] and
              'LMI_DPU_PROBE_RETURN restored=0' not in log and 'LMI_DPU_DESKTOP' not in log and 'LMI_DPU_REFUSAL' not in log)
    results=[];bitmap=0;pattern_references={}
    if complete:
        complete=rows[0]['ok'] and rows[1]['ok']
        for variant in range(8):
            for kind in range(4):
                group=rows[2+9*(variant*4+kind):2+9*(variant*4+kind)+9]
                native=group[:4];scaled=group[4:8];summary=group[8]
                a,b=native[0]['actual'],native[1]['actual'];references=[a,b,b,a]
                valid=(a!=b and all(row['ok'] and row['expected']==row['actual']==ref for row,ref in zip(native,references)) and
                       all(row['expected']==ref and row['ok']==(row['actual']==ref) for row,ref in zip(scaled,references)))
                valid=valid and pattern_references.setdefault(kind,(a,b))==(a,b)
                same=all(row['ok'] for row in scaled)
                valid=valid and summary['ok']==same and summary['expected']==a and summary['actual']==b and summary['ticks']==variant+1
                complete=complete and valid
                if same:bitmap|=1<<(variant*4+kind)
                results.append(dict(variant=variant,pattern=['flat','vertical_stripes','horizontal_stripes','grid'][kind],
                    preload='5/3' if variant&1 else '4/2',phase='zero' if variant&2 else 'centered',
                    dynamic_expansion=not bool(variant&4),evidence_consistent=valid,all_four_scaled_frames_match=same,
                    references=[hex(a),hex(b)],scaled_crc=[hex(row['actual']) for row in scaled]))
        total,recovery,final=rows[-3:]
        complete=bool(complete and total['ok'] and total['expected']==total['actual']==256 and total['ticks']==bitmap and
                      recovery['ok'] and recovery['expected']==recovery['actual']==recovery['ticks']==0 and
                      not final['ok'] and final['expected']==256 and final['actual']==1)
    # A partial/contradictory log never establishes even a candidate match.
    matching=[variant for variant in range(8) if all(x['all_four_scaled_frames_match'] for x in results if x['variant']==variant)] if complete else []
    return dict(probe_result='BATCH_DIAGNOSTIC_COMPLETE' if complete else 'BATCH_DIAGNOSTIC_INCOMPLETE',
        diagnostic_complete=complete,hardware_tested=True,hardware_scaling_verified=False,desktop_pipeline_enabled=False,
        performance_verified=False,desktop_average_fps=None,return_restored=len(restored)==1,
        matching_variants=matching,pattern_results=results,malformed=malformed,probe_samples=rows,
        submitted_frames=rows[-3]['expected'] if complete else None,completed_frames=rows[-3]['actual'] if complete else None)
