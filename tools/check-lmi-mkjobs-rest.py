"""Regression check: REST jobs retain distinct plist names, with/without env propagation."""
from pathlib import Path
import hashlib,json,os,plistlib,subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-mkjobs-rest-check'
before=out/'mkjobs.before.py'
after=root/'userland-source/userland/mkjobs.py'
records=[]
with tempfile.TemporaryDirectory(prefix='fixture-',dir=out) as temp:
    work=Path(temp);ios=work/'ios'
    daemons=ios/'System/Library/LaunchDaemons';angels=ios/'System/Library/LaunchAngels'
    daemons.mkdir(parents=True);angels.mkdir()
    labels=['org.lmi.seed','org.lmi.extraA','org.lmi.extraB','org.lmi.keyboard']
    for i,label in enumerate(labels):
        job=dict(Label=label,Program=f'/usr/libexec/{label}',MachServices={label:True},RunAtLoad=True,KeepAlive=True)
        with ((angels if i==3 else daemons)/(label+'.plist')).open('wb') as f:plistlib.dump(job,f)
    listing=work/'root.slt';listing.write_text(''.join(f'Path = usr/libexec/{label}\n' for label in labels))
    for env_value in (None,'1'):
        env=os.environ.copy();env.pop('RWA_PACKED16',None)
        if env_value:env['RWA_PACKED16']=env_value
        for source in (before,after):
            dest=work/(source.name+('-set' if env_value else '-unset'))
            completed=subprocess.run([sys.executable,str(source),'--rest','--root-volume',str(listing),str(ios),str(dest),labels[0]],env=env,capture_output=True,text=True,check=True)
            names=sorted(p.name for p in dest.iterdir())
            if source==before:
                assert names==['RWA_PACKED16',labels[0]+'.plist'],names
            else:
                assert names==sorted(label+'.plist' for label in labels),names
                found=[]
                for path in dest.iterdir():
                    job=plistlib.loads(path.read_bytes());found.append(job['Label'])
                    assert job['StandardOutPath']==job['StandardErrorPath']=='/dev/console'
                    if job['Label']!=labels[0]:assert 'RunAtLoad' not in job and 'KeepAlive' not in job
                    assert job.get('EnvironmentVariables',{}).get('RWA_PACKED16')==env_value
                assert sorted(found)==sorted(labels) and len(set(found))==4
            records.append(dict(source=source.name,RWA_PACKED16=env_value,files=names,stdout=completed.stdout))
report=dict(before_sha256=hashlib.sha256(before.read_bytes()).hexdigest(),after_sha256=hashlib.sha256(after.read_bytes()).hexdigest(),records=records,result='PASS: reproduced overwritten REST filenames; fixed distinct daemon/angel jobs and env propagation')
(out/'regression.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['result'])
