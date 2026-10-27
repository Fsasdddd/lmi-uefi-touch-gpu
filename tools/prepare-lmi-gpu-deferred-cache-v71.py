"""Derive deferred CPU ownership transfers from frozen asynchronous v70."""
from pathlib import Path
r=Path(__file__).resolve().parents[1];t=r/'tools'
def write(n,s):
    p=t/n;assert not p.exists(),p;p.write_text(s)
h=(t/'lmi-gpu-overlap-v70.h').read_text().replace('LMI_GPU_OVERLAP_V70_H','LMI_GPU_DEFERRED_CACHE_V71_H')
h=h.replace('    uint64_t queued,finished,wait_polls,busy_polls,later_queued,unlocked_ticks;', '''    uint64_t queued,finished,wait_polls,busy_polls,later_queued,unlocked_ticks;
    unsigned gpu_owned_mask;
    uint64_t post_deferred,cpu_sync_targets,cpu_sync_bytes,cpu_sync_ticks;''')
write('lmi-gpu-deferred-cache-v71.h',h)
c=(t/'lmi-gpu-overlap-v70.c').read_text().replace('"lmi-gpu-overlap-v70.h"','"lmi-gpu-deferred-cache-v71.h"')
c=c.replace('extern int lmi_frame_done(uint32_t);', '''extern int lmi_frame_done(uint32_t);
extern int lmi_frame_full_pixels(const unsigned char *,void **,struct lmi_direct_plan *,struct lmi_fast_stats *);''')
at=c.index('static void dirty(')
c=c[:at]+'''/* GPU-written pixels need no CPU cache publication for DPU DMA. Transfer
 * both targets back BEFORE a CPU preservation/read/write can run. Invalidation
 * never publishes stale speculative clean CPU lines over newer GPU pixels.
 * One presenter owns this mask; no allocation is freed during the RAM run. */
static __attribute__((noinline)) void cpu_access(struct lmi_gpu_frame_stats *s)
{
    if(!s->gpu_owned_mask)return;
    uint64_t began=lmi_frame_ticks();
    for(unsigned n=0;n<2;n++)if(s->gpu_owned_mask&(1u<<n)) {
        if(!s->target[n].address || !cache_sync(s->target[n].pixels,LMI_DMA_BUFFER_BYTES,0)) {
            IOLockLock(lmi_frame_gpu_lock);uncertain(s,s->pending.backend);
        }
        s->gpu_owned_mask&=~(1u<<n);s->cpu_sync_targets++;
        s->cpu_sync_bytes+=LMI_DMA_BUFFER_BYTES;
    }
    s->cpu_sync_ticks+=lmi_frame_ticks()-began;
}
/* Mirror the frozen fast wrapper's exact admission BEFORE its compositor
 * can read the previous target. Decode via its actual compiled pixels helper;
 * no client pointer or alternate ABI is admitted here. A later mapping/copy
 * refusal transfers ownership in draw() before the CPU fallback writes. */
static __attribute__((noinline)) int full_frame(struct lmi_gpu_frame_stats *s,
    struct lmi_compositor *c,struct lmi_display_pipeline *p,const unsigned char *swap,
    void **surfaces,unsigned *index,uint64_t *ticket)
{
    struct lmi_direct_plan plan;
    if(s->pre.original.active || !c || !c->initialized || !p || !p->initialized ||
       p->failed || p->stopping || p->detached || p->serial==UINT64_MAX || !index || !ticket ||
       !lmi_fast_original_fields(c) || !lmi_frame_full_pixels(swap,surfaces,&plan,&s->pre.original))return 0;
    for(unsigned n=0;n<2;n++)if(p->state[n]==LMI_FREE) {
        const struct lmi_frame_buffer *b=p->buffer+n;
        return b->width==1125 && b->height==2436 && b->pitch==4544 && b->bytes>=4544u*2436u &&
            b->bytes<=UINTPTR_MAX-b->pixels &&
            (plan.pixels+plan.bytes<=b->pixels || b->pixels+b->bytes<=plan.pixels);
    }
    return 0;
}
'''+c[at:]
old='''               !lmi_blit_completed((void *)s->state.pixels) ||
               !cache_sync(s->pending.target,LMI_DMA_BUFFER_BYTES,0))uncertain(s,d);'''
new='''               !lmi_blit_completed((void *)s->state.pixels))uncertain(s,d);
            s->gpu_owned_mask|=1u<<s->pending.index;s->post_deferred++;'''
assert c.count(old)==1;c=c.replace(old,new)
c=c.replace('leaves no dirty target lines. Ordinary/failed frames revoke both bits.',
            'leaves no dirty target lines. CPU access requires a transfer first.')
c=c.replace('successful GPU write and\n     * post-invalidate.', 'successful GPU write with\n     * no intervening CPU writer.')
c=c.replace('bits. Keep post-invalidate for ordinary-frame reads and speculation.',
            'bits after transferring ownership for ordinary-frame reads/writes.')
c=c.replace('        dirty(s);s->credit=0;s->fallback++;', '        cpu_access(s);dirty(s);s->credit=0;s->fallback++;')
c=c.replace('''        if(s->clean_owner!=p) {dirty(s);s->clean_owner=p;}
        s->credit=0;''','''        if(s->clean_owner!=p) {cpu_access(s);dirty(s);s->clean_owner=p;}
        if(s->gpu_owned_mask && !full_frame(s,c,p,swap,surfaces,index,ticket))cpu_access(s);
        s->credit=0;''')
c=c.replace('''        if(result!=1 || !s->written)dirty(s);
        s->credit=0;''','''        if(result!=1 || !s->written) {cpu_access(s);dirty(s);}
        /* No early clean credit: ordinary submit may CPU-clean this target. */
        else if(s->credit)cpu_access(s);
        s->credit=0;''')
c=c.replace('''    return lmi_preclean_original_clean(context,b);
}''','''    if(s)cpu_access(s);
    return lmi_preclean_original_clean(context,b);
}''')
c=c.replace('''        lmi_frame_emit("LMI_GPU_COPY_PENDING",&pending,1);''','''        lmi_frame_emit("LMI_GPU_COPY_PENDING",&pending,1);
        lmi_frame_emit("LMI_GPU_CPU_TRANSFER",&s->post_deferred,4);
        const uint64_t owned=s->gpu_owned_mask;
        lmi_frame_emit("LMI_GPU_CPU_OWNED",&owned,1);''')
write('lmi-gpu-deferred-cache-v71.c',c)
