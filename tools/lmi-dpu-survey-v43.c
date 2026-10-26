/* lmi QSEED3-lite and MDSS stream inventory. No MMIO writes.
 * DT: SID 0x820/mask 0x402, Apps SMMU 0x15000000/1MB, VIG0 0x5000,
 * scaler +0xa00. MiCode 789514465a7cd3acbf70fa67f7e10fd8fde270bd.
 * This inventory is a prerequisite to owned-buffer DMA, not DMA validation.
 */
#ifndef LMI_DPU_SURVEY_HOST
#define SURVEY_CODE __attribute__((section("__TEXT_EXEC,__lmi_dpu"),noinline,used))
#define SURVEY_RO __attribute__((section("__TEXT_EXEC,__lmi_ro")))
#else
#define SURVEY_CODE
#define SURVEY_RO
extern unsigned int lmi_survey_test_read(unsigned long,unsigned int);
#endif
extern unsigned long ml_io_map(unsigned long,unsigned long);
extern int snprintf(char *,unsigned long,const char *,...);
extern void loader_log_line(const char *);
typedef unsigned int survey_u32;
typedef unsigned long survey_u64;
static const survey_u32 survey_streams[] SURVEY_RO={0x820,0x822,0xc20,0xc22};
static const survey_u32 survey_pipe_offsets[] SURVEY_RO={
    0,8,0xc,0x10,0x14,0x24,0x30,0x34,0x38,0x170,
    0x100,0x104,0x108,0x110,0x114,0x118,0x120,0x124,0x128,
    0xa00,0xa04,0xa0c,0xa10,0xa14,0xa18,0xa1c,0xa20,
    0xa40,0xa44,0xa48,0xa60,0xa90,0xa94,0xa98,0xa9c
};
static const survey_u32 survey_cb_offsets[] SURVEY_RO={
    0,0x10,0x20,0x24,0x28,0x2c,0x30,0x38,0x3c,0x58,0x60,0x64,0x68
};
static const char survey_reg_fmt[] SURVEY_RO="LMI_DPU_SURVEY space=%u offset=%x value=%x\n";
static const char survey_match_fmt[] SURVEY_RO="LMI_DPU_STREAM slot=%u smr=%x s2cr=%x covers=%x cb=%u\n";
static const char survey_end_fmt[] SURVEY_RO="LMI_DPU_SURVEY_END valid=%u slots=%u contexts=%u coverage=%u/%u/%u/%u writes=0\n";
static const char survey_start[] SURVEY_RO="LMI_DPU_SURVEY_BEGIN readonly=1\n";
static const char survey_failed[] SURVEY_RO="LMI_DPU_SURVEY_REFUSED mapping-or-geometry\n";

static SURVEY_CODE survey_u32 survey_read(survey_u64 base,survey_u32 offset)
{
#ifdef LMI_DPU_SURVEY_HOST
    return lmi_survey_test_read(base,offset);
#else
    survey_u32 value;
    __asm__ volatile("ldr %w0, [%1, %w2, uxtw]" : "=&r"(value) : "r"(base),"r"(offset) : "memory");
    return value;
#endif
}
static SURVEY_CODE void survey_emit(unsigned space,survey_u32 offset,survey_u32 value)
{
    char text[128];
    snprintf(text,sizeof(text),survey_reg_fmt,space,offset,value);
    loader_log_line(text);
}
SURVEY_CODE void lmi_dpu_pipeline_survey(survey_u64 mdss)
{
    if(!mdss) {loader_log_line(survey_failed);return;}
    loader_log_line(survey_start);
    for(unsigned n=0;n<sizeof(survey_pipe_offsets)/sizeof(survey_pipe_offsets[0]);n++) {
        survey_u32 offset=0x5000+survey_pipe_offsets[n];
        survey_emit(0,offset,survey_read(mdss,offset));
    }
    /* Mixer ownership, layer routing and completion ownership, read only. */
    for(unsigned n=0;n<6;n++) survey_emit(0,0x2000+4*n,survey_read(mdss,0x2000+4*n));
    survey_emit(0,0x1010,survey_read(mdss,0x1010));
    survey_emit(0,0x1014,survey_read(mdss,0x1014));
    survey_u64 smmu=ml_io_map(0x15000000ul,0x100000ul);
    if(!smmu) {loader_log_line(survey_failed);return;}
    survey_u32 control=survey_read(smmu,0),id0=survey_read(smmu,0x20),id1=survey_read(smmu,0x24);
    survey_emit(1,0,control);survey_emit(1,0x20,id0);survey_emit(1,0x24,id1);
    survey_emit(1,0x28,survey_read(smmu,0x28));survey_emit(1,0x48,survey_read(smmu,0x48));
    survey_u32 count=id0&255,contexts=id1&255;
    survey_u32 page=(id1&(1u<<31))?0x10000u:0x1000u;
    survey_u64 cb_start=(survey_u64)page<<(((id1>>28)&7)+1);
    if(control==~0u || !(id0&(1u<<27)) || !count || !contexts || contexts>128 ||
       cb_start+(survey_u64)contexts*page>0x100000ul) {loader_log_line(survey_failed);return;}
    unsigned coverage[4]={0},seen[128]={0};
    int wide=(control&8)!=0;
    for(unsigned i=0;i<count;i++) {
        survey_u32 smr=survey_read(smmu,0x800+4*i),s2cr=survey_read(smmu,0xc00+4*i);
        if(!(wide?(s2cr&0x400):(smr&0x80000000)))continue;
        survey_u32 mask=(smr>>16)&(wide?0xffff:0x7fff),sid=smr&(wide?0xffff:0x7fff),covers=0;
        for(unsigned n=0;n<4;n++)if(!((sid^survey_streams[n])&~mask)) {coverage[n]++;covers|=1u<<n;}
        if(!covers)continue;
        unsigned cb=s2cr&255;char text[128];
        snprintf(text,sizeof(text),survey_match_fmt,i,smr,s2cr,covers,cb);loader_log_line(text);
        if(((s2cr>>16)&3) || cb>=contexts || seen[cb])continue;
        seen[cb]=1;
        survey_emit(1,page+4*cb,survey_read(smmu,page+4*cb));
        survey_emit(1,page+0x800+4*cb,survey_read(smmu,page+0x800+4*cb));
        for(unsigned n=0;n<sizeof(survey_cb_offsets)/sizeof(survey_cb_offsets[0]);n++) {
            survey_u32 offset=(survey_u32)cb_start+cb*page+survey_cb_offsets[n];
            survey_emit(1,offset,survey_read(smmu,offset));
        }
    }
    char text[160];
    snprintf(text,sizeof(text),survey_end_fmt,
        (unsigned)(coverage[0]==1 && coverage[1]==1 && coverage[2]==1 && coverage[3]==1),
        count,contexts,coverage[0],coverage[1],coverage[2],coverage[3]);
    loader_log_line(text);
}
