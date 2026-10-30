/* Board evidence: out/lmi-cpu-epss/board-profile-b/profile.json. Registers and
 * parsing rules checked against MiCode lmi-q-oss qcom-cpufreq-hw.c. XO is the
 * DT's 38.4MHz xo_board / kona bi_tcxo divider 2. Source0 is not selectable
 * here: its exact parent rate is unnecessary to select a nonzero-source row.
 * Duplicate termination still decodes source0 as the vendor 300MHz fallback.
 * Selection is additionally bounded by this phone's Android cpuinfo maxima.
 * No post-prepare heap allocation, sleeping or locking is needed to restore. */
#include "lmi-cpu-epss.h"
static uint32_t khz(uint32_t raw)
{ return raw>>30 ? (raw&255u)*19200u : 300000u; }
static uint32_t cores(uint32_t raw) { return raw>>16&7u; }
int lmi_epss_select(struct lmi_epss_domain *d,uint32_t max_cores,uint32_t cap)
{
    if(!d || !max_cores || max_cores>7 || !cap)return 0;
    uint32_t previous=0,previous_cc=0,best=0,chosen=0,rows=0;
    for(uint32_t i=0;i<LMI_EPSS_ROWS;i++) {
        uint32_t raw=d->lut[i],freq=khz(raw),cc=cores(raw);
        if(i && freq==previous && cc==previous_cc) { rows=i;break; }
        previous=freq;previous_cc=cc;
        if(raw>>30 && freq && cc==max_cores && freq<=cap && freq>best) {
            best=freq;chosen=i;
        }
    }
    /* Refuse an unterminated, empty or unsupported table before any writes.
     * Preserve the complete request word, but accept only real LUT indices. */
    if(!rows || !best || d->original>=rows)return 0;
    if(khz(d->lut[d->original])>cap)return 0;
    d->rows=rows;d->target=chosen;d->khz=best;
    return 1;
}
int lmi_epss_prepare(struct lmi_epss_state *s,const struct lmi_epss_io *io)
{
    static const uint32_t cap[LMI_EPSS_DOMAINS]={1804800,2419200,2841600};
    if(!s || !io || !io->map || !io->read || !io->write || !io->barrier)return 0;
    if(s->prepared || s->dirty)return 0;
    s->io=*io;s->applied=0;s->changed=0;s->failed_domain=0;
    for(uint32_t i=0;i<LMI_EPSS_DOMAINS;i++) {
        struct lmi_epss_domain *d=&s->domain[i];s->failed_domain=i;
        d->base=io->map(io->context,LMI_EPSS_BASE+i*LMI_EPSS_SIZE,LMI_EPSS_SIZE);
        if(!d->base)return 0;
        for(uint32_t j=0;j<LMI_EPSS_ROWS;j++)
            if(!io->read(io->context,d->base,LMI_EPSS_LUT+4*j,&d->lut[j]))return 0;
        if(!io->read(io->context,d->base,LMI_EPSS_PERF,&d->original))return 0;
        if(!lmi_epss_select(d,4,cap[i]))return 0;
    }
    s->failed_domain=LMI_EPSS_DOMAINS;
    __atomic_store_n(&s->prepared,1,__ATOMIC_RELEASE);
    return 1;
}
int lmi_epss_restore(struct lmi_epss_state *s)
{
    if(!s)return 0;
    if(!__atomic_load_n(&s->dirty,__ATOMIC_ACQUIRE))return 1;
    const struct lmi_epss_io *io=&s->io;
    /* Other processors stopped. Reverse order; a failed restore remains dirty
     * and retryable. One domain's failure never skips remaining domains. */
    for(uint32_t n=LMI_EPSS_DOMAINS;n>0;n--) {
        uint32_t i=n-1,bit=1u<<i;
        if(!(__atomic_load_n(&s->dirty,__ATOMIC_ACQUIRE)&bit))continue;
        struct lmi_epss_domain *d=&s->domain[i];uint32_t got=~d->original;
        io->barrier(io->context); /* apply may have stopped before its post-store barrier */
        int wrote=io->write(io->context,d->base,LMI_EPSS_PERF,d->target);
        io->barrier(io->context);
        int read=io->read(io->context,d->base,LMI_EPSS_PERF,&got);
        d->restored_readback=got;
        if(wrote && read && got==d->original)
            __atomic_fetch_and(&s->dirty,~bit,__ATOMIC_RELEASE);
    }
    return __atomic_load_n(&s->dirty,__ATOMIC_ACQUIRE)==0;
}
int lmi_epss_apply(struct lmi_epss_state *s)
{
    if(!s || !__atomic_load_n(&s->prepared,__ATOMIC_ACQUIRE) || s->applied || s->dirty)return 0;
    const struct lmi_epss_io *io=&s->io;
    for(uint32_t i=0;i<LMI_EPSS_DOMAINS;i++) {
        struct lmi_epss_domain *d=&s->domain[i];uint32_t bit=1u<<i,got=0;
        s->failed_domain=i;
        if(d->original==d->target) { d->applied_readback=d->original;continue; }
        /* Journal before an attempted write, including writes reporting a
         * failure after having reached hardware. The barrier orders memory
         * publication before the MMIO store, also for panic/return recovery. */
        __atomic_fetch_or(&s->dirty,bit,__ATOMIC_RELEASE);
        io->barrier(io->context);
        int wrote=io->write(io->context,d->base,LMI_EPSS_PERF,d->target);
        io->barrier(io->context);
        int read=io->read(io->context,d->base,LMI_EPSS_PERF,&got);
        d->applied_readback=got;
        if(!wrote || !read || got!=d->target) {
            (void)lmi_epss_restore(s);return 0;
        }
        s->changed|=bit;
    }
    s->failed_domain=LMI_EPSS_DOMAINS;s->applied=1;return 1;
}
