"""Pin a read-only lmi scaler/DMA inventory separately from the future pipeline."""
import json,re,shutil,struct
from lmi_display_v40_policy import validate,checked,KERNEL_SHA as BASE_SHA
from lmi_display_v41_policy import observe as observe41
KERNEL_SHA='63e0b7984c508dcf7e3580b9052d5bcf639fd5c94b55661022b7e24604589a36'
SOURCE_SHA='0c6e96e2f4b8149ba265deafb11399168b7585153a60ac80adea9dd3d03c105b'
SURVEY_SHA='d34c036b797cef6b56baa87496a79b8b7978e5e4ee4f59e761571932297be9b2'
BUILDER_SHA='256582d362b857b49b282785b732cbee13034b855e8be76b9f85f01dc8f97056'
ALLOWED=[(11386880,11403264),(10353136,10353140),(13588952,13588960),(13964712,13964720)]
def stage(root,out):
    sealed,meta=validate(root);folder=root/'out/lmi-display-observer-v43'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads((folder/'build-audit.json').read_text())
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==BASE_SHA
    for key in ['layout_unchanged','original_source_bytes_exact','runtime_outside_extension_exact']:assert audit[key]
    assert audit['register_writes'] is False and audit['synchronized_present'] is False
    for name,digest in [('lmi-dpu-observer-v43.c',SOURCE_SHA),('lmi-dpu-survey-v43.c',SURVEY_SHA),('build-lmi-display-v43.py',BUILDER_SHA)]:
        checked(root/'tools'/name,digest);checked(folder/name,digest) if name.endswith('.c') else None
    assert audit['source_sha256']==SOURCE_SHA and audit['survey_sha256']==SURVEY_SHA and audit['builder_sha256']==BUILDER_SHA
    host=json.loads((root/'out/lmi-dpu-observer-v43-host/result.json').read_text())
    survey=json.loads((root/'out/lmi-dpu-survey-v43-host/result.json').read_text())
    assert host['result']=='PASS' and host['source_sha256']==SOURCE_SHA and host['forwards']==512 and host['readonly_mapping']
    assert survey['result']=='PASS' and survey['source_sha256']==SURVEY_SHA and survey['scenarios']==14 and survey['readonly_mmio']
    old=(sealed/'mach.development.bcm2837').read_bytes();assert len(raw)==len(old)
    check=bytearray(raw)
    for lo,hi in ALLOWED:check[lo:hi]=old[lo:hi]
    assert check==old and audit['allowed_file_ranges']==[list(r) for r in ALLOWED]
    assert struct.unpack_from('<I',raw,10353136)[0]==0x1403f1a0
    pc=0xfffffff007ae07e4
    first,branch=struct.unpack_from('<II',raw,11386880+pc-0xfffffff007ae0000)
    imm=branch&0x3ffffff;imm=imm-(1<<26) if imm&(1<<25) else imm
    assert first==0xd10703ff and branch&0xfc000000==0x14000000 and pc+4+imm*4==0xfffffff0079e39f4
    meta['sha256']=KERNEL_SHA;meta['display_v43']=meta.pop('display_v40')
    meta['display_v43'].update(scaler_dma_survey=True,buffer_pipeline_enabled=False,readonly=True)
    target=out/'display-v43-candidate';assert not target.exists();shutil.copytree(folder,target)
    for name,directory in [('observer-host-check','lmi-dpu-observer-v43-host'),('survey-host-check','lmi-dpu-survey-v43-host')]:
        shutil.copy2(root/'out'/directory/'result.json',target/(name+'.json'))
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def observe(log):
    result=observe41(log);rows=[];matches=[];malformed=[];ends=[]
    reg=re.compile(r'LMI_DPU_SURVEY space=([01]) offset=([0-9a-f]+) value=([0-9a-f]+)')
    stream=re.compile(r'LMI_DPU_STREAM slot=(\d+) smr=([0-9a-f]+) s2cr=([0-9a-f]+) covers=([0-9a-f]+) cb=(\d+)')
    end=re.compile(r'LMI_DPU_SURVEY_END valid=(\d+) slots=(\d+) contexts=(\d+) coverage=(\d+)/(\d+)/(\d+)/(\d+) writes=0')
    for line in log.splitlines():
        if line.startswith('LMI_DPU_SURVEY space='):
            m=reg.fullmatch(line)
            if not m:malformed.append(line);continue
            space,offset,value=m.groups();rows.append(dict(space=int(space),offset=int(offset,16),value=int(value,16)))
        elif line.startswith('LMI_DPU_STREAM '):
            m=stream.fullmatch(line)
            if not m:malformed.append(line);continue
            slot,smr,s2cr,covers,cb=m.groups();matches.append(dict(slot=int(slot),smr=int(smr,16),s2cr=int(s2cr,16),covers=int(covers,16),cb=int(cb)))
        elif line.startswith('LMI_DPU_SURVEY_END '):
            m=end.fullmatch(line)
            if not m:malformed.append(line);continue
            ends.append(list(map(int,m.groups())))
    keys=[(r['space'],r['offset']) for r in rows]
    complete=(log.splitlines().count('LMI_DPU_SURVEY_BEGIN readonly=1')==1 and len(ends)==1 and
        ends[0][0]==1 and ends[0][3:]==[1,1,1,1] and not malformed and
        'LMI_DPU_SURVEY_REFUSED' not in log and len(keys)==len(set(keys)) and
        all(key in keys for key in [(0,0x5a00),(0,0x5a20),(1,0),(1,0x20),(1,0x24)]))
    result.update(survey_result='READ_ONLY_INVENTORY_COMPLETE' if complete else 'NOT_VERIFIED',
        survey_registers=rows,stream_matches=matches,survey_end=ends,survey_malformed=malformed,
        dma_verified=False,hardware_scaling_verified=False,double_buffer_enabled=False)
    return result
