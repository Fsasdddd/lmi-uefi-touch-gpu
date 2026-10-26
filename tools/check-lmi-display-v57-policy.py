"""In-memory log mutation tests; modeled index7 ACK is never saved as hardware."""
from pathlib import Path
import hashlib,json,re
from lmi_display_v57_policy import frequency,observe
root=Path(__file__).resolve().parents[1];out=root/'out/lmi-display-v57-policy-host';out.mkdir(exist_ok=True)
baseline=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v56-desktop-180/checkpoint-63.log').read_text()
old='LMI_GPU_HFI_DCVS_REQUEST\n000000000060041e\n0000000000000001\n0000000000000001\n00000000000000ff\n'
new=old.replace('0000000000000001\n00000000000000ff','0000000000000007\n00000000000000ff')
assert baseline.count(old)==1
model=baseline.replace(old,new)
checks=0
def check(log,ok=False):
    global checks
    result=frequency(log);checks+=1
    assert result['frequency_request_acknowledged']==ok,(checks,result)
    assert result['requested_gpu_mhz']==670 and not result['gpu_clock_measured']
check(model,True);check(baseline);check('')
markers={'LMI_GPU_PLAN_SPEED_BIN':1,'LMI_GPU_PERF_PLAN':59,'LMI_GPU_HFI_PERF_REQUEST':59,
    'LMI_GPU_HFI_PERF_REPLY':8,'LMI_GPU_HFI_PERF_RESULT':1,'LMI_GPU_HFI_START_REQUEST':1,
    'LMI_GPU_HFI_DCVS_REQUEST':4,'LMI_GPU_HFI_DCVS_REPLY':8,'LMI_GPU_GX_OOB_REQUEST':1,
    'LMI_GPU_GX_OOB_REPLY':1,'LMI_GPU_GX_AFTER':1,'LMI_GPU_GX_RESULT':1}
for marker,count in markers.items():
    m=re.search(re.escape(marker)+r'\n((?:[0-9a-f]{16}\n){'+str(count)+'})',model);assert m
    words=m[1].splitlines(keepends=True)
    check(model[:m.start()]+model[m.end():])
    check(model+model[m.start():m.end()])
    check(model[:m.end()]+'0000000000000000\n'+model[m.end():])
    for i,word in enumerate(words):
        # ACK upper sequence bits are intentionally allowed by the protocol.
        if marker.endswith('_REPLY') and i==5:bit=0x100
        elif marker=='LMI_GPU_GX_AFTER':bit=0x40
        else:bit=1
        edited=words.copy();edited[i]=f'{int(word,16)^bit:016x}\n'
        check(model[:m.start(1)]+''.join(edited)+model[m.end(1):])
for marker in ['LMI_GPU_HFI_PERF_ACK_VERIFIED','LMI_GPU_HFI_START_ACK_VERIFIED',
               'LMI_GPU_HFI_DCVS_ACK_VERIFIED','LMI_GPU_GX_OOB_HELD']:
    check(model.replace(marker+'\n',''));check(model+marker+'\n')
for marker in ['LMI_GPU_DESKTOP_FAULT_HELD','LMI_GPU_DESKTOP_RELEASE_HELD']:
    check(model+marker+'\n')
result=observe(model)
assert result['desktop_pipeline_enabled'] and result['gpu_frequency']['frequency_request_acknowledged']
assert not result['performance_verified'] and not result['bypass_pixel_equivalence']
names=['lmi_display_v57_policy.py','lmi_display_v56_policy.py','check-lmi-display-v57-policy.py']
report=dict(result='PASS',checks=checks,hardware_tested=False,model_not_saved_as_hardware=True,
    sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
