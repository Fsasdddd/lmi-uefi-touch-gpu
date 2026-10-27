"""Actual v64 backend + native frame wrappers, separate CPU/DMA pixels."""
from pathlib import Path
import hashlib,json,re,subprocess
root=Path(__file__).resolve().parents[1];tools=root/'tools'
out=root/'out/lmi-gpu-frame-v67-host';out.mkdir(exist_ok=True)
attempt=out/('attempt-'+str(len(list(out.glob('attempt-*')))+1));attempt.mkdir()
prior=root/'out/lmi-display-v62-host'
frozen=json.loads((prior/'result.json').read_text())
for n,d in frozen['sources'].items():assert hashlib.sha256((tools/n).read_bytes()).hexdigest()==d
for n,d in frozen['generated_sources'].items():assert hashlib.sha256((prior/n).read_bytes()).hexdigest()==d
prefix=(prior/'fast-pixel-regression.c').read_text().split('int main(void)',1)[0]
prefix=prefix.replace('void *IOMallocAligned(size_t n,size_t a)', 'static void allocated(void *,size_t);\nvoid *IOMallocAligned(size_t n,size_t a)')
prefix=prefix.replace('return p;}','allocated(p,n);return p;}',1)
prefix=prefix.replace('lmi_fast_draw(self,surfaces[0]', 'lmi_gpu_frame_draw(self,surfaces[0]')
prefix=prefix.replace('offset+pitch*2436u,4096','(offset+pitch*2436u+4095u)&~4095u,4096')
prefix=prefix.replace('sw(f->surface,LMI_SURF_info+0x1c,offset+pitch*2436u);',
                      'sw(f->surface,LMI_SURF_info+0x1c,(offset+pitch*2436u+4095u)&~4095u);')
prefix=prefix.replace('sw(f->surface,k+0x1c,BYTES);','sw(f->surface,k+0x1c,(BYTES+4095u)&~4095u);')
prefix='#include "lmi-gpu-frame-v67.h"\n#include "lmi-gpu-copy-v66.h"\n'+prefix
test=out/'check.c';test.write_text(prefix+(tools/'check-lmi-gpu-frame-v67.c').read_text())
pre=(tools/'lmi-display-preclean-v65.c').read_text()
pre=pre.replace('static int ready(', 'int lmi_frame_preclean_ready(').replace('ready(s)', 'lmi_frame_preclean_ready(s)')
pre=pre.replace('int ok=lmi_preclean_original_clean(s->context,&s->buffer);',
                'extern int lmi_gpu_frame_clean(void *,const struct lmi_frame_buffer *);\n    int ok=lmi_gpu_frame_clean(s->context,&s->buffer);')
(out/'preclean.c').write_text(pre)
flags=['clang','-std=c17','-O2','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-D_POSIX_C_SOURCE=200112L',
       '-Wno-misleading-indentation','-DLMI_PRECLEAN_HOST','-fsanitize=address,undefined',
       '-fno-sanitize-recover=all','-I'+str(tools)]
sources=[test,prior/'original-compositor.c',out/'preclean.c',*[tools/n for n in
         ['lmi-display-fast-v62.c','lmi-display-direct-plan-v61.c','lmi-display-pipeline-v51.c']]]
def run(source,label):
    c=subprocess.run([*flags,*map(str,sources),str(source),'-o',str(out/label)],capture_output=True,text=True)
    (attempt/(label+'-compile.log')).write_text(c.stdout+c.stderr)
    if c.returncode:print(c.stdout+c.stderr)
    c.check_returncode()
    result=subprocess.run([str(out/label)],capture_output=True,text=True,timeout=90)
    (attempt/(label+'.log')).write_text(result.stdout+result.stderr)
    return result
production=tools/'lmi-gpu-frame-v67.c'
result=run(production,'check');print(result.stdout+result.stderr,end='');result.check_returncode()
raw=production.read_text();mutations={
    'wrong-linear-length':('4544u*2436u/4):1136','4544u*2436u/4-1):1136'),
    'wrong-row-stride':('src+=pitch;dst+=4544;','src+=4544;dst+=4544;'),
    'missing-write-wait':('out[n++]=0x70928000;','out[n++]=0x70268000;'),
    'missing-post-invalidate':('!cache_sync(f->target,LMI_DMA_BUFFER_BYTES,0))uncertain(s,d);','0)uncertain(s,d);'),
    'source-cpu-published':('uint32_t n=commands(s,source->address,target->address);',
                          'cache_sync(s->pre.original.source,span,1);\n    uint32_t n=commands(s,source->address,target->address);'),
    'uncertain-copy-falls-back':('!cache_sync(f->target,LMI_DMA_BUFFER_BYTES,0))uncertain(s,d);',
                               '!cache_sync(f->target,LMI_DMA_BUFFER_BYTES,0))goto leave;'),
    'source-not-retained':('lmi_frame_retain(surface);s->retained++;','s->retained++;'),
    'rollback-not-unmapped':('lmi_desktop_unmap(address,span);redwood_gpu_address_free(address,span);',
                            'redwood_gpu_address_free(address,span);'),
    'credit-reused':('if(s)s->credit=0;\n    if(credit', 'if(s)s->credit=s->credit;\n    if(credit'),
    'credit-ignores-ready':('b==&s->pre.buffer && lmi_frame_preclean_ready(&s->pre)', 'b==&s->pre.buffer'),
    'journal-too-small':('IOMallocAligned(sizeof(struct lmi_gpu_frame_stats),alignment)',
                         'IOMallocAligned(sizeof(struct lmi_preclean_stats),alignment)'),
}
caught=[]
for label,(old,new) in mutations.items():
    assert raw.count(old)==1,(label,old)
    changed=attempt/(label+'.c');changed.write_text(raw.replace(old,new))
    m=run(changed,label);assert m.returncode!=0,('mutation survived',label);caught.append(label)
analysis=subprocess.run(['clang','--analyze','-std=c17','-I'+str(tools),str(production),
                         '-Xanalyzer','-analyzer-output=text'],capture_output=True,text=True,check=True)
(attempt/'static-analysis.log').write_text(analysis.stdout+analysis.stderr);assert not analysis.stdout+analysis.stderr
report=dict(result='PASS',scenarios=int(re.search(r'PASS: (\d+) integrated',result.stdout)[1]),
    actual_v64_backend=True,original_compositor_pipeline=True,separate_cpu_dma_views=True,
    independent_packet_decode=True,asan_ubsan=True,mutations_caught=caught,static_analysis=True,
    hardware_tested=False,performance_verified=False,attempt=str(attempt.relative_to(root)),
    sources={n:hashlib.sha256((tools/n).read_bytes()).hexdigest() for n in
             ['lmi-gpu-frame-v67.c','lmi-gpu-frame-v67.h','check-lmi-gpu-frame-v67.c','check-lmi-gpu-frame-v67.py',
              'lmi-gpu-desktop-v64.c','lmi-display-preclean-v65.c']},
    generated_sources={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['check.c','preclean.c']})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
