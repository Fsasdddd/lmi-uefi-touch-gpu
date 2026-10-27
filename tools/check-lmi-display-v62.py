"""Actual producer-fence code and frozen compositor/pitch regression, host only."""
from pathlib import Path
import hashlib,json,re,subprocess
root=Path(__file__).resolve().parents[1]
out=root/'out/lmi-display-v62-host';out.mkdir(exist_ok=True)
names=['check-lmi-display-v62.py','check-lmi-display-fence-v62.c',
       'lmi-display-fence-v62.c','lmi-display-fence-v62.h','lmi-display-fence-abi-v62.h',
       'lmi-display-fast-v62.c','lmi-display-fast-v62.h','lmi-display-surface-abi.h',
       'lmi-display-direct-plan-v61.c','lmi-display-direct-plan-v61.h',
       'lmi-display-compositor-v56.c','lmi-display-compositor.h','lmi-display-compositor-abi.h',
       'lmi-display-pipeline-v51.c','lmi-display-pipeline.h','check-lmi-display-fast-v61.c']
flags=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-pthread','-I'+str(root/'tools')]
commands=[];logs=[]
def run(label,sources):
    cmd=[*flags,*map(str,sources),'-o',str(out/label)]
    commands.append(cmd);subprocess.run(cmd,check=True)
    result=subprocess.run([str(out/label)],text=True,capture_output=True,timeout=20)
    logs.append(result.stdout+result.stderr);(out/(label+'.log')).write_text(logs[-1]);print(logs[-1],end='')
    result.check_returncode();return result.stdout
fence=run('fence',[root/'tools/lmi-display-fence-v62.c',root/'tools/check-lmi-display-fence-v62.c'])
fence_cases=int(re.search(r'PASS: (\d+) producer',fence)[1])
# The pixel/compositor scenarios are identical to v61. The only adaptations
# install the now separately allocated journal and check the fifth log line.
test=(root/'tools/check-lmi-display-fast-v61.c').read_text()
test=test.replace('lmi-display-fast-v61.h','lmi-display-fast-v62.h')
test=test.replace('logged[8][256]','logged[10][256]').replace('log_count<8','log_count<10')
test=test.replace('!strncmp(s,"LMI_FRAME_STRIDE ",17)',
                  '!strncmp(s,"LMI_FRAME_STRIDE ",17) || !strncmp(s,"LMI_SWAP_FENCE ",15)')
test=test.replace('current=f;\n    source', 'current=f;\n    lmi_fast_state=calloc(1,sizeof(*lmi_fast_state));assert(lmi_fast_state);\n    source')
test=test.replace('log_count==4','log_count==5').replace('log_count==8','log_count==10')
test=test.replace('logged[4],"LMI_DPU_FAST','logged[5],"LMI_DPU_FAST')
test=test.replace('strlen(logged[6])','strlen(logged[7])').replace('logged[7],"LMI_FRAME_STRIDE','logged[8],"LMI_FRAME_STRIDE')
test=test.replace('lmi_fast_state->strided=UINT64_MAX;',
                  'lmi_fast_state->strided=UINT64_MAX;\n    for(unsigned i=0;i<10;i++)((&lmi_fast_state->fence.began)[i])=UINT64_MAX;')
test=test.replace('destroy(f);scenarios++;\n    /* Exercise',
                  'assert(strlen(logged[9])==225);destroy(f);scenarios++;\n    /* Exercise')
(out/'fast-pixel-regression.c').write_text(test)
assert 'lmi_fast_state=calloc' in test and 'assert(strlen(logged[9])==225)' in test
original=(root/'tools/lmi-display-compositor-v56.c').read_text()
assert original.count('FN int original_fields')==1
adapted=original.replace('FN int original_fields','int original_fields').replace('original_fields','lmi_fast_original_fields').replace('lmi_compositor_frame','lmi_fast_original_frame')
(out/'original-compositor.c').write_text(adapted)
pixels=run('pixels',[out/'original-compositor.c',root/'tools/lmi-display-fast-v62.c',
           root/'tools/lmi-display-direct-plan-v61.c',root/'tools/lmi-display-pipeline-v51.c',out/'fast-pixel-regression.c'])
assert '21' in pixels
report=dict(result='PASS',fence_cases=fence_cases,pixel_cases=21,asan_ubsan=True,real_pthread_waiters=True,
            original_compositor_used=True,hardware_tested=False,commands=commands,
            sources={n:hashlib.sha256((root/'tools'/n).read_bytes()).hexdigest() for n in names},
            generated_sources={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['original-compositor.c','fast-pixel-regression.c']})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
