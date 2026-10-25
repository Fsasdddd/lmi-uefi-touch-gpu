/* Caller holds CX/bus clocks and GMU RESET, and keeps the root wired.
 * No CBAR/SCTLR/stream writes, translation enable, or firmware execution. */
typedef unsigned int ctx_u32;
typedef unsigned long long ctx_u64;
extern void log_line(const char *);
extern void log_hex(ctx_u64);
#ifdef LMI_GPU_STAGE1_INIT
extern void delay(ctx_u32,ctx_u32);
#endif
#ifdef LMI_GPU_CONTEXT_HOST
extern ctx_u32 ctx_read(volatile ctx_u32 *);
extern void ctx_write(volatile ctx_u32 *,ctx_u32);
#else
static ctx_u32 __attribute__((noinline)) ctx_read(volatile ctx_u32 *address) {
    ctx_u64 value;
    __asm__ volatile("ldr %w0, [%1]\n\tuxtw %0, %w0"
        : "=&r"(value) : "r"(address) : "memory");
    return (ctx_u32)value;
}
static void __attribute__((noinline)) ctx_write(volatile ctx_u32 *address,ctx_u32 value) {
    __asm__ volatile("str %w0, [%1]" : "+r"(value) : "r"(address) : "memory");
    __asm__ volatile("dsb sy":::"memory");
}
#endif
static void ctx_field(const char *label,ctx_u64 value) {log_line(label);log_hex(value);}
/* 1=configured/restored; 2=refused or mismatch but safe to free;
 * 0=restoration unconfirmed: caller MUST retain backing until reset.
 * TBI0/1 are explicitly requested. Inputs remain untagged below 2^36,
 * matching the restricted GMU firmware/HFI map, never arbitrary addresses. */
int lmi_gmu_root_probe(ctx_u64 root,void *context) {
    volatile ctx_u32 *s=context;
    if(!s || !root || (root&4095) || (root>>36))return 2;
    if(ctx_read(&s[0x20/4])!=0x4c017e06 || ctx_read(&s[0x24/4])!=0x20000005 ||
       ctx_read(&s[0])&8)return 2;
    ctx_u32 control=ctx_read(&s[0x8000/4]),cbar=ctx_read(&s[0x1000/4]);
#ifdef LMI_GPU_STAGE1_INIT
    if(cbar)return 2;
#endif
    if((control&1)||ctx_read(&s[0x48/4])||ctx_read(&s[0x8058/4]))return 2;
    for(ctx_u32 i=0;i<6;i++)if(ctx_read(&s[(0x800+4*i)/4])&0x80000000u)return 2;
    const ctx_u32 offsets[]={0x1800,0x8010,0x8030,0x8020,0x8024,0x8028,0x802c,0x8038,0x803c};
    ctx_u32 requested[]={1,0x38071,0x803519,(ctx_u32)root,(ctx_u32)(root>>32),0,0,0xf404ff44,0};
#ifdef LMI_GPU_STAGE1_INIT
    /* Vendor non-dynamic ASID = cbndx+1. No translation/stream enable. */
    requested[4]|=0x10000;
#endif
    ctx_u32 original[9],actual[9],restored[9];
    for(ctx_u32 i=0;i<9;i++)original[i]=ctx_read(&s[offsets[i]/4]);
    if(original[0])return 2;
    for(ctx_u32 i=0;i<9;i++)if(original[i]!=ctx_read(&s[offsets[i]/4]))return 2;
    ctx_field("LMI_GPU_WIRED_CONTEXT_ROOT\n",root);
    for(ctx_u32 i=0;i<9;i++) {
        ctx_write(&s[offsets[i]/4],requested[i]);
#ifdef LMI_GPU_STAGE1_INIT
        if(!i)ctx_write(&s[0x1000/4],0x1f300);
#endif
    }
    for(ctx_u32 i=0;i<9;i++)actual[i]=ctx_read(&s[offsets[i]/4]);
    ctx_u32 state[4];
    const ctx_u32 status_offsets[]={0x8000,0x1000,0x48,0x8058};
    for(ctx_u32 i=0;i<4;i++)state[i]=ctx_read(&s[status_offsets[i]/4]);
    /* ARM IHI0062D.c16.5.9 pp299-300: FSR[10:9] is the read-only
     * format field generated from CBA2R.VA64/TCR.EAE, not fault status.
     * Require the exact AArch64 format and NO other status bits. */
    ctx_u32 expected_cbar=cbar;
#ifdef LMI_GPU_STAGE1_INIT
    /* Linux destroy_domain_context disables SCTLR; it does not write
     * unsupported stage2 TYPE0 to uninitialize CBAR. Leave stage1 TYPE
     * inert with M0/no routes until bounded reboot; never claim literal
     * CBAR restoration. No DMA/translation is started in this profile. */
    expected_cbar=0x1f300;
#endif
    ctx_u32 during=state[0]==control && state[1]==expected_cbar && !state[2] && state[3]==0x400;
    for(ctx_u32 i=0;i<6;i++)during&=!(ctx_read(&s[(0x800+4*i)/4])&0x80000000u);
#ifdef LMI_GPU_STAGE1_INIT
    ctx_u32 synced=0;
    if(during) {
        ctx_write(&s[0x8610/4],1);
        ctx_write(&s[0x87f0/4],0);
        for(ctx_u32 n=0;n<1000;n++) {
            if(!(ctx_read(&s[0x87f4/4])&1)) {synced=1;break;}
            delay(1,1000);
        }
    }
    ctx_field("LMI_GPU_STAGE1_LOCAL_SYNC\n",synced);
    during&=synced;
#endif
    /* TCR2 before TTBR because it controls ASID access; format restored last. */
    for(ctx_u32 i=1;i<9;i++)ctx_write(&s[offsets[i]/4],original[i]);
    ctx_write(&s[offsets[0]/4],original[0]);
    for(ctx_u32 i=0;i<9;i++)restored[i]=ctx_read(&s[offsets[i]/4]);
    ctx_u32 safe=1,matched=during;
    for(ctx_u32 i=0;i<9;i++) {
        safe&=original[i]==restored[i];matched&=requested[i]==actual[i];
        ctx_field("LMI_GPU_WIRED_CONTEXT_OFFSET\n",offsets[i]);
        ctx_field("LMI_GPU_WIRED_CONTEXT_BEFORE\n",original[i]);
        ctx_field("LMI_GPU_WIRED_CONTEXT_REQUESTED\n",requested[i]);
        ctx_field("LMI_GPU_WIRED_CONTEXT_ACTUAL\n",actual[i]);
        ctx_field("LMI_GPU_WIRED_CONTEXT_RESTORED\n",restored[i]);
    }
    safe&=ctx_read(&s[0x8000/4])==control;
    safe&=ctx_read(&s[0x1000/4])==expected_cbar;
    safe&=ctx_read(&s[0x48/4])==0 && ctx_read(&s[0x8058/4])==0;
    for(ctx_u32 i=0;i<6;i++)safe&=!(ctx_read(&s[(0x800+4*i)/4])&0x80000000u);
#ifdef LMI_GPU_STAGE1_INIT
    if(!synced)safe=0;
    ctx_field("LMI_GPU_STAGE1_CBAR_RETAINED\n",ctx_read(&s[0x1000/4]));
#endif
    for(ctx_u32 i=0;i<4;i++)ctx_field("LMI_GPU_WIRED_CONTEXT_DURING_VALUE\n",state[i]);
    ctx_field("LMI_GPU_WIRED_CONTEXT_DURING_SAFE\n",during);
    ctx_field("LMI_GPU_WIRED_CONTEXT_SAFE\n",safe);
    ctx_field("LMI_GPU_WIRED_CONTEXT_MATCHED\n",matched);
    return safe?(matched?1:2):0;
}
