/* lmi-only RAM return. Native PSCI stops the other scheduler CPUs and, if
 * necessary, hands the return to the boot CPU through loader_return().
 * Never reuse RAM until firmware confirms that all seven other cores are off.
 * The stock DT pins MPIDRs to 0x000, 0x100, ... 0x700, using SMC PSCI.
 */
.section .smp_return,"ax"
.global smp_return_redirect, smp_return_prepare
smp_return_redirect:
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #63
    b.eq ram_timer
    stp x24, x23, [sp, #-64]! // displaced loader_return prologue
    b native_return_resume

smp_return_prepare:
    stp x19, x20, [sp, #-48]!
    stp x21, x22, [sp, #16]
    stp x29, x30, [sp, #32]
    add x29, sp, #32
    adr x0, online_marker
    bl log_line
    adrp x8, online_cpus
    ldr w0, [x8, :lo12:online_cpus]
    bl log_hex
    bl stop_other_cpus
    // Only the original boot core may get this far.
    mrs x20, mpidr_el1
    and x20, x20, #0xffffff
    mrs x22, cntvct_el0 // one shared extra second for firmware OFF transitions
    mov x19, #0
1:
    cmp x19, x20
    b.eq 2f
affinity_retry:
    mov x0, #4
    movk x0, #0xc400, lsl #16 // PSCI_AFFINITY_INFO (64-bit)
    mov x1, x19
    mov x2, #0
    mov x3, #0
    smc #0
    cmp x0, #1 // AFFINITY_OFF; negative/unknown is not proof
    b.eq 2f
    mov x21, x0
    cmp x0, #2 // only ON (0) and ON_PENDING (2) can be retried
    b.hi affinity_held
    mrs x8, cntfrq_el0
    mov x9, #0xf800
    movk x9, #0x124, lsl #16 // verified lmi 19.2MHz, also one second
    cmp x8, x9
    b.ne affinity_held
    isb
    mrs x8, cntvct_el0
    sub x8, x8, x22 // unsigned elapsed time also handles counter wrap
    cmp x8, x9
    b.hs affinity_held
    yield
    b affinity_retry
2:
    add x19, x19, #0x100
    cmp x19, #0x800
    b.lo 1b
    adr x0, stopped_marker
    bl log_line
    ldp x29, x30, [sp, #32]
    ldp x21, x22, [sp, #16]
    ldp x19, x20, [sp], #48
    ret

.global smp_touch_poll
smp_touch_poll:
    tst w1, #255
    b.eq touch_poll_sample
    ret
touch_poll_sample:
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    mov w19, w1
    // Only three initialized header bytes are read, including active reports.
    ldrb w8, [x0]
    ldrb w9, [x0, #1]
    ldrb w20, [x0, #2]
    orr w20, w20, w9, lsl #8
    orr w20, w20, w8, lsl #16
    adr x0, touch_poll_marker
    bl log_line
    mov w0, w19
    bl log_hex
    mov w0, w20
    bl log_hex
    mrs x0, mpidr_el1
    bl log_hex
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    ret
touch_poll_marker: .asciz "LMI_TOUCH_SMP_POLL\n"
.balign 4
affinity_held:
    adr x0, held_marker
    bl log_line
    mov x0, x19
    bl log_hex
    mov x0, x21
    bl log_hex
5:
    wfi // retain every backing page; no loader/RAM reuse on uncertain stop
    b 5b
online_marker: .asciz "LMI_SMP_ONLINE_BEFORE_STOP\n"
stopped_marker: .asciz "LMI_SMP_OTHER_CORES_OFF\n"
held_marker: .asciz "LMI_SMP_RETURN_HELD\n"
.balign 4

/* Format on this thread's stack, then take the native line lock once. The
 * old helper locked each character separately, allowing other CPUs to split
 * even a single hexadecimal value. No shared formatting state is needed.
 */
.global log_hex, smp_log_hex
log_hex:
smp_log_hex:
    stp x29, x30, [sp, #-48]!
    mov x29, sp
    add x8, sp, #16
    mov x9, #60
6:
    lsr x10, x0, x9
    and x10, x10, #15
    add x11, x10, #48
    add x12, x10, #87
    cmp x10, #10
    csel x11, x11, x12, lo
    strb w11, [x8], #1
    subs x9, x9, #4
    b.ge 6b
    mov w10, #10
    strb w10, [x8]
    strb wzr, [x8, #1]
    add x0, sp, #16
    bl log_line
    ldp x29, x30, [sp], #48
    ret
