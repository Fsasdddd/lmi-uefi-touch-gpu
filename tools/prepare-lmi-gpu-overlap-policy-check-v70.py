"""Keep old fixtures unchanged; add v70 completion and ordering failures."""
from pathlib import Path
r=Path(__file__).resolve().parents[1];t=r/'tools'
s=(t/'check-lmi-display-v69-policy.py').read_text().replace('v69','v70')
at=s.index('good=policy.observe(fixture)')
s=s[:at]+'''overlap='LMI_GPU_COPY_OVERLAP 2000 2000 8000 6000 1000 100000\\n'
pending='LMI_GPU_COPY_PENDING 0\\n'
fixture=fixture.replace(cache,cache+overlap+pending)
'''+s[at:]
s=s.replace("'LMI_GPU_TARGET_CACHE']", "'LMI_GPU_TARGET_CACHE','LMI_GPU_COPY_OVERLAP','LMI_GPU_COPY_PENDING']")
at=s.index("(out/'synthetic-fixture.log')")
s=s[:at]+'''# These are admission fixtures, not measured runtime evidence.
for index,value in [(0,1999),(1,1999),(2,7999),(3,5999),(4,2001),(5,0)]:
    row=overlap.strip().split();row[index+1]=str(value)
    reject('copy-overlap-'+str(index),fixture.replace(overlap,' '.join(row)+'\\n'))
reject('copy-still-pending',fixture.replace(pending,'LMI_GPU_COPY_PENDING 42\\n'))
reject('copy-order',fixture.replace(overlap+pending,pending+overlap))
reject('overlap-overflow',fixture.replace(overlap,overlap.replace(' 8000 ',' '+str(1<<64)+' ')))
reject('pending-overflow',fixture.replace(pending,'LMI_GPU_COPY_PENDING '+str(1<<64)+'\\n'))
old=(root/'out/lmi-checkpoint-63-ios-probe-test-display-v69-desktop-180/checkpoint-63.log').read_text(encoding='utf-8')
reject('v69-has-no-async-copy-evidence',old)
for row in ['2000 2000 2000 0 0 0','2000 2000 8000 6000 0 100000']:
    trial=fixture.replace(overlap,'LMI_GPU_COPY_OVERLAP '+row+'\\n')
    assert policy.validate_run(policy.observe(trial))['passed'],row
    cases+=1
for field in ['counts_valid','pending_zero','record_order_valid']:
    trial=copy.deepcopy(good);trial['gpu_copy_overlap'][field]=False
    assert not policy.validate_run(trial)['passed'];cases+=1
'''+s[at:]
p=t/'check-lmi-display-v70-policy.py';assert not p.exists();p.write_text(s)
