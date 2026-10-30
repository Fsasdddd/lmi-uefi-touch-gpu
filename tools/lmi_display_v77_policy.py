"""CPU-only EPSS requests plus the complete unchanged v73 GPU/DPU admission."""
import hashlib,json,re,shutil
import lmi_display_v73_policy as prior
checked=prior.checked
KERNEL_SHA='ca0b8c221f8318f1447b043e7e31bf944a6baadfa9647a83afb409b2bad4a901'
AUDIT_SHA='5c4fe95c22be501bedd6b9469f9cff4af1a1bbc9b137239628cc07c7a3a963cf'
HOST_SHA='7d37145cffd5f723b939caa2bcecd350196d7ded9b40f3e39ec75e6899b9d8a8'
NATIVE_SHA='e66b1e9cc3ed876f51d603d870a19c8d1cdb59b01f2313e49f284f923593749b'
LINK_SHA='824ca7b9d8cd4ce233d5ac0115b71612d384042c8efe11186388232af4dc47c5'
PRIOR_SHA='8cf330b0787fe9c4a8aa393e3d5a6237f07bee3ec97444f6015dae273b961ee3'
CAPS=(1804800,2419200,2841600)


def verify_image(original,raw,audit):
    assert hashlib.sha256(original).hexdigest()==prior.KERNEL_SHA
    assert hashlib.sha256(raw).hexdigest()==KERNEL_SHA and len(raw)==len(original)
    assert audit['base_sha256']==prior.KERNEL_SHA and audit['sha256']==KERNEL_SHA
    restored=bytearray(raw)
    for a,z in audit['allowed_file_ranges']:
        assert 0<=a<z<=len(raw);restored[a:z]=original[a:z]
    assert restored==original
    assert len(audit['hooks'])==3 and audit['native_gpu_poll_us']==200 and audit['ddr_disabled']


def stage(root,out):
    checked(root/'tools/lmi_display_v73_policy.py',PRIOR_SHA)
    folder=root/'out/lmi-cpu-epss-v77e'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    paths=[(root/'out/lmi-cpu-epss/host-c/result.json',HOST_SHA),
           (root/'out/lmi-cpu-epss/native-e/result.json',NATIVE_SHA),
           (root/'out/lmi-cpu-epss/link-c/result.json',LINK_SHA)]
    reviews=[json.loads(checked(p,d)) for p,d in paths]
    assert reviews[0]['scenarios']==291 and len(reviews[0]['mutations_caught'])==8
    assert reviews[1]['scenarios']==13 and reviews[1]['original_display_cleanup_called_before_cpu_restore']
    assert reviews[2]['link_reproduced'] and reviews[2]['live_checkpoint63_cleanup_verified']
    for report in [audit,*reviews]:
        if 'scenarios' in report or 'link_reproduced' in report:assert report['result']=='PASS'
        for name,digest in report['inputs'].items():checked(root/name,digest)
    baseline,meta=prior.stage(root,out)
    verify_image(baseline.read_bytes(),raw,audit)
    target=out/'display-v77-candidate';assert not target.exists();shutil.copytree(folder,target)
    for path,_ in paths:shutil.copy2(path,target/(path.parent.name+'-review.json'))
    meta['display_v77']=meta.pop('display_v73');meta['sha256']=KERNEL_SHA
    meta['display_v77'].update(performance_change=True,performance_verified=False,
        independent_cpu_requests=True,cpu_caps_khz=list(CAPS),ddr_disabled=True,
        native_gpu_fence_poll_us=200,v72_touch_preserved=True,
        all_prior_gpu_display_safety_required=True,original_cleanup_then_cpu_restore=True)
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta


def cpu_observe(log):
    tags=('INIT','LUT','APPLY','REQUEST','RESTORE','RESTORE_DOMAIN')
    rows={};valid=True
    for tag,n in zip(tags,[6,10,6,7,6,4]):
        matches=re.findall(r'(?m)^LMI_CPU_EPSS_'+tag+r' ((?:[0-9]+ ){'+str(n-1)+r'}[0-9]+)$',log)
        lines=[line for line in log.splitlines() if line.startswith('LMI_CPU_EPSS_'+tag+' ')]
        values=[list(map(int,line.split())) for line in matches];rows[tag]=values
        valid &= len(matches)==len(lines) and all(all(0<=v<1<<32 for v in row) for row in values)
    valid &= [len(rows[t]) for t in tags]==[1,15,1,3,1,3]
    details=[];mask=0
    if valid:
        valid &= rows['INIT'][0]==[1,1,0,0,0,3]
        for i,cap in enumerate(CAPS):
            chunks=rows['LUT'][i*5:i*5+5]
            valid &= [v[:2] for v in chunks]==[[i,j] for j in range(0,40,8)]
            lut=[word for v in chunks for word in v[2:]]
            decoded=[((v&255)*19200 if v>>30 else 300000,(v>>16)&7) for v in lut]
            end=next((j for j in range(1,40) if decoded[j]==decoded[j-1]),None)
            eligible=[(freq,j) for j,(freq,cc) in enumerate(decoded[:end])
                      if lut[j]>>30 and cc==4 and 0<freq<=cap] if end else []
            request=rows['REQUEST'][i];restore=rows['RESTORE_DOMAIN'][i]
            if not eligible:valid=False;continue
            frequency=max(freq for freq,j in eligible)
            target=next(j for freq,j in eligible if freq==frequency)
            orig=request[2]
            valid &= request[:2]==[i,end] and orig<end and decoded[min(orig,39)][0]<=cap
            valid &= request[3:]==[target,frequency,target,2]
            changed=orig!=target;mask|=int(changed)<<i
            valid &= restore==[i,orig,orig if changed else 0,0]
            details.append(dict(domain=i,original_request_index=orig,target_request_index=target,
                requested_khz=frequency,restore_readback=restore[2] if changed else None,
                unchanged_request=not changed,measured_cpu_frequency=None))
        valid &= rows['APPLY'][0]==[1,1,mask,1,mask,3]
        valid &= rows['RESTORE'][0]==[1,1,0,1,mask,3]
    positions=[log.find('LMI_CPU_EPSS_'+tag+' ') for tag in tags]
    valid &= all(p>=0 for p in positions) and positions==sorted(positions)
    return dict(records_and_requests_valid=bool(valid),domains=details,changed_mask=mask,
        measured_cpu_frequency=None,measured_animation_fps=None,performance_verified=False,
        scope='Validates board LUT selection, requested index readback and restoration of modified requests. Neither EPSS request nor Android policy is a CPU or animation frequency measurement.')


def observe(log):
    result=prior.observe(log);result['cpu_epss']=cpu_observe(log);return result


def validate_run(observation):
    result=prior.validate_run(observation)
    if observation.get('cpu_epss',{}).get('records_and_requests_valid') is not True:
        result['failed_checks'].append('cpu_epss.records_and_requests_valid')
    result['passed']=not result['failed_checks']
    return result
