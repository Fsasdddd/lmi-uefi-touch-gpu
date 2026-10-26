/* Fixed read-only lmi DPU census. Offsets: live.dts and MiCode lmi-q-oss
 * 789514465a7cd3acbf70fa67f7e10fd8fde270bd, sde_hw_{ctl,sspp,intf,pingpong}.c.
 * No interrupt status/acknowledge accesses, clocks, resets, or register writes.
 * Runs only in resident UEFI before/after XNU, never alongside a live kernel.
 */
#ifndef LMI_DISPLAY_CENSUS_HOST
static uint32_t lmi_display_read(uint32_t offset)
{
    return *(volatile const uint32_t *)(uintptr_t)(0x0ae00000ULL + offset);
}
static uint64_t lmi_display_tick(void) { return READ_SYSREG(CNTVCT_EL0); }
static void lmi_display_pause(void) { BS->stall(1000); }
#define lmi_display_emit print
#endif

static void lmi_display_block(const char *stage, const char *block,
    uint32_t base, const uint32_t *offsets, unsigned count)
{
    for (unsigned i=0;i<count;i++) {
        uint32_t offset=base+offsets[i];
        lmi_display_emit("LMI_DPU_REG %s %s offset=%x value=%x\n", stage,block,
            (uint64_t)offset,(uint64_t)lmi_display_read(offset));
    }
}

static void lmi_display_census(const char *stage, int permitted)
{
    static const uint32_t ctl[]={0x2000,0x2200,0x2400,0x2600,0x2800,0x2a00};
    static const uint32_t sspp[]={0x5000,0x7000,0x9000,0xb000,0x25000,0x27000,0x29000,0x2b000};
    static const uint32_t intf[]={0x6b000,0x6b800,0x6c000,0x6c800};
    static const uint32_t pp[]={0x71000,0x71800,0x72000,0x72800,0x73000,0x73800};
    static const uint32_t ctl_regs[]={0,0x14,0x18,0x1c,0x64,0xf4};
    static const uint32_t src_regs[]={0,8,0xc,0x10,0x14,0x24,0x30,0x38};
    static const uint32_t intf_regs[]={0,4,0xac,0xb0,0x26c,0x280,0x284,0x288,0x28c,0x294,0x298,0x2ac,0x2b0,0x2b4};
    static const uint32_t pp_regs[]={0,4,8,0xc,0x14,0x28,0x2c,0x30};
    struct sample { uint64_t at; uint32_t pp[6],intf[4],frames[4]; } samples[24];
    if (!permitted) return;
    lmi_display_emit("LMI_DPU_BEGIN %s readonly=1\n",stage);
    for (unsigned i=0;i<6;i++) lmi_display_block(stage,"CTL",ctl[i],ctl_regs,6);
    for (unsigned i=0;i<8;i++) lmi_display_block(stage,"SSPP",sspp[i],src_regs,8);
    for (unsigned i=0;i<4;i++) lmi_display_block(stage,"INTF",intf[i],intf_regs,14);
    for (unsigned i=0;i<6;i++) lmi_display_block(stage,"PP",pp[i],pp_regs,8);
    /* Sample before printing, so framebuffer console/log formatting cannot
     * stretch each 1ms interval. Raw counter ticks retain actual intervals. */
    for (unsigned n=0;n<24;n++) {
        samples[n].at=lmi_display_tick();
        for (unsigned i=0;i<6;i++) samples[n].pp[i]=lmi_display_read(pp[i]+0x2c);
        for (unsigned i=0;i<4;i++) {
            samples[n].intf[i]=lmi_display_read(intf[i]+0x2b0);
            samples[n].frames[i]=lmi_display_read(intf[i]+0xac);
        }
        if (n+1<24) lmi_display_pause();
    }
    for (unsigned n=0;n<24;n++) {
        for (unsigned i=0;i<6;i++) lmi_display_emit("LMI_DPU_TIME %s ticks=%x offset=%x value=%x\n",
            stage,samples[n].at,(uint64_t)(pp[i]+0x2c),(uint64_t)samples[n].pp[i]);
        for (unsigned i=0;i<4;i++) {
            lmi_display_emit("LMI_DPU_TIME %s ticks=%x offset=%x value=%x\n",
                stage,samples[n].at,(uint64_t)(intf[i]+0x2b0),(uint64_t)samples[n].intf[i]);
            lmi_display_emit("LMI_DPU_TIME %s ticks=%x offset=%x value=%x\n",
                stage,samples[n].at,(uint64_t)(intf[i]+0xac),(uint64_t)samples[n].frames[i]);
        }
    }
    lmi_display_emit("LMI_DPU_END %s\n",stage);
}
