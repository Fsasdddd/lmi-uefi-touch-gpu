"""Create separate v69 sources; the frozen v68 release is never edited."""
from pathlib import Path
root=Path(__file__).resolve().parents[1];tools=root/'tools'
def write(name,text):
    p=tools/name;assert not p.exists(),p;p.write_text(text)
h=(tools/'lmi-gpu-frame-v68.h').read_text().replace('LMI_GPU_FRAME_V68_H','LMI_GPU_CACHE_V69_H')
h=h.replace('    uint64_t retained,released,fallback,skipped_clean,copy_ticks,held;',
'''    uint64_t retained,released,fallback,skipped_clean,copy_ticks,held;
    /* Private targets have one CPU presenter. A successful post-invalidate
     * leaves no dirty target lines. Ordinary/failed frames revoke both bits. */
    struct lmi_display_pipeline *clean_owner;
    unsigned clean_mask;
    uint64_t target_prepared,target_reused,dirty_resets,target_bytes_saved,target_prepare_ticks;''')
write('lmi-gpu-cache-v69.h',h)
c=(tools/'lmi-gpu-frame-v68.c').read_text().replace('"lmi-gpu-frame-v68.h"','"lmi-gpu-cache-v69.h"')
c=c.replace('static __attribute__((noinline)) int copy(','''static void dirty(struct lmi_gpu_frame_stats *s)
{
    if(s->clean_mask)s->dirty_resets++;
    s->clean_mask=0;
}
static __attribute__((noinline)) int copy(''')
c=c.replace('''    /* Discard no dirty CPU bytes: publish then invalidate the entire owned
     * destination before its writer changes. Source is GPU-produced and is
     * NEVER CPU-published here, which could overwrite fresh GPU pixels.
     */
    if(!cache_sync(f->target,LMI_DMA_BUFFER_BYTES,1) || !cache_sync(f->target,LMI_DMA_BUFFER_BYTES,0) ||
       !cache_sync(s->commands.pixels,n*4,1) ||''','''    /* Reuse only this exact private target after a successful GPU write and
     * post-invalidate. No compositor preservation/bootstrap/padding writer
     * runs before the qualified draw (the frozen fast wrapper sets latest).
     * CPU fallback, a no-draw swap, failed frame or owner change revokes both
     * bits. Keep post-invalidate for ordinary-frame reads and speculation.
     * Source is GPU-produced and must NEVER be CPU-published here.
     */
    unsigned reused=!!(s->clean_mask&(1u<<index));
    uint64_t prepare_began=lmi_frame_ticks();
    if(!reused && (!cache_sync(f->target,LMI_DMA_BUFFER_BYTES,1) ||
                  !cache_sync(f->target,LMI_DMA_BUFFER_BYTES,0)))goto leave;
    uint64_t prepare_ticks=lmi_frame_ticks()-prepare_began;
    if(!cache_sync(s->commands.pixels,n*4,1) ||''')
c=c.replace('''    s->copy_ticks+=lmi_frame_ticks()-began;
    s->draws++;''','''    s->copy_ticks+=lmi_frame_ticks()-began;
    s->clean_mask|=1u<<index;
    if(reused) {s->target_reused++;s->target_bytes_saved+=2ull*LMI_DMA_BUFFER_BYTES;}
    else s->target_prepared++;
    s->target_prepare_ticks+=prepare_ticks;
    s->draws++;''')
c=c.replace('''        s->credit=0;s->fallback++;''','''        dirty(s);s->credit=0;s->fallback++;''')
c=c.replace('''    if(s) {s->credit=0;s->written=0;s->completed_target=0;s->pipeline=p;}''','''    if(s) {
        if(s->clean_owner!=p) {dirty(s);s->clean_owner=p;}
        s->credit=0;s->written=0;s->completed_target=0;s->pipeline=p;
    }''')
c=c.replace('''    if(s && result==1 && s->written)s->frames++;
    if(s)s->credit=0;''','''    if(s && result==1 && s->written)s->frames++;
    if(s) {
        if(result!=1 || !s->written)dirty(s);
        s->credit=0;
    }''')
c=c.replace('''        lmi_frame_emit("LMI_GPU_BLIT_LIFETIME",&s->evicted,7);''','''        lmi_frame_emit("LMI_GPU_BLIT_LIFETIME",&s->evicted,7);
        lmi_frame_emit("LMI_GPU_TARGET_CACHE",&s->target_prepared,5);''')
assert 'target_prepared++' in c and 'prepare_ticks=' in c
write('lmi-gpu-cache-v69.c',c)
