/* lmi command-mode CPU presentation prototype.
 * Register sequence: MiCode 789514465a7cd3acbf70fa67f7e10fd8fde270bd,
 * sde_encoder_phys_cmd_prepare_commit and sde_hw_interrupts.c.
 * v41 observed INTF1_MUX=0, sync=0x180085, auto=0x80000001, GOP/4320.
 * Only PP0's disabled completion bit is acknowledged. No source address,
 * SMMU, panel, clocks, timing geometry or owned-buffer lifetime is changed.
 */
typedef unsigned int u32;
typedef unsigned long u64;
#ifndef LMI_DPU_SYNC_HOST
#define CODE __attribute__((section("__TEXT_EXEC,__lmi_dpu"),noinline,used))
#define DATA __attribute__((section("__DATA,__lmi_dpu")))
#define RODATA __attribute__((section("__TEXT_EXEC,__lmi_ro")))
extern void delay(unsigned int);
extern int snprintf(char *, unsigned long, const char *, ...);
extern void loader_log_line(const char *);
#else
#define CODE
#define DATA
#define RODATA
extern u64 sync_test_irq_off(void);
extern void sync_test_irq_restore(u64);
extern u64 sync_test_tick(void);
extern u64 sync_test_frequency(void);
extern u32 sync_test_read(u32);
extern void sync_test_write(u32,u32);
extern void sync_test_barrier(void);
extern void sync_test_native_stop(void);
extern void sync_test_hold(void);
#endif

#define SYNC 0x6ba88u
#define AUTO 0x6bab4u
#define LINE 0x6bab0u
#define FRAME 0x6b8acu
#define ENABLE 0x1010u
#define STATUS 0x1014u
#define CLEAR 0x1018u
#define START 0x201cu
#define DONE (1u<<8)
#define TE (1u<<20)
#define AUTOMATIC (1u<<31)
#define TIMEOUT_TICKS 960000ul /* 50ms at the verified 19.2MHz */

/* Keep the complete journal in the final 32 bytes before the original BSS.
 * Volatile prevents compiler scalar replacement from enlarging its footprint. */
static volatile struct {
    volatile u32 *map;
    u32 saved_sync,saved_auto,active,disabled,stopping;
} state DATA;
static const char report_format[] RODATA =
    "LMI_DPU_SYNC n=%lu ok=%u phase=%u frames=%u line=%u status=%x restored=%u\n";
static const char refused[] RODATA = "LMI_DPU_SYNC_REFUSED configuration-or-irq-ownership\n";
static const char restored[] RODATA = "LMI_DPU_SYNC_RETURN restored=1\n";
static const char restore_failed[] RODATA = "LMI_DPU_SYNC_RETURN restored=0\n";

static CODE u64 irq_off(void) {
#ifdef LMI_DPU_SYNC_HOST
    return sync_test_irq_off();
#else
    u64 flags; __asm__ volatile("mrs %0, daif\nmsr daifset, #3" : "=r"(flags) :: "memory"); return flags;
#endif
}
static CODE void irq_restore(u64 flags) {
#ifdef LMI_DPU_SYNC_HOST
    sync_test_irq_restore(flags);
#else
    __asm__ volatile("msr daif, %0" :: "r"(flags) : "memory");
#endif
}
static CODE void barrier(void) {
#ifdef LMI_DPU_SYNC_HOST
    sync_test_barrier();
#else
    __asm__ volatile("dsb sy" ::: "memory");
#endif
}
static CODE u64 ticks(void) {
#ifdef LMI_DPU_SYNC_HOST
    return sync_test_tick();
#else
    u64 n;__asm__ volatile("isb\nmrs %0, cntvct_el0" : "=r"(n) :: "memory");return n;
#endif
}
static CODE u64 frequency(void) {
#ifdef LMI_DPU_SYNC_HOST
    return sync_test_frequency();
#else
    u64 n;__asm__ volatile("mrs %0, cntfrq_el0" : "=r"(n));return n;
#endif
}
static CODE u32 read_reg(u32 offset) {
#ifdef LMI_DPU_SYNC_HOST
    return sync_test_read(offset);
#else
    return state.map[offset/4];
#endif
}
static CODE void write_reg(u32 offset,u32 value) {
#ifdef LMI_DPU_SYNC_HOST
    sync_test_write(offset,value);
#else
    state.map[offset/4]=value;
#endif
    barrier();
}
CODE int lmi_dpu_sync_stopping(void) { return __atomic_load_n(&state.stopping,__ATOMIC_ACQUIRE)!=0; }

/* Each register transaction is IRQ-masked and checks the return gate. Setting
 * stopping before native SMP shutdown prevents a new transaction; other cores
 * can only honor the stop after their current short transaction has ended. */
static CODE int transaction(u64 *flags) {
    *flags=irq_off();
    if(lmi_dpu_sync_stopping()) {irq_restore(*flags);return 0;}
    return 1;
}
static CODE int restore_registers(int returning) {
    u64 flags=irq_off();
    if(!returning && lmi_dpu_sync_stopping()) {irq_restore(flags);return 0;}
    int ok=1;
    if(__atomic_load_n(&state.active,__ATOMIC_ACQUIRE)) {
        write_reg(SYNC,state.saved_sync);
        write_reg(AUTO,state.saved_auto);
        ok=read_reg(SYNC)==state.saved_sync && read_reg(AUTO)==state.saved_auto;
        if(ok) __atomic_store_n(&state.active,0,__ATOMIC_RELEASE);
    }
    irq_restore(flags);return ok;
}
static CODE int wait_idle(void) {
    u64 began=ticks();
    do {
        u64 flags;if(!transaction(&flags)) return 0;
        u32 line=read_reg(LINE)&0xffff;
        irq_restore(flags);
        if(line==0 || line>=2400) return 1;
        delay(50);
    } while(ticks()-began<TIMEOUT_TICKS);
    return 0;
}

CODE int lmi_dpu_sync_begin(volatile u32 *map) {
    u64 flags;
    if(!map || state.disabled || !transaction(&flags)) return 0;
    state.map=map;
    if(frequency()!=19200000 || state.active || read_reg(0x6ba5c)!=0 ||
       read_reg(SYNC)!=0x180085 || read_reg(AUTO)!=0x80000001 ||
       read_reg(0x5014)!=0x9c000000 || read_reg(0x5024)!=4320 ||
       (read_reg(ENABLE)&DONE)) {
        state.disabled=1;irq_restore(flags);loader_log_line(refused);return 0;
    }
    state.saved_sync=read_reg(SYNC);state.saved_auto=read_reg(AUTO);
    __atomic_store_n(&state.active,1,__ATOMIC_RELEASE); /* publish complete restoration journal before the first write */
    write_reg(SYNC,state.saved_sync&~TE);
    write_reg(AUTO,state.saved_auto&~AUTOMATIC);
    irq_restore(flags);
    if(!wait_idle()) {
        state.disabled=1;restore_registers(0);return 0;
    }
    if(!transaction(&flags)) return 0;
    write_reg(SYNC,state.saved_sync); /* reconnect TE with autorefresh off */
    int ok=read_reg(SYNC)==state.saved_sync && read_reg(AUTO)==(state.saved_auto&~AUTOMATIC);
    irq_restore(flags);
    if(!ok) {state.disabled=1;restore_registers(0);}
    return ok;
}

CODE void lmi_dpu_sync_finish(unsigned long sample) {
    u64 flags;if(!transaction(&flags)) return;
    barrier(); /* make the complete CPU-written GOP visible before CTL_START */
    u32 first=read_reg(FRAME);
    write_reg(CLEAR,DONE);
    write_reg(START,1);
    irq_restore(flags);
    u64 began=ticks();u32 frame=first,line=0,status=0;int ok=0;
    do {
        if(!transaction(&flags)) return;
        status=read_reg(STATUS);frame=read_reg(FRAME);line=read_reg(LINE)&0xffff;
        irq_restore(flags);
        if((status&DONE) && frame-first==1 && line>=2400) {ok=1;break;}
        delay(50);
    } while(ticks()-began<TIMEOUT_TICKS);
    int restored_ok=restore_registers(0);
    if(!ok || !restored_ok) state.disabled=1;
    if(sample<=4 || sample%128==0 || !ok || !restored_ok) {
        char linebuf[192];
        snprintf(linebuf,sizeof(linebuf),report_format,sample,(unsigned)(ok&&restored_ok),
            2u,frame-first,line,status,(unsigned)restored_ok);
        loader_log_line(linebuf);
    }
}

/* Patches the one BL from ram_timer to the original smp_return_prepare.
 * Preserve its exact OFF verification before touching restoration registers.
 * Unknown affinity states still retain all RAM in the original stop loop. */
CODE void lmi_dpu_sync_smp_prepare(void) {
    __atomic_store_n(&state.stopping,1,__ATOMIC_RELEASE);
#ifdef LMI_DPU_SYNC_HOST
    sync_test_native_stop();
#else
    ((void (*)(void))0xfffffff00745a818ul)();
#endif
    int ok=restore_registers(1);
    loader_log_line(ok?restored:restore_failed);
    if(!ok) {
#ifdef LMI_DPU_SYNC_HOST
        sync_test_hold();
#else
        for(;;) __asm__ volatile("wfe" ::: "memory");
#endif
    }
    /* GOP remains firmware-owned: no new DMA allocation is freed here. */
}
