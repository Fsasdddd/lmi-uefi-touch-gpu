/* Checkpoint guard, using the pinned gic_v3_irq.c register
 * layout. IRQ-enabled stages temporarily mask resident SPI/PPI enables and
 * restore them. Opt-in checkpoint63 SMP also saves/restores owned SGIs 0/1.
 * No SPI routing/priority, physical timer, distributor-mode
 * or WAKER writes; resident SPI pending state is never acknowledged/cleared.
 * Refuse a sleeping redistributor, active virtual timer, nonzero active
 * priority, or a distributor that XNU would have to reconfigure.
 */
static struct {
    uint64_t rd, sre, ap1;
    uint32_t ctlr, waker, group, modifier, enabled, pending, config, pending_cleared;
    uint32_t seen_group, seen_enabled;
    uint8_t priority, seen_priority;
    int armed, restore, restored, matches;
    uint32_t late, isolated, isolation_ok, banks, spi_enabled[32];
    uint64_t spi_config_hash;
} lmi_gic;
#ifndef LMI_SMP_RETURN
#define LMI_SMP_RETURN 0
#endif
static uint32_t lmi_local_irqs;
static uint8_t lmi_sgi_priority[2];
#define LMI_VTIMER (1u << 27)
#define LMI_GIC32(p) (*(volatile uint32_t *)(uintptr_t)(p))
#define LMI_GIC8(p) (*(volatile uint8_t *)(uintptr_t)(p))

/* Read-only fingerprint of non-pending SPI configuration. No IAR reads:
 * pending interrupts of resident firmware must not be acknowledged or cleared.
 */
static uint64_t lmi_spi_config_hash(void)
{
    uint64_t h=1469598103934665603ULL;
    for (uint32_t bank=1; bank<lmi_gic.banks; bank++) {
        h=(h^LMI_GIC32(0x17a00080+bank*4))*1099511628211ULL;
        h=(h^LMI_GIC32(0x17a00d00+bank*4))*1099511628211ULL;
    }
    uint32_t limit=lmi_gic.banks*32;
    if (limit>1020) limit=1020;
    for (uint32_t id=32; id<limit; id++) {
        h=(h^LMI_GIC8(0x17a00400+id))*1099511628211ULL;
        if ((id&15)==0) h=(h^LMI_GIC32(0x17a00c00+(id/16)*4))*1099511628211ULL;
        h=(h^*(volatile uint64_t *)(uintptr_t)(0x17a06000+(uint64_t)id*8))*1099511628211ULL;
    }
    return h;
}

static int lmi_gic_capture(uint64_t checkpoint)
{
    lmi_local_irqs=LMI_VTIMER | ((LMI_SMP_RETURN && checkpoint==63)?3u:0u);
    lmi_gic.armed=0;
    lmi_gic.isolated=0;
    lmi_gic.late=(checkpoint==57 || checkpoint==58 || checkpoint==59 || checkpoint==60 || checkpoint==61 || checkpoint==62 || checkpoint==63);
    if (checkpoint!=50 && checkpoint!=21 && checkpoint!=52 && checkpoint!=53 && checkpoint!=54 && checkpoint!=55 && checkpoint!=56 && !lmi_gic.late) return 1;
    uint64_t mpidr=READ_SYSREG(MPIDR_EL1);
    uint32_t affinity=(uint32_t)(((mpidr>>32)&255)<<24 | (mpidr&0xffffff));
    uint64_t rd=0;
    for (uint64_t p=0x17a60000; p<0x17b60000; p+=0x20000) {
        uint64_t typer=*(volatile uint64_t *)(uintptr_t)(p+8);
        if ((uint32_t)(typer>>32)==affinity) { rd=p; break; }
        if (typer&16) break;
    }
    if (!rd) { print("lmi GIC guard: no matching redistributor\n"); return 0; }
    lmi_gic.rd=rd;
    lmi_gic.ctlr=LMI_GIC32(0x17a00000);
    lmi_gic.waker=LMI_GIC32(rd+0x14);
    lmi_gic.sre=READ_SYSREG(ICC_SRE_EL1);
    lmi_gic.ap1=READ_SYSREG(ICC_AP1R0_EL1);
    lmi_gic.group=LMI_GIC32(rd+0x10080);
    lmi_gic.modifier=LMI_GIC32(rd+0x10d00);
    lmi_gic.enabled=LMI_GIC32(rd+0x10100);
    lmi_gic.priority=LMI_GIC8(rd+0x1041b);
    lmi_gic.pending=LMI_GIC32(rd+0x10200)&lmi_local_irqs;
    for(unsigned i=0;i<2;i++)lmi_sgi_priority[i]=LMI_GIC8(rd+0x10400+i);
    lmi_gic.config=LMI_GIC32(rd+0x10c04);
    uint32_t active=LMI_GIC32(rd+0x10300);
    print("lmi GIC snapshot: rd=%x ctlr=%x waker=%x sre=%x ap1=%x group=%x modifier=%x enabled=%x priority=%x active=%x\n",
          rd,(uint64_t)lmi_gic.ctlr,(uint64_t)lmi_gic.waker,lmi_gic.sre,lmi_gic.ap1,
          (uint64_t)lmi_gic.group,(uint64_t)lmi_gic.modifier,(uint64_t)lmi_gic.enabled,
          (uint64_t)lmi_gic.priority,(uint64_t)active);
    if ((lmi_gic.ctlr&0x12)!=0x12 || (lmi_gic.waker&6) || !(lmi_gic.sre&1) ||
        lmi_gic.ap1 || (active&lmi_local_irqs)) {
        print("lmi GIC guard: unsupported resident state; refusing kernel entry\n");
        return 0;
    }
    print("lmi timer snapshot: ctl=%x pending=%x config=%x\n",READ_SYSREG(CNTV_CTL_EL0),(uint64_t)lmi_gic.pending,(uint64_t)lmi_gic.config);
    if (checkpoint!=50 && (lmi_gic.pending || (lmi_gic.config&(2u<<22)))) {
        print("lmi GIC guard: pending or edge-configured virtual timer; refusing kernel entry\n");
        return 0;
    }
    lmi_gic.restore=(checkpoint!=50);
    lmi_gic.restored=lmi_gic.matches=0;
    lmi_gic.armed=1;
    return 1;
}

static int lmi_gic_isolate(void)
{
    if (!lmi_gic.late) return 1;
    uint64_t daif=READ_SYSREG(DAIF),rd=lmi_gic.rd;
    __asm__ volatile("msr daifset, #15" ::: "memory");
    lmi_gic.banks=(LMI_GIC32(0x17a00004)&31)+1;
    lmi_gic.enabled=LMI_GIC32(rd+0x10100);
    /* The current processor must not be inside a resident IRQ handler. */
    int active=(READ_SYSREG(ICC_AP1R0_EL1)!=0 || LMI_GIC32(rd+0x10300)!=0);
    for (uint32_t bank=1; bank<lmi_gic.banks; bank++) {
        lmi_gic.spi_enabled[bank]=LMI_GIC32(0x17a00100+bank*4);
        if (LMI_GIC32(0x17a00300+bank*4)) active=1;
    }
    if (active) {
        __asm__ volatile("msr daif, %0"::"r"(daif):"memory");
        print("lmi IRQ isolation refused: active resident interrupt\n");
        return 0;
    }
    lmi_gic.spi_config_hash=lmi_spi_config_hash();
    lmi_gic.isolated=1;
    LMI_GIC32(rd+0x10180)=lmi_gic.enabled&~LMI_VTIMER;
    for (uint32_t bank=1; bank<lmi_gic.banks; bank++)
        LMI_GIC32(0x17a00180+bank*4)=lmi_gic.spi_enabled[bank];
    __asm__ volatile("dsb sy" ::: "memory");
    for (unsigned n=0; n<1000000 && ((LMI_GIC32(0x17a00000)&0x80000000u) || (LMI_GIC32(rd)&8)); n++) {}
    int ok=!(LMI_GIC32(rd+0x10100)&~LMI_VTIMER);
    for (uint32_t bank=1; bank<lmi_gic.banks; bank++)
        if (LMI_GIC32(0x17a00100+bank*4)) ok=0;
    lmi_gic.isolation_ok=ok;
    print("lmi IRQ isolated: banks=%d ppi=%x spi-mask-ok=%d config=%x\n",(uint64_t)lmi_gic.banks,
          (uint64_t)LMI_GIC32(rd+0x10100),(uint64_t)ok,lmi_gic.spi_config_hash);
    if (!ok) {
        /* No kernel was entered. Restore only the forwarding masks changed above. */
        LMI_GIC32(rd+0x10100)=lmi_gic.enabled;
        for (uint32_t bank=1; bank<lmi_gic.banks; bank++)
            LMI_GIC32(0x17a00100+bank*4)=lmi_gic.spi_enabled[bank];
        __asm__ volatile("dsb sy\n msr daif, %0"::"r"(daif):"memory");
        return 0;
    }
    __asm__ volatile("" ::: "memory");
    clean_dcache((uint64_t)(uintptr_t)&lmi_gic,(uint64_t)(uintptr_t)&lmi_gic+sizeof(lmi_gic));
    clean_dcache((uint64_t)(uintptr_t)&lmi_local_irqs,(uint64_t)(uintptr_t)&lmi_local_irqs+sizeof(lmi_local_irqs));
    clean_dcache((uint64_t)(uintptr_t)&lmi_sgi_priority,(uint64_t)(uintptr_t)&lmi_sgi_priority+sizeof(lmi_sgi_priority));
    clean_dcache((uint64_t)(uintptr_t)log_buf,(uint64_t)(uintptr_t)log_buf+log_len);
    clean_dcache((uint64_t)(uintptr_t)&log_len,(uint64_t)(uintptr_t)&log_len+sizeof(log_len));
    return 1; /* DAIF stays masked until the native kernel explicitly enables IRQs. */
}

/* Called by the return stub with UEFI mappings/stack restored and DAIF masked.
 * The returned log/reason and all UEFI nonvolatile registers are already saved.
 * This function makes no firmware calls and allocates no memory.
 */
__attribute__((used,noinline)) int lmi_gic_restore(void)
{
    if (!lmi_gic.armed) return 1;
    uint64_t rd=lmi_gic.rd;
    lmi_gic.seen_group=LMI_GIC32(rd+0x10080);
    lmi_gic.seen_enabled=LMI_GIC32(rd+0x10100);
    lmi_gic.seen_priority=LMI_GIC8(rd+0x1041b);
    if (lmi_gic.restore) {
        uint64_t timer=READ_SYSREG(CNTV_CTL_EL0);
        __asm__ volatile("msr cntv_ctl_el0, %0\n isb"::"r"((uint64_t)2));
        LMI_GIC32(rd+0x10180)=lmi_local_irqs;
        __asm__ volatile("dsb sy");
        /* Wait for the redistributor to finish disabling the PPI. */
        for (unsigned n=0; n<1000000 && (LMI_GIC32(rd)&8); n++) {}
        /* No software-pending timer at guarded entry, and PPI 27 is level
         * sensitive. Disable its source before clearing this run's pending
         * state. The stub saved/restored UEFI's original compare deadline;
         * an elapsed original deadline may naturally become pending again
         * when the resident timer is restored below. */
        LMI_GIC32(rd+0x10280)=lmi_local_irqs;
        __asm__ volatile("dsb sy\n isb");
        for (unsigned n=0; n<1000000 && (LMI_GIC32(rd+0x10200)&lmi_local_irqs); n++) {}
        lmi_gic.pending_cleared=!(LMI_GIC32(rd+0x10200)&lmi_local_irqs);
        LMI_GIC32(rd+0x10080)=(LMI_GIC32(rd+0x10080)&~lmi_local_irqs)|(lmi_gic.group&lmi_local_irqs);
        LMI_GIC32(rd+0x10d00)=(LMI_GIC32(rd+0x10d00)&~lmi_local_irqs)|(lmi_gic.modifier&lmi_local_irqs);
        LMI_GIC8(rd+0x1041b)=lmi_gic.priority;
        if(lmi_local_irqs&3u)for(unsigned i=0;i<2;i++)LMI_GIC8(rd+0x10400+i)=lmi_sgi_priority[i];
        LMI_GIC32(rd+0x10100)=lmi_gic.enabled&lmi_local_irqs;
        __asm__ volatile("msr icc_ap1r0_el1, %0\n dsb sy\n isb"::"r"(lmi_gic.ap1));
        __asm__ volatile("msr cntv_ctl_el0, %0\n isb"::"r"(timer));
        lmi_gic.restored=1;
    }
    lmi_gic.matches=(LMI_GIC32(0x17a00000)==lmi_gic.ctlr &&
        LMI_GIC32(rd+0x14)==lmi_gic.waker && READ_SYSREG(ICC_SRE_EL1)==lmi_gic.sre &&
        READ_SYSREG(ICC_AP1R0_EL1)==lmi_gic.ap1 &&
        ((LMI_GIC32(rd+0x10080)^lmi_gic.group)&lmi_local_irqs)==0 &&
        ((LMI_GIC32(rd+0x10d00)^lmi_gic.modifier)&lmi_local_irqs)==0 &&
        ((LMI_GIC32(rd+0x10100)^lmi_gic.enabled)&lmi_local_irqs)==0 &&
        LMI_GIC8(rd+0x1041b)==lmi_gic.priority);
    if(lmi_local_irqs&3u)for(unsigned i=0;i<2;i++)
        if(LMI_GIC8(rd+0x10400+i)!=lmi_sgi_priority[i])lmi_gic.matches=0;
    if (lmi_gic.restore && ((LMI_GIC32(rd)&8) || !lmi_gic.pending_cleared ||
        (LMI_GIC32(rd+0x10300)&lmi_local_irqs) ||
        ((LMI_GIC32(rd+0x10c04)^lmi_gic.config)&(3u<<22)) ||
        READ_SYSREG(CNTV_CVAL_EL0)!=loader_ctx[CTX_CNTV_CVAL] ||
        ((READ_SYSREG(CNTV_CTL_EL0)^loader_ctx[CTX_CNTV_CTL])&3))) lmi_gic.matches=0;
    if (lmi_gic.isolated) {
        /* Restore forwarding masks only. Never clear resident SPI pending bits. */
        if (lmi_spi_config_hash()!=lmi_gic.spi_config_hash) lmi_gic.matches=0;
        LMI_GIC32(rd+0x10180)=~lmi_gic.enabled;
        LMI_GIC32(rd+0x10100)=lmi_gic.enabled;
        for (uint32_t bank=1; bank<lmi_gic.banks; bank++) {
            LMI_GIC32(0x17a00180+bank*4)=~lmi_gic.spi_enabled[bank];
            LMI_GIC32(0x17a00100+bank*4)=lmi_gic.spi_enabled[bank];
        }
        __asm__ volatile("dsb sy" ::: "memory");
        for (unsigned n=0; n<1000000 && ((LMI_GIC32(0x17a00000)&0x80000000u) || (LMI_GIC32(rd)&8)); n++) {}
        if (LMI_GIC32(rd+0x10100)!=lmi_gic.enabled) lmi_gic.matches=0;
        for (uint32_t bank=1; bank<lmi_gic.banks; bank++) {
            if (LMI_GIC32(0x17a00100+bank*4)!=lmi_gic.spi_enabled[bank] ||
                LMI_GIC32(0x17a00300+bank*4)) lmi_gic.matches=0;
        }
    }
    return lmi_gic.matches;
}
