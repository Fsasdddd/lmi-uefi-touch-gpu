"""Bind one compiler-proven frequency-index patch and independent live ACK data."""
import hashlib,json,re,shutil,struct,runpy
import lmi_display_v56_policy
KERNEL_SHA='5fe49222bc6bbed6678b2a2bfae7c32196f9414438e59fb457c5efd0198b4c43'
AUDIT_SHA='86c1b248aa619dc368be993bf06a8d237706167cf5812284d6f1ec55f4c096e4'
HOST_SHA='5242b2369797593c5bc45d54d01e750f96948a3e1a15136f30b130c4e741aa03'
BASE_POLICY_SHA='4b61ca05543036fd5b0aa85059886ba24503ae857ec5125d4028aaa9f1e2a553'
checked=lmi_display_v56_policy.checked

def stage(root,out):
    checked(root/'tools/lmi_display_v56_policy.py',BASE_POLICY_SHA)
    baseline,meta=lmi_display_v56_policy.stage(root,out)
    folder=root/'out/lmi-display-probe-v57b'
    raw=checked(folder/'mach.development.bcm2837',KERNEL_SHA)
    audit=json.loads(checked(folder/'build-audit.json',AUDIT_SHA))
    host=json.loads(checked(root/'out/lmi-gpu-gx-v57-host/result.json',HOST_SHA))
    assert host['result']=='PASS' and host['asan_ubsan'] and host['scenarios']==34 and not host['hardware_tested']
    for sources in (audit['sources'],host['sources']):
        for name,digest in sources.items():checked(root/'tools'/name,digest)
    assert audit['sha256']==KERNEL_SHA and audit['base_sha256']==meta['sha256']
    assert all(audit[k] for k in ['outside_patch_exact','relocations_unchanged','referenced_rodata_unchanged','unused_cst16_not_referenced'])
    assert audit['allowed_file_ranges']==[[11383544,11383548]]
    before=baseline.read_bytes();check=bytearray(raw)
    assert len(check)==len(before) and struct.unpack_from('<I',check,11383544)[0]==0xd28000e8
    assert struct.unpack_from('<I',before,11383544)[0]==0xd2800028
    check[11383544:11383548]=before[11383544:11383548];assert check==before
    target=out/'display-v57-candidate';assert not target.exists();shutil.copytree(folder,target)
    shutil.copy2(root/'out/lmi-gpu-gx-v57-host/result.json',target/'gx-host-check.json')
    meta['display_v57']=meta.pop('display_v56');meta['sha256']=KERNEL_SHA
    meta['display_v57']['gpu_frequency_experiment']=dict(stock_speed_bin=0,index=7,requested_khz=670000,bandwidth_index=255,measured=False,ram_only=True)
    meta['lmi_gpu_gx'].update(base_frequency_index=1,frequency_index=7,requested_khz=670000,frequency_measured=False,
        base_source_sha256=meta['lmi_gpu_gx']['source_sha256'],source_sha256=audit['sources']['lmi-gpu-gx-v57.c'])
    (target/'execution-profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    return target/'mach.development.bcm2837',meta

def frequency(log):
    def rows(marker,n):
        assert log.count(marker+'\n')==1,marker
        m=re.search(r'(?m)^'+re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(n)+r'})(?![0-9a-f]{16}\n)',log)
        assert m,marker
        return [int(v,16) for v in m[1].splitlines()]
    result=dict(requested_gpu_mhz=670,gpu_clock_measured=False,frequency_request_acknowledged=False)
    try:
        assert rows('LMI_GPU_PLAN_SPEED_BIN',1)==[0]
        plan=rows('LMI_GPU_PERF_PLAN',59);request=rows('LMI_GPU_HFI_PERF_REQUEST',59)
        expected=[0,8,2]+[0]*56
        for n,(khz,vote) in enumerate(zip([0,305000,400000,441600,490000,525000,587000,670000],
                [0,0x400202,0x800203,0x900304,0xc00305,0xe00406,0x1000507,0x1400608])):
            expected[3+3*n:6+3*n]=[vote,0xffffffff,khz]
        expected[53:55]=[0x400202,200000]
        assert plan==expected
        expected[0]=0x203b04;assert request==expected
        perf=rows('LMI_GPU_HFI_PERF_REPLY',8)
        assert perf[:5]==[64,64,4,8,1] and perf[5]&0xfff00==0x10300 and perf[6:]==[0x203b04,0]
        assert rows('LMI_GPU_HFI_PERF_RESULT',1)==[1]
        assert rows('LMI_GPU_HFI_START_REQUEST',1)==[0x50010a]
        assert rows('LMI_GPU_HFI_DCVS_REQUEST',4)==[0x60041e,1,7,255]
        ack=rows('LMI_GPU_HFI_DCVS_REPLY',8)
        assert ack[:5]==[236,236,20,24,1] and ack[5]&0xfff00==0x10300 and ack[6:]==[0x60041e,0]
        assert rows('LMI_GPU_GX_OOB_REQUEST',1)==[0x40000000]
        assert rows('LMI_GPU_GX_OOB_REPLY',1)==[0x80000000]
        assert not rows('LMI_GPU_GX_AFTER',1)[0]&0xc0 and rows('LMI_GPU_GX_RESULT',1)==[1]
        markers=['LMI_GPU_HFI_PERF_REQUEST','LMI_GPU_HFI_PERF_REPLY','LMI_GPU_HFI_PERF_ACK_VERIFIED',
            'LMI_GPU_HFI_START_REQUEST','LMI_GPU_HFI_START_ACK_VERIFIED','LMI_GPU_HFI_DCVS_REQUEST',
            'LMI_GPU_HFI_DCVS_REPLY','LMI_GPU_HFI_DCVS_ACK_VERIFIED','LMI_GPU_GX_OOB_REQUEST',
            'LMI_GPU_GX_OOB_REPLY','LMI_GPU_GX_OOB_HELD','LMI_GPU_GX_RESULT']
        assert all(log.count(m+'\n')==1 for m in markers)
        positions=[log.index(m+'\n') for m in markers];assert positions==sorted(positions)
        assert not any(m in log for m in ['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD'])
        result['frequency_request_acknowledged']=True
    except AssertionError as e:result['frequency_refusal']=str(e) or 'Live frequency/ACK/table mismatch'
    return result

def observe(log):
    result=lmi_display_v56_policy.observe(log)
    result['gpu_frequency']=frequency(log)
    result['performance_verified']=False
    return result
