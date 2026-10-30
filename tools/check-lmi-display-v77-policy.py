"""Use synthetic CPU records with an unchanged v73 log; never edit hardware evidence."""
from pathlib import Path
import hashlib,json,re
import lmi_display_v77_policy as policy
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'out/lmi-cpu-epss/policy-b';assert not out.exists();out.mkdir()
raw=(ROOT/'out/lmi-cpu-epss-v77e/mach.development.bcm2837').read_bytes()
original=(ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837').read_bytes()
audit=json.loads((ROOT/'out/lmi-cpu-epss-v77e/build-audit.json').read_text())
policy.verify_image(original,raw,audit)
native=json.loads((ROOT/'out/lmi-cpu-epss/native-e/result.json').read_text())
case=next(v for v in native['cases'] if v['name']=='apply-all-and-restore')
synthetic='\n'.join(tag+' '+' '.join(map(str,values)) for tag,values in case['logs'])+'\n'
baseline_path=ROOT/'out/lmi-checkpoint-63-ios-probe-test-display-v73-desktop-180/checkpoint-63.log'
baseline=baseline_path.read_text(encoding='utf-8')
combined=synthetic+baseline
assert policy.validate_run(policy.observe(combined))['passed']
assert policy.observe(combined)['cpu_epss']['measured_cpu_frequency'] is None
assert not policy.validate_run(policy.observe(baseline))['passed']
mutations={
    'missing-cpu-restore':re.sub(r'(?m)^LMI_CPU_EPSS_RESTORE .*\n','',combined),
    'missing-lut-chunk':combined.replace('LMI_CPU_EPSS_LUT 0 0 ','BAD_LUT 0 0 ',1),
    'duplicate-request':combined+next(l for l in synthetic.splitlines() if l.startswith('LMI_CPU_EPSS_REQUEST '))+'\n',
    'false-core-count':combined.replace('LMI_CPU_EPSS_LUT 0 0 262144','LMI_CPU_EPSS_LUT 0 0 196608',1),
    'wrong-request':combined.replace('LMI_CPU_EPSS_REQUEST 0 5 0 2 ','LMI_CPU_EPSS_REQUEST 0 5 0 3 ',1),
    'restore-failed':combined.replace('LMI_CPU_EPSS_RESTORE 1 1 0 1 7 3','LMI_CPU_EPSS_RESTORE 0 1 7 1 7 3'),
    'gpu-held':re.sub(r'(?m)^(LMI_GPU_BLIT_LIFETIME .*) 0$',r'\1 1',combined),
    'timing-missing':re.sub(r'(?m)^LMI_TIME_FRAME .*\n','',combined),
}
# A source0 core-count change can still be a legitimate ignored row, so use a
# selected row's count for this mutation rather than requiring unrelated bits.
old='1074004062';new=str(int(old)^(1<<16))
for name,text in list(mutations.items()):
    if name=='false-core-count':
        line=next(l for l in combined.splitlines() if l.startswith('LMI_CPU_EPSS_LUT 0 0 '))
        fields=line.split();fields[5]=str(int(fields[5])^(1<<16))
        text=combined.replace(line,' '.join(fields));mutations[name]=text
    assert text!=combined,name
    assert not policy.validate_run(policy.observe(text))['passed'],name
rejected=[]
for name,a,b in [('old-candidate',original,original),('wrong-parent',raw,raw),('truncated',original,raw[:-4])]:
    try:policy.verify_image(a,b,audit)
    except AssertionError:rejected.append(name)
    else:raise AssertionError(name)
paths=[Path(__file__),ROOT/'tools/lmi_display_v77_policy.py',baseline_path,
       ROOT/'out/lmi-cpu-epss/native-e/result.json',ROOT/'out/lmi-cpu-epss-v77e/build-audit.json']
report=dict(result='PASS',scenarios=14,record_mutations_rejected=list(mutations),image_mutations_rejected=rejected,
    prior_gpu_and_timing_rejections_preserved=True,synthetic_records_not_hardware_evidence=True,
    original_hardware_log_unchanged=True,hardware_tested=False,
    inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: 14 image/record checks; unchanged GPU/DPU/timing admission retained')
