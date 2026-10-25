"""Checkpoint 62: an original iOS launchd process reaches a native EL0 getpid trap."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess
parser=argparse.ArgumentParser()
parser.add_argument('--continue-launchd',action='store_true',help='Checkpoint 63: continue native getpid and return through a RAM-only timer')
parser.add_argument('--smp-cpus',type=int,choices=(1,2,4,8),default=1,help='Opt-in matching lmi SMP RAM return; no persistent cleanup callbacks')
parser.add_argument('--force-log-wrap',action='store_true',help='Short return preflight: preserve the log head, zero unused RAM log space, exercise the wrapped-ring path')
parser.add_argument('--normalize-return-tcr',action='store_true',help='Give checkpoint63 return tables their own 4KiB/L1 TTBR0 configuration, preserving TTBR1 and runtime userspace')
parser.add_argument('--trace-return',action='store_true',help='Show checkpoint63 GIC-quiesce and cache-clean stages on the real console')
parser.add_argument('--return-stub-ro',action='store_true',help='Map the MMU-on return stub EL1 read-only executable (AP_RONA), preserving all other descriptor bits')
parser.add_argument('--clean-return-tables',action='store_true',help='Checkpoint63 candidate: explicitly clean both return-table pages to PoC before TTBR0 handoff')
parser.add_argument('--trace-graphics',action='store_true',help='Observe the existing first graphics-mode request and real surface/console fields without changing its behavior')
parser.add_argument('--release-graphics-console',action='store_true',help='Checkpoint63 first-frame fix: release the native text console after the original graphics-mode request')
parser.add_argument('--lmi-touch',action='store_true',help='Replace the disabled redwood SPI thread with bounded lmi FT3518 I2C driver; requires separate reviewed loader opt-in')
parser.add_argument('--trace-poster-registers',action='store_true',help='Log saved user ESR/FAR and protocol operands during the fixed bounded ustacks snapshots')
parser.add_argument('--lmi-gpu-readonly',action='store_true',help='lmi-only GCC/fuse/clock inventory; no GPU power, firmware, SMMU or MMIO writes')
parser.add_argument('--lmi-gpu-cx-probe',action='store_true',help='lmi-only reversible cold CX-domain power test; no GPU clocks/firmware/SMMU')
parser.add_argument('--lmi-gpu-clock-probe',action='store_true',help='Extend CX probe with reversible crystal-source GMU clock votes; no firmware/SMMU/CP')
parser.add_argument('--lmi-gpu-gmu-readonly',action='store_true',help='Extend clock probe with read-only CM3 reset and AO counter')
parser.add_argument('--lmi-gpu-tcm-load',action='store_true',help='Extend GMU probe with TCM load/readback while RESET remains asserted')
parser.add_argument('--lmi-gpu-smmu-readonly',action='store_true',help='Read SMMU GR0/stream routes with reversible lmi bus clocks; no SMMU writes')
parser.add_argument('--lmi-gpu-ram-plan',action='store_true',help='Build GMU prealloc and software page tables in owned RAM only; no MMIO')
parser.add_argument('--lmi-gpu-cb0-readonly',action='store_true',help='Extend SMMU inventory with finite CB0/GR1 snapshot; no SMMU writes')
parser.add_argument('--lmi-gpu-cb0-format-probe',action='store_true',help='Reversible CBA2R0 format-bit capability test, no stream/translation enable')
parser.add_argument('--lmi-gpu-cb0-context-probe',action='store_true',help='Reversible disabled-context register probe')
parser.add_argument('--lmi-gpu-cb0-table-probe',action='store_true',help='Owned zero-root TTBR readback, no CBAR writes or translation')
parser.add_argument('--lmi-gpu-ram-hfi',action='store_true',help='RAM-only full vendor HFI queues plus firmware backing')
parser.add_argument('--lmi-gpu-wired-context',action='store_true',help='Disabled-context readback using live firmware/HFI wired backing; no streams or translation')
parser.add_argument('--lmi-gpu-stage1-init',action='store_true',help='Initialize idle CB0 stage1 TYPE and test local ASID1 TLB sync, M0/no routes; CBAR left inert until reboot')
parser.add_argument('--lmi-gpu-arc-inventory',action='store_true',help='Read-only lmi command DB CX/MX ARC resource/selector inventory')
parser.add_argument('--lmi-gpu-rscc-readonly',action='store_true',help='Read-only GPU RSCC/DRV0 capacity and idle TCS census, CM3 RESET1')
parser.add_argument('--lmi-gpu-rpmh-probe',action='store_true',help='GPU DRV0 MX then CX selector2 requests; votes remain until reboot, no clock frequency change')
parser.add_argument('--lmi-gpu-rscc-sde-probe',action='store_true',help='Vendor RSCC STATUS0 BIT24 SDE gate-disable before independent GPU votes')
parser.add_argument('--lmi-gpu-rpmh-interface-probe',action='store_true',help='Vendor GMU RPMh interface enable under RESET1, restore only after confirmed TCS idle')
parser.add_argument('--lmi-gpu-rpmh-bus-probe',action='store_true',help='Hold verified GPU MEMNOC/SNOC clocks before DRV0 requests; retain on pending')
parser.add_argument('--lmi-gpu-rpmh-arc-slot-probe',action='store_true',help='Use pinned lmi GMU firmware active ARC TCS1 instead of bandwidth TCS0')
parser.add_argument('--lmi-gpu-rsc-state',action='store_true',help='Read-only lmi RSC/PDC/clock/QMP descriptor state under RESET1; no RPMh requests')
parser.add_argument('--lmi-gpu-rsc-init',action='store_true',help='Verify vendor GPU RSC/PDC initialization and exact restoration under RESET1; no RPMh requests')
parser.add_argument('--lmi-gpu-rsc-sequence-probe',action='store_true',help='Isolate five vendor RSC sequence SRAM words and SDE; leave hidden/PDC registers unchanged')
parser.add_argument('--lmi-gpu-pdc-enable-probe',action='store_true',help='Mode24: isolated RSC sequence plus reversible GPU PDC start/enable; no hidden writes or triggers')
parser.add_argument('--lmi-gpu-rsc-pdc-vote-probe',action='store_true',help='Mode25: hold verified isolated RSC/PDC state across GPU DRV0 slot1 MX/CX requests; no SMMU writes or firmware execution')
parser.add_argument('--lmi-gpu-gmu-200mhz-probe',action='store_true',help='Mode26: confirmed MX/CX votes then reversible 200MHz GMU RCG configuration; never reprogram GPLL0')
parser.add_argument('--lmi-gpu-gmu-route-probe',action='store_true',help='Mode27: real kernel SID5/mask400 stage1 attach/detach using owned HFI/firmware backing under 200MHz/RESET1')
parser.add_argument('--lmi-gpu-gmu-boot',action='store_true',help='Mode28: source-defined GMU firmware boot with live wired backing and dependencies retained until bounded reboot')
parser.add_argument('--lmi-gpu-hfi-io',action='store_true',help='Mode29: one-shot FW_VER bidirectional HFI DMA proof; retain dependencies until reboot')
parser.add_argument('--lmi-gpu-table-plan',action='store_true',help='Mode30: prove extra original RX pages and prepare vendor performance table read-only')
parser.add_argument('--lmi-gpu-hfi-perf',action='store_true',help='Mode31: cache-isolated HFI queues and acknowledged vendor performance table; no GX request')
parser.add_argument('--lmi-gpu-hfi-core',action='store_true',help='Mode32: A650 off bandwidth table and CORE_FW_START ACK; no GX OOB or CP')
parser.add_argument('--lmi-gpu-gx',action='store_true',help='Mode33: START, lowest DCVS and bounded GPU OOB; retain until reboot')
parser.add_argument('--lmi-gpu-cp-plan',action='store_true',help='Mode34: read-only powered CP and idle CB1 snapshot')
parser.add_argument('--lmi-gpu-core-memory',action='store_true',help='Mode35: GPU-only wired tables, SQE backing and CB1 SID0/1 attach; no CP start')
parser.add_argument('--lmi-gpu-cp',action='store_true',help='Mode36: SQE, upstream ME_INIT and owned memory fence; no secure writes')
parser.add_argument('--lmi-gpu-cp-config-ready',action='store_true',help='Mode42: exact delayed CP configuration gate before SQE start')
parser.add_argument('--lmi-gpu-cp-config-plan',action='store_true',help='Mode41: inert CP config census with SQE/WPTR stopped; no submit')
parser.add_argument('--lmi-gpu-fal-veto',action='store_true',help='Mode40: source-defined A650 FAL10 veto before firmware boot, then CP')
parser.add_argument('--lmi-gpu-core-access',action='store_true',help='Mode39: read-only GX power/reset/clock/access census after CB1 attach')
parser.add_argument('--lmi-gpu-cp-sp-clock',action='store_true',help='Mode38: source-defined SP clock enable before exact CP configuration')
parser.add_argument('--lmi-gpu-cp-fence',action='store_true',help='Mode37: explicit source-defined AHB ALLOW before CP configuration')
parser.add_argument('--lmi-gpu-scm-query',action='store_true',help='Mode43: GPU PAS service availability queries after verified CP writeback; no PIL state or buffers')
parser.add_argument('--lmi-gpu-zap-metadata',action='store_true',help='Mode44: owned contiguous Normal-NC original GPU13 MDT passed only to PAS_INIT_IMAGE')
parser.add_argument('--lmi-gpu-unsecure',action='store_true',help='Mode46: authenticated A6xx CP_SET_SECURE_MODE(0) and distinct normal-mode GPU writeback')
parser.add_argument('--lmi-gpu-tile',action='store_true',help='Explicit mode46 extension: owned16x16 GPU clear with exact pixels and guards')
parser.add_argument('--lmi-gpu-desktop',action='store_true',help='Opt-in lmi desktop backend; requires authenticated mode46 and exact tile')
parser.add_argument('--lmi-gpu-zap-load',action='store_true',help='Mode45: owned aligned original GPU13 payload with MEM_SETUP/AUTH_AND_RESET after accepted MDT')
args=parser.parse_args()
assert args.smp_cpus==1 or (args.continue_launchd and args.trace_return and args.normalize_return_tcr and args.clean_return_tables and args.return_stub_ro)
assert not args.lmi_gpu_desktop or args.lmi_gpu_tile
assert not args.lmi_gpu_tile or args.lmi_gpu_unsecure
assert not args.lmi_gpu_unsecure or args.lmi_gpu_zap_load
assert not args.lmi_gpu_zap_load or args.lmi_gpu_zap_metadata
assert not args.lmi_gpu_zap_metadata or (args.lmi_gpu_cp_config_ready and not args.lmi_gpu_scm_query)
assert not args.lmi_gpu_scm_query or args.lmi_gpu_cp_config_ready
assert not args.lmi_gpu_cp_config_ready or (args.lmi_gpu_fal_veto and not args.lmi_gpu_cp_config_plan)
assert not args.lmi_gpu_cp_config_plan or args.lmi_gpu_fal_veto
assert not args.lmi_gpu_fal_veto or (args.lmi_gpu_cp_fence and not args.lmi_gpu_cp_sp_clock)
assert not args.lmi_gpu_core_access or (args.lmi_gpu_core_memory and not args.lmi_gpu_cp)
assert not args.lmi_gpu_cp_sp_clock or args.lmi_gpu_cp_fence
assert not args.lmi_gpu_cp_fence or args.lmi_gpu_cp
assert not args.lmi_gpu_cp or args.lmi_gpu_core_memory
assert not args.lmi_gpu_core_memory or args.lmi_gpu_cp_plan
assert not args.lmi_gpu_cp_plan or args.lmi_gpu_gx
assert not args.lmi_gpu_gx or args.lmi_gpu_hfi_core
if args.lmi_gpu_gx:
    probe_source=(Path(__file__).resolve().parent/'lmi-gpu-probe.c').read_text()
    assert 'mode>=12 && mode<=46' in probe_source and 'mode!=33' in probe_source, 'GX mode must enter the SMMU/RSC path'
assert not args.lmi_gpu_hfi_core or args.lmi_gpu_hfi_perf
assert not args.lmi_gpu_hfi_perf or args.lmi_gpu_table_plan
assert not args.lmi_gpu_table_plan or args.lmi_gpu_hfi_io
assert not args.lmi_gpu_hfi_io or args.lmi_gpu_gmu_boot
assert not args.lmi_gpu_gmu_boot or args.lmi_gpu_gmu_route_probe
assert not args.lmi_gpu_gmu_route_probe or (args.lmi_gpu_gmu_200mhz_probe and args.lmi_gpu_ram_plan and args.lmi_gpu_ram_hfi)
assert not args.lmi_gpu_gmu_200mhz_probe or args.lmi_gpu_rsc_pdc_vote_probe
assert not args.lmi_gpu_rsc_pdc_vote_probe or (args.lmi_gpu_pdc_enable_probe and args.lmi_gpu_rpmh_arc_slot_probe and args.lmi_gpu_smmu_readonly and not any((args.lmi_gpu_stage1_init,args.lmi_gpu_wired_context,args.lmi_gpu_ram_plan and not args.lmi_gpu_gmu_route_probe,args.lmi_gpu_cb0_readonly)))
assert not args.lmi_gpu_pdc_enable_probe or args.lmi_gpu_rsc_sequence_probe
assert not args.lmi_gpu_rsc_sequence_probe or args.lmi_gpu_rsc_init
assert not args.lmi_gpu_rsc_init or (args.lmi_gpu_rscc_readonly and (not args.lmi_gpu_rpmh_probe or args.lmi_gpu_rsc_pdc_vote_probe) and not args.lmi_gpu_rsc_state)
assert not args.lmi_gpu_rsc_state or (args.lmi_gpu_rscc_readonly and not args.lmi_gpu_rpmh_probe)
assert not args.lmi_gpu_rpmh_arc_slot_probe or args.lmi_gpu_rpmh_bus_probe
assert not args.lmi_gpu_rpmh_bus_probe or args.lmi_gpu_rpmh_interface_probe
assert not args.lmi_gpu_rpmh_interface_probe or args.lmi_gpu_rscc_sde_probe
assert not args.lmi_gpu_rscc_sde_probe or args.lmi_gpu_rpmh_probe
assert not args.lmi_gpu_rpmh_probe or args.lmi_gpu_rscc_readonly
assert not args.lmi_gpu_rscc_readonly or args.lmi_gpu_arc_inventory
assert not args.lmi_gpu_arc_inventory or args.lmi_gpu_stage1_init or args.lmi_gpu_rsc_pdc_vote_probe
assert not args.lmi_gpu_stage1_init or args.lmi_gpu_wired_context
assert not args.lmi_gpu_wired_context or (args.lmi_gpu_ram_plan and args.lmi_gpu_ram_hfi and args.lmi_gpu_cb0_readonly and not any((args.lmi_gpu_cb0_context_probe,args.lmi_gpu_cb0_format_probe,args.lmi_gpu_tcm_load)))
assert not args.lmi_gpu_ram_hfi or args.lmi_gpu_ram_plan
assert not args.lmi_gpu_cb0_readonly or args.lmi_gpu_smmu_readonly
assert not args.lmi_gpu_cb0_format_probe or args.lmi_gpu_cb0_readonly
assert not args.lmi_gpu_cb0_context_probe or (args.lmi_gpu_cb0_readonly and not args.lmi_gpu_cb0_format_probe)
assert not args.lmi_gpu_cb0_table_probe or args.lmi_gpu_cb0_context_probe
assert not args.force_log_wrap or args.continue_launchd
assert not args.normalize_return_tcr or args.continue_launchd
assert not args.trace_return or args.continue_launchd
assert not args.return_stub_ro or args.continue_launchd
assert not args.clean_return_tables or (args.continue_launchd and args.trace_return)
assert not args.trace_graphics or (args.continue_launchd and args.trace_return)
assert not args.release_graphics_console or args.trace_graphics
assert not args.lmi_touch or args.continue_launchd
assert not args.trace_poster_registers or args.lmi_touch
assert not args.lmi_gpu_readonly or (args.lmi_touch and args.continue_launchd)
assert not args.lmi_gpu_cx_probe or (args.lmi_touch and args.continue_launchd and not args.lmi_gpu_readonly)
gpu_compact=args.lmi_gpu_wired_context or args.lmi_gpu_rsc_pdc_vote_probe
gpu_split_region=args.lmi_gpu_stage1_init or args.lmi_gpu_rsc_pdc_vote_probe
gpu_probe=args.lmi_gpu_readonly or args.lmi_gpu_cx_probe or args.lmi_gpu_ram_plan
assert not args.lmi_gpu_ram_plan or (args.lmi_touch and args.continue_launchd and not args.lmi_gpu_readonly and (not args.lmi_gpu_cx_probe or args.lmi_gpu_wired_context or args.lmi_gpu_gmu_route_probe))
assert not args.lmi_gpu_clock_probe or args.lmi_gpu_cx_probe
assert not args.lmi_gpu_gmu_readonly or args.lmi_gpu_clock_probe
assert not args.lmi_gpu_tcm_load or args.lmi_gpu_gmu_readonly
assert not args.lmi_gpu_smmu_readonly or (args.lmi_gpu_gmu_readonly and not args.lmi_gpu_tcm_load)
root=Path(__file__).resolve().parents[1]
src=root/'out/lmi-checkpoint-61-user-probe-test-stackalign/diagnostic-kernel/mach.development.bcm2837'
b=bytearray(src.read_bytes())
assert hashlib.sha256(b).hexdigest()=='afb7ab6c0512d5199c5347c52b1748b5f1b4102ff5aede51f5429750e6a804d4'
out=root/('out/lmi-kernel-ios-continue' if args.continue_launchd else 'out/lmi-kernel-ios-probe');out.mkdir(exist_ok=True)
symbols={}
for line in (root/'out/kernel-symbols.txt').read_text().splitlines():
    v=line.split(maxsplit=2)
    if len(v)==3:symbols[v[2]]=int(v[0],16)
base=0xfffffff007460a40
asm='''.text
.global _start
_start:
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #62
    b.ne original
    stp x19, x20, [sp, #-96]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    stp x0, x1, [sp, #32]
    str x2, [sp, #48]
    bl proc_pid
    mov x19, x0
    cmp w19, #1
    b.ne restore
    add x1, sp, #64
    mov w2, #32
    bl proc_name
    ldr x8, [sp, #64]
    adr x9, apple_name
    ldr x10, [x9]
    cmp x8, x10
    b.ne restore
    ldr w8, [sp, #72]
    ldr w10, [x9, #8]
    cmp w8, w10
    b.ne restore
    adr x0, name_marker
    bl log_line
    add x0, sp, #64
    bl log_line
    mov w0, #10
    bl log_char
    adr x0, pid_marker
    bl log_line
    mov x0, x19
    bl log_hex
    bl current_thread
    bl user_regs
    mov x20, x0
    cbz x20, stop
'''
fields=[('flavor',0,'w','LMI_IOS_STATE_FLAVOR'),('pc',0x108,'x','LMI_IOS_PC'),('pstate',0x110,'w','LMI_IOS_PSTATE'),
        ('esr',0x120,'w','LMI_IOS_ESR'),('syscall',0x88,'x','LMI_IOS_X16')]
for label,offset,width,marker in fields:
    asm+=f'''    adr x0, {label}_marker
    bl log_line
    ldr {width}0, [x20, #{offset}]
    bl log_hex
'''
asm+='''stop:
    adr x0, status
    bl log_line
    adr x20, status
screen_loop:
    ldrb w0, [x20], #1
    cbz w0, screen_done
    bl console_char
    b screen_loop
screen_done:
    mov w0, #62
    bl checkpoint
restore:
    ldp x0, x1, [sp, #32]
    ldr x2, [sp, #48]
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #96
original:
    stp x20, x19, [sp, #-32]! // displaced native getpid prologue
    b getpid_resume
apple_name: .asciz "launchd.ios"
name_marker: .asciz "LMI_IOS_PID1_NAME\\n"
pid_marker: .asciz "LMI_IOS_PID\\n"
'''
for label,offset,width,marker in fields:asm+=f'{label}_marker: .asciz "{marker}\\n"\n'
asm+='status: .asciz "\\nHackiOS lmi - checkpoint 62\\nlaunchd.ios PID 1 reached a user syscall\\nEL0 register evidence captured in RAM log\\nDesktop not verified; Android retained\\n"\n.balign 4\n'
if args.continue_launchd:
    asm=asm.replace('    cmp x8, #62\n    b.ne original',
        '    cmp x8, #62\n    b.eq selected\n    cmp x8, #63\n    b.ne original\nselected:')
    asm=asm.replace('stop:\n', '''stop:
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #63
    b.ne stop62
    adr x0, continue_marker
    bl log_line
    b restore
stop62:
''')
    asm=asm.replace('    adr x0, continue_marker\n    bl log_line\n    b restore', '''    adr x0, continue_marker
    bl log_line
    adr x0, start_ticks_marker
    bl log_line
    mrs x0, cntvct_el0
    bl log_hex
    b restore''')
    asm+='''
.balign 16
.global ram_timer
ram_timer:
    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #63
    b.ne native_timer
    msr daifset, #15
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    adr x0, timer_marker
    bl log_line
    mrs x0, cntvct_el0
    bl log_hex
    adr x0, frequency_marker
    bl log_line
    mrs x0, cntfrq_el0
    bl log_hex
    adr x19, timer_screen
timer_screen_loop:
    ldrb w0, [x19], #1
    cbz w0, linearize
    bl console_char
    b timer_screen_loop
linearize:
    // Same head/ring ordering as native loader_log_linearize, with IRQs off.
    // No peripheral callback, persistence function or message-buffer replay.
    adrp x8, log_linear
    mov w9, #1
    strb w9, [x8, :lo12:log_linear]
    adrp x8, log_wrapped
    ldrb w8, [x8, :lo12:log_wrapped]
    cbz w8, timer_checkpoint
    adrp x8, ring_at
    ldr w19, [x8, :lo12:ring_at]
    mov w20, #0x100000
    sub w20, w20, w19
    adrp x0, log_scratch
    add x0, x0, :lo12:log_scratch
    adrp x1, log_buffer
    add x1, x1, :lo12:log_buffer
    add x1, x1, #0x40000
    add x1, x1, x19
    mov x2, x20
    bl move_bytes
    adrp x0, log_scratch
    add x0, x0, :lo12:log_scratch
    add x0, x0, x20
    adrp x1, log_buffer
    add x1, x1, :lo12:log_buffer
    add x1, x1, #0x40000
    mov x2, x19
    bl move_bytes
    adrp x0, log_buffer
    add x0, x0, :lo12:log_buffer
    add x0, x0, #0x40000
    adrp x1, log_scratch
    add x1, x1, :lo12:log_scratch
    mov x2, #0x100000
    bl move_bytes
    adrp x8, log_length
    mov w9, #0x140000
    str w9, [x8, :lo12:log_length]
timer_checkpoint:
    adr x19, ordered_screen
    bl screen_string
    mrs x20, tcr_el1
    bl screen_hex_value
    adr x0, tcr_marker
    bl log_line
    mov x0, x20
    bl log_hex
    adr x19, sctlr_screen
    bl screen_string
    mrs x20, sctlr_el1
    bl screen_hex_value
    adr x0, sctlr_marker
    bl log_line
    mov x0, x20
    bl log_hex
    mov w0, #63
    bl checkpoint
    adr x19, rejected_screen
    bl screen_string
    brk #0
screen_hex_value:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    mov x19, #60
screen_hex:
    lsr x8, x20, x19
    and x8, x8, #15
    adr x9, screen_digits
    ldrb w0, [x9, x8]
    bl console_char
    subs x19, x19, #4
    b.ge screen_hex
    mov w0, #10
    bl console_char
    ldp x29, x30, [sp], #16
    ret
screen_string:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
screen_string_loop:
    ldrb w0, [x19], #1
    cbz w0, screen_string_done
    bl console_char
    b screen_string_loop
screen_string_done:
    ldp x29, x30, [sp], #16
    ret
native_timer:
    sub sp, sp, #64 // displaced native timer prologue
    b timer_resume
continue_marker: .asciz "LMI_IOS_GETPID_CONTINUING\\n"
timer_marker: .asciz "LMI_RAM_ONLY_TIMER_EXPIRED\\n"
start_ticks_marker: .asciz "LMI_IOS_CONTINUE_CNTVCT\\n"
frequency_marker: .asciz "LMI_TIMER_CNTFRQ\\n"
timer_screen: .asciz "\\nLMI RAM timer: returning through checkpoint 63\\n"
ordered_screen: .asciz "\\nLMI log ordered; TCR_EL1="
sctlr_screen: .asciz "LMI SCTLR_EL1="
rejected_screen: .asciz "LMI checkpoint returned unexpectedly\\n"
screen_digits: .ascii "0123456789abcdef"
tcr_marker: .asciz "LMI_RETURN_TCR_ORIGINAL\\n"
sctlr_marker: .asciz "LMI_RETURN_SCTLR_ORIGINAL\\n"
.balign 4
'''
    if args.normalize_return_tcr:
        asm+='''
.global return_tcr
return_tcr:
    // Replace the native MRS result, not the live translation configuration.
    // loader_jump installs it together with its own TTBR0 after RAM cleanup.
    // x8=stub, x9=entered flag pointer, x0/x1=reason/code must survive.
    mrs x10, tcr_el1
    adrp x11, stub_slot
    ldr x11, [x11, :lo12:stub_slot]
    cmp x11, #63
    b.ne return_tcr_done
    mov x11, #0xc03f
    bic x10, x10, x11 // TG0=4KiB, T0SZ cleared
    mov x11, #26     // 38-bit VA: L1 start, matches successful preflight
    orr x10, x10, x11
return_tcr_done:
    ret
.balign 4
'''
    if args.force_log_wrap:
        asm=asm.replace('linearize:\n', '''linearize:
    // Preserve real messages already recorded, including the timer samples.
    // Exercise the long-run ring path without waiting for a service log flood.
    adrp x8, log_length
    ldr w9, [x8, :lo12:log_length]
    adrp x10, log_buffer
    add x10, x10, :lo12:log_buffer
    add x10, x10, x9
    mov w11, #0x140000
    cmp w9, w11
    b.hs force_wrap_done
force_wrap_fill:
    strb wzr, [x10], #1
    add w9, w9, #1
    cmp w9, w11
    b.lo force_wrap_fill
    str w11, [x8, :lo12:log_length]
    adrp x8, ring_at
    mov w9, #0x2345
    movk w9, #1, lsl #16
    str w9, [x8, :lo12:ring_at]
    adrp x8, log_wrapped
    mov w9, #1
    strb w9, [x8, :lo12:log_wrapped]
force_wrap_done:
''')
if args.trace_return:
    asm+='''
.section .return_trace,"ax"
.global trace_gic, trace_cache
trace_gic:
    adrp x11, stub_slot
    ldr x11, [x11, :lo12:stub_slot]
    cmp x11, #63
    b.ne trace_gic_native
    stp x19, x20, [sp, #-32]!
    stp x29, x30, [sp, #16]
    add x29, sp, #16
    adr x19, gic_enter_text
    bl screen_string
    bl native_gic_quiesce
    adr x19, gic_done_text
    bl screen_string
    ldp x29, x30, [sp, #16]
    ldp x19, x20, [sp], #32
    ret
trace_gic_native:
    b native_gic_quiesce
trace_cache:
    adrp x11, stub_slot
    ldr x11, [x11, :lo12:stub_slot]
    cmp x11, #63
    b.ne trace_cache_done
    // Native handoff still needs x8=L1, x9=log, x10=length pointer.
    // x11 is overwritten by the original code immediately after this hook.
    stp x8, x9, [sp, #-48]!
    stp x10, x19, [sp, #16]
    stp x29, x30, [sp, #32]
    add x29, sp, #32
    adr x19, cache_done_text
    bl screen_string
    ldp x8, x9, [sp]
    ldp x10, x19, [sp, #16]
    ldp x29, x30, [sp, #32]
    add sp, sp, #48
trace_cache_done:
    dsb sy // displaced native instruction
    ret
gic_enter_text: .asciz "R1: GIC quiesce enter\\n"
gic_done_text: .asciz "R2: GIC quiesce done\\n"
cache_done_text: .asciz "R3: cache clean done; handoff\\n"
.balign 4
'''
if args.trace_graphics:
    asm+='''
.section .return_trace,"ax"
.global trace_graphics
trace_graphics:
    // The original method has already set fGraphics and validated surface.
    // Keep its actual PE call first. All observation follows the native call.
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    bl native_graphics
'''
    if args.release_graphics_console:
        asm+='''    adrp x8, stub_slot
    ldr x8, [x8, :lo12:stub_slot]
    cmp x8, #63
    b.ne graphics_release_done
    mov x0, #0
    mov w1, #5 // kPEReleaseScreen, verified pexpert.h and native switch
    bl native_graphics
graphics_release_done:
'''
    graphics_fields=[('BPE','ldrh w0, [x26, #0x98]'),
                     ('PLANES','ldr w0, [x26, #0x90]'),
                     ('FGRAPHICS','ldrb w0, [x19, #0xc4]'),
                     ('CONSOLE_ENABLED','adrp x8, console_enabled\n    ldr w0, [x8, :lo12:console_enabled]'),
                     ('GRAPHICS_BOOT','adrp x8, graphics_boot\n    ldrb w0, [x8, :lo12:graphics_boot]')]
    for label,load in graphics_fields:
        asm+=f'    adr x0, graphics_{label}\n    bl log_line\n    {load}\n    bl log_hex\n'
    asm+='    ldp x29, x30, [sp], #16\n    ret\n'
    for label,_ in graphics_fields:asm+=f'graphics_{label}: .asciz "LMI_GRAPHICS_{label}\\n"\n'
    asm+='.balign 4\n'
if args.clean_return_tables:
    assert symbols['_loader_l1']==symbols['_loader_l2']+0x1000
    needle='    add sp, sp, #48\ntrace_cache_done:'
    assert asm.count(needle)==1
    asm=asm.replace(needle,'''    add sp, sp, #48
    // x11 is replaced by native code after this hook; x12 is no longer live.
    // Clean the static L2/L1 pages explicitly before installing TTBR0.
    adrp x11, return_tables
    add x11, x11, :lo12:return_tables
    add x12, x11, #2, lsl #12
clean_return_table_line:
    dc cvac, x11
    add x11, x11, #64
    cmp x11, x12
    b.lo clean_return_table_line
    dsb sy
trace_cache_done:''')
if args.smp_cpus>1:
    # This runs before log linearization and loader_jump. Secondary callers
    # transfer through the redirected loader_return entry to the same path.
    asm=asm.replace('    adr x0, timer_marker\n','    bl smp_return_prepare\n    adr x0, timer_marker\n',1)
    asm+='\n'+(root/'tools/lmi-smp-return.S').read_text()
(out/'probe.S').write_text(asm)
targets=dict(stub_slot=symbols['_loader_stub_slot']+16,proc_pid=symbols['_proc_pid'],proc_name=symbols['_proc_name'],
    current_thread=symbols['_current_thread'],user_regs=symbols['_get_user_regs'],log_line=symbols['_loader_log_line'],log_char=symbols['_loader_log_putc'],
    log_hex=0xfffffff00745ebd0,console_char=symbols['_console_write_unbuffered'],checkpoint=symbols['_loader_checkpoint'],getpid_resume=symbols['_getpid']+4)
if args.continue_launchd:
    targets.update(timer_resume=symbols['_loader_return_timer']+4,move_bytes=symbols['_memmove'],
        log_linear=symbols['_loader_log_linear'],log_wrapped=symbols['_loader_log_wrapped'],
        ring_at=symbols['_loader_log_ring_at'],log_scratch=symbols['_loader_log_scratch'],
        log_buffer=symbols['_loader_log'],log_length=symbols['_loader_log_len'])
if args.trace_return:targets['native_gic_quiesce']=symbols['_gic_v3_irq_quiesce']
if args.clean_return_tables:targets['return_tables']=symbols['_loader_l2']
if args.trace_graphics:targets.update(native_graphics=symbols['_PE_initialize_console'],console_enabled=0xfffffff007d78c04,graphics_boot=0xfffffff007d78e08)
if args.smp_cpus>1:
    del targets['log_hex'] # stack formatter is defined in .smp_return
    targets.update(stop_other_cpus=symbols['_psci_smp_stop_others'],online_cpus=symbols['_processor_avail_count'],native_return_resume=symbols['_loader_return']+4)
subprocess.run(['clang','--target=aarch64-none-elf','-c',str(out/'probe.S'),'-o',str(out/'probe.o')],check=True)
trace_base=0xfffffff00745fd80
subprocess.run(['ld.lld',f'-Ttext={base:#x}','--entry=_start',*([f'--section-start=.return_trace={trace_base:#x}'] if args.trace_return else []),*(['--section-start=.smp_return=0xfffffff00745a800'] if args.smp_cpus>1 else []),*[f'--defsym={k}={v:#x}' for k,v in targets.items()],str(out/'probe.o'),'-o',str(out/'probe.elf')],check=True)
subprocess.run(['llvm-objcopy','-j','.text','-O','binary',str(out/'probe.elf'),str(out/'probe.bin')],check=True)
regions=[];pos=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
    cmd,size=struct.unpack_from('<II',b,pos)
    if cmd==0x19:regions.append(struct.unpack_from('<QQQQ',b,pos+24))
    pos+=size
def offset(va,size=4):
    m=[fo+va-start for start,vs,fo,fs in regions if start<=va and va+size<=start+fs]
    assert len(m)==1
    return m[0]
code=(out/'probe.bin').read_bytes();co=offset(base,len(code))
assert base>=symbols['_LowSecondaryExceptionVectorBase']+0x800 and base+len(code)<symbols['_resume_idle_cpu']
assert b[co:co+len(code)]==struct.pack('<I',0xd503201f)*(len(code)//4)
b[co:co+len(code)]=code
pc=symbols['_getpid'];off=offset(pc);old=0xa9be4ff4
assert struct.unpack_from('<I',b,off)[0]==old
assert (base-pc)%4==0 and -(1<<27)<=base-pc<(1<<27)
new=0x14000000|(((base-pc)//4)&0x3ffffff);struct.pack_into('<I',b,off,new)
patches=[dict(va=hex(pc),old=hex(old),new=hex(new))]
if args.continue_launchd:
    local_symbols={parts[2]:int(parts[0],16) for line in subprocess.check_output(['llvm-nm',str(out/'probe.elf')],text=True).splitlines() if len(parts:=line.split())==3}
    timer_target=local_symbols['ram_timer'];pc=symbols['_loader_return_timer'];off=offset(pc);old=0xd10103ff
    assert struct.unpack_from('<I',b,off)[0]==old
    assert (timer_target-pc)%4==0 and -(1<<27)<=timer_target-pc<(1<<27)
    new=0x14000000|(((timer_target-pc)//4)&0x3ffffff);struct.pack_into('<I',b,off,new)
    patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),target=hex(timer_target)))
    if args.smp_cpus>1:
        subprocess.run(['llvm-objcopy','-j','.smp_return','-O','binary',str(out/'probe.elf'),str(out/'smp-return.bin')],check=True)
        # locore.s fills to .align12 after the EL0_64 vectors. This is
        # beyond all 16 architectural vector slots (16 * 128 = 2048).
        smp_base=symbols['_ExceptionVectorsBase']+0x800
        smp_code=(out/'smp-return.bin').read_bytes();off=offset(smp_base,len(smp_code))
        assert smp_base==0xfffffff00745a800 and smp_base+len(smp_code)<=symbols['el1_sp0_synchronous_vector_long']
        assert b[off:off+len(smp_code)]==struct.pack('<I',0xd503201f)*(len(smp_code)//4)
        b[off:off+len(smp_code)]=smp_code
        pc=symbols['_loader_return'];off=offset(pc);old=0xa9bc5ff8
        assert struct.unpack_from('<I',b,off)[0]==old
        target=local_symbols['smp_return_redirect']
        assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
        new=0x14000000|(((target-pc)//4)&0x3ffffff);struct.pack_into('<I',b,off,new)
        patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),target=hex(target),purpose='SMP RAM-only return redirect; no native persistence/board cleanup'))
    if args.return_stub_ro:
        # The stub performs only system-register operations before disabling
        # the MMU. AP_RONA gives it EL1 ROX and remains executable under WXN.
        pc=0xfffffff007472ab4;off=offset(pc);old=0xd280c02a;new=0xd280d02a
        assert struct.unpack_from('<I',b,off)[0]==old # mov x10,#0x601
        struct.pack_into('<I',b,off,new) # mov x10,#0x681
        patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),purpose='Return stub AP_RWNA to AP_RONA; no physical address or memory type change'))
    if args.normalize_return_tcr:
        pc=0xfffffff007472a18;off=offset(pc);old=0xd538204a
        assert struct.unpack_from('<I',b,off)[0]==old # mrs x10,TCR_EL1
        target=local_symbols['return_tcr']
        assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
        new=0x94000000|(((target-pc)//4)&0x3ffffff)
        struct.pack_into('<I',b,off,new)
        patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),target=hex(target)))
    if args.trace_return:
        subprocess.run(['llvm-objcopy','-j','.return_trace','-O','binary',str(out/'probe.elf'),str(out/'return-trace.bin')],check=True)
        trace=(out/'return-trace.bin').read_bytes();off=offset(trace_base,len(trace))
        assert trace_base+len(trace)<=symbols['_LowSecondaryExceptionVectorBase']
        assert b[off:off+len(trace)]==struct.pack('<I',0xd503201f)*(len(trace)//4)
        b[off:off+len(trace)]=trace
        for pc,old,label in [(0xfffffff007472a58,0x940006fd,'trace_gic'),(0xfffffff007472b90,0xd5033f9f,'trace_cache')]:
            off=offset(pc);assert struct.unpack_from('<I',b,off)[0]==old
            target=local_symbols[label]
            assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
            new=0x94000000|(((target-pc)//4)&0x3ffffff);struct.pack_into('<I',b,off,new)
            patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),target=hex(target)))
        if args.trace_graphics:
            # Preserve both inspected field-load instructions as a layout guard.
            for pc,old in [(0xfffffff0079e3f9c,0x79413348),(0xfffffff0079e3fa8,0xb9409348)]:
                assert struct.unpack_from('<I',b,offset(pc))[0]==old
            pc=0xfffffff0079e3fc8;off=offset(pc);old=0x9401c992
            assert struct.unpack_from('<I',b,off)[0]==old
            assert pc+4*(old&0x3ffffff)==symbols['_PE_initialize_console']
            target=local_symbols['trace_graphics']
            assert (target-pc)%4==0 and -(1<<27)<=target-pc<(1<<27)
            new=0x94000000|(((target-pc)//4)&0x3ffffff);struct.pack_into('<I',b,off,new)
            patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),target=hex(target)))
if args.lmi_touch:
    touch_base=symbols['_goodix_thread']
    touch_end=symbols['_redwood_spmi_lock']
    touch_targets=dict(io_map=symbols['_ml_io_map'],delay=symbols['_delay_for_interval'],
        log_line=symbols['_loader_log_line'],log_hex=local_symbols['smp_log_hex'] if args.smp_cpus>1 else 0xfffffff00745ebd0,
        boot_arg=symbols['_PE_parse_boot_argn'],current_thread=symbols['_current_thread'],
        terminate=symbols['_thread_terminate'],touch_post=symbols['_redwood_touch_post'],
        memset=symbols['_memset'],memcpy=symbols['_memcpy'],user_regs=symbols['_get_user_regs'],
        io_map_memory=symbols['_ml_io_map_wcomb'],thread_info=symbols['_thread_info'])
    if args.smp_cpus>1:
        touch_targets.update(smp_touch_poll=local_symbols['smp_touch_poll'])
    # No original helper in this private static driver region is used afterward.
    # The original init still starts goodix_thread, now our entry at the same VA.
    (out/'touch.ld').write_text(f'''SECTIONS {{
      . = {touch_base:#x};
      .text : {{ *(.text.entry) *(.text*) *(.rodata*) }}
      /DISCARD/ : {{ *(.comment) *(.eh_frame*) *(.note*) }}
    }}''')
    if gpu_split_region:
        import runpy
        region_audit=runpy.run_path(str(root/'tools/audit-lmi-gpu-init-region.py'))['audit'](src.read_bytes())
        context_base=int(region_audit['start'],16)
        context_limit=int(region_audit['end'],16)
        boot_section=''
        if args.lmi_gpu_gmu_boot:
            boot_audit=runpy.run_path(str(root/'tools/audit-lmi-gpu-padding.py'))['audit'](src.read_bytes(),(root/'out/kernel-symbols.txt').read_text(),END=0xfffffff007ae0000 if args.lmi_gpu_table_plan else 0xfffffff007add000)
            boot_base=int(boot_audit['start'],16);boot_limit=int(boot_audit['end'],16)
            boot_section=f'.gpu_boot {boot_base:#x} : {{ *(.gpu_boot .gpu_boot_data) *gpu-boot.o(.rodata*) *gpu-hfi-io.o(.rodata*) }}'
        if args.lmi_gpu_table_plan:
            boot_section=boot_section[:-1]+'. = ABSOLUTE(0xfffffff007add620); *(.gpu_page1) *(.gpu_plan .gpu_plan_data) *gpu-table-plan.o(.rodata*) *(.gpu_cp_plan .gpu_cp_plan_data) *gpu-cp-plan.o(.rodata*) . = ABSOLUTE(0xfffffff007ade000); *(.gpu_page2) *(.gpu_hfi_perf) *gpu-hfi-perf.o(.rodata*) *(.gpu_core_mem .gpu_core_mem_data) *gpu-core-memory.o(.rodata*) *(.gpu_cp .gpu_cp_data) *gpu-cp.o(.rodata*) *gpu-core-access.o(.rodata*) . = ABSOLUTE(0xfffffff007adf000); *(.gpu_page3) *(.gpu_hfi_core) *gpu-hfi-core.o(.rodata*) *(.gpu_gx) *gpu-gx.o(.rodata*) *(.gpu_core_attach) }'
        if args.lmi_gpu_cp_config_ready:
            # Keep the proved page canaries fixed. READY adds executable CP
            # checks on page2; its completion helper/constants/strings fit in
            # page3's audited tail. All original region bounds still apply.
            boot_section=boot_section.replace('*(.gpu_cp .gpu_cp_data) *gpu-cp.o(.rodata*)','*(.gpu_cp)')
            boot_section=boot_section[:-1]+' *(.gpu_cp_finish .gpu_cp_data) *gpu-cp.o(.rodata*) }'
        if args.lmi_gpu_scm_query:
            boot_section=boot_section[:-1]+' *(.gpu_scm) *gpu-scm.o(.rodata*) }'
        if args.lmi_gpu_zap_metadata:
            boot_section=boot_section[:-1]+' *(.gpu_zap) *gpu-zap-metadata.o(.rodata*) }'
        zap_constants='*gpu-zap-metadata.o(.rodata)' if args.lmi_gpu_zap_metadata else ''
        frame_section=''
        unsecure_section=''
        normal_diag_section=''
        desktop_section=''
        if args.lmi_gpu_desktop:
            desktop_audit=runpy.run_path(str(root/'tools/audit-lmi-gpu-desktop-region.py'))['audit'](src.read_bytes(),(root/'out/kernel-symbols.txt').read_text(),(root/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text())
            desktop_base=int(desktop_audit['start'],16)
            desktop_section=f'.gpu_desktop {desktop_base:#x} : {{ *(.gpu_desktop .gpu_desktop_data) *gpu-desktop.o(.rodata*) }}'
            desktop_profile=runpy.run_path(str(root/'tools/lmi-gpu-desktop-profile.py'))
            touch_targets.update(desktop_profile['bindings'](symbols))
        if args.lmi_gpu_unsecure:
            unsecure_audit=runpy.run_path(str(root/'tools/audit-lmi-gpu-unsecure-region.py'))['audit'](src.read_bytes(),(root/'out/kernel-symbols.txt').read_text(),(root/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text())
            unsecure_base=int(unsecure_audit['start'],16);unsecure_limit=int(unsecure_audit['end'],16)
            unsecure_section=f'.gpu_unsecure {unsecure_base:#x} : {{ *(.gpu_unsecure .gpu_unsecure_data) *gpu-unsecure.o(.rodata*) }}'
            normal_diag_audit=runpy.run_path(str(root/'tools/audit-lmi-gpu-normal-diag-region.py'))['audit'](src.read_bytes(),(root/'out/kernel-symbols.txt').read_text(),(root/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text())
            normal_diag_base=int(normal_diag_audit['start'],16);normal_diag_limit=int(normal_diag_audit['end'],16)
            normal_diag_section=f'.gpu_normal_diag {normal_diag_base:#x} : {{ *(.gpu_normal_diag .gpu_normal_diag_data) *gpu-tile.o(.rodata*) }}'
        if args.lmi_gpu_zap_load:
            frame_audit=runpy.run_path(str(root/'tools/audit-lmi-gpu-frame-region.py'))['audit'](src.read_bytes(),(root/'out/kernel-symbols.txt').read_text(),(root/'hackios/xnu/files/bsd/dev/redwood_adreno.c').read_text())
            frame_base=int(frame_audit['start'],16);frame_limit=int(frame_audit['end'],16)
            frame_section=f'.gpu_zap_load {frame_base:#x} : {{ *(.gpu_zap_load .gpu_zap_load_data) *gpu-zap-load.o(.rodata*) }}'
        (out/'touch.ld').write_text(f'''SECTIONS {{
          .text {touch_base:#x} : {{ *(.text.entry) *(EXCLUDE_FILE (*gpu-context.o *gpu-resources.o) .text*) *(EXCLUDE_FILE (*gpu-context.o *gpu-resources.o *gpu-rpmh.o *gpu-boot.o *gpu-hfi-io.o *gpu-table-plan.o *gpu-hfi-perf.o *gpu-hfi-core.o *gpu-gx.o *gpu-cp-plan.o *gpu-core-memory.o *gpu-cp.o *gpu-core-access.o *gpu-scm.o *gpu-zap-metadata.o *gpu-zap-load.o *gpu-unsecure.o *gpu-tile.o *gpu-desktop.o) .rodata*) }}
          .gpu_context {context_base:#x} : {{ *gpu-context.o(.text* .rodata*) *gpu-resources.o(.text* .rodata*) *gpu-rpmh.o(.rodata*) *(.gpu_extra .gpu_helpers) {zap_constants} }}
          {frame_section}
          {unsecure_section}
          {normal_diag_section}
          {desktop_section}
          {boot_section}
          /DISCARD/ : {{ *(.comment) *(.eh_frame*) *(.note*) }}
        }}''')
    subprocess.run(['clang','--target=aarch64-none-elf','-Oz' if gpu_compact else '-Os' if gpu_probe else '-O2','-ffreestanding','-fno-builtin',
        '-fno-stack-protector','-mno-outline-atomics','-mgeneral-regs-only',*(['-flto'] if gpu_compact else []),'-ffunction-sections','-fdata-sections','-c',
        *(['-DLMI_TOUCH_COMPACT_LOG'] if args.lmi_gpu_gmu_route_probe else []),*(['-DLMI_TOUCH_SMP'] if args.smp_cpus>1 else []),str(root/'tools/lmi-touch.c'),'-o',str(out/'touch.o')],check=True)
    touch_objects=[str(out/'touch.o')]
    if gpu_probe:
        subprocess.run(['clang','--target=aarch64-none-elf','-Oz' if gpu_compact else '-Os',*(['-flto'] if gpu_compact else []),'-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-mno-outline-atomics','-mgeneral-regs-only',*(['-flto'] if gpu_compact else []),'-ffunction-sections','-fdata-sections','-c',
            *(['-DLMI_GPU_RAM_PLAN'] if args.lmi_gpu_ram_plan else []),
            *(['-DLMI_GPU_WIRED_CONTEXT'] if args.lmi_gpu_wired_context else []),
            *(['-DLMI_GPU_STAGE1_INIT'] if args.lmi_gpu_stage1_init else []),
            *(['-DLMI_GPU_ARC_INVENTORY'] if args.lmi_gpu_arc_inventory else []),
            *(['-DLMI_GPU_RSCC_READONLY'] if args.lmi_gpu_rscc_readonly else []),
            *(['-DLMI_GPU_RSC_STATE'] if args.lmi_gpu_rsc_state else []),
            *(['-DLMI_GPU_RSC_INIT'] if args.lmi_gpu_rsc_init else []),
            *(['-DLMI_GPU_RSC_SEQUENCE'] if args.lmi_gpu_rsc_sequence_probe else []),
            *(['-DLMI_GPU_PDC_ENABLE'] if args.lmi_gpu_pdc_enable_probe else []),*(['-DLMI_GPU_RSC_PDC_VOTE'] if args.lmi_gpu_rsc_pdc_vote_probe else []),*(['-DLMI_GPU_GMU_200MHZ'] if args.lmi_gpu_gmu_200mhz_probe else []),*(['-DLMI_GPU_GMU_ROUTE'] if args.lmi_gpu_gmu_route_probe else []),*(['-DLMI_GPU_GMU_BOOT'] if args.lmi_gpu_gmu_boot else []),*(['-DLMI_GPU_HFI_IO'] if args.lmi_gpu_hfi_io else []),*(['-DLMI_GPU_TABLE_PLAN'] if args.lmi_gpu_table_plan else []),*(['-DLMI_GPU_HFI_PERF'] if args.lmi_gpu_hfi_perf else []),*(['-DLMI_GPU_HFI_CORE'] if args.lmi_gpu_hfi_core else []),*(['-DLMI_GPU_GX'] if args.lmi_gpu_gx else []),*(['-DLMI_GPU_CP_PLAN'] if args.lmi_gpu_cp_plan else []),*(['-DLMI_GPU_CORE_MEMORY'] if args.lmi_gpu_core_memory else []),*(['-DLMI_GPU_CP'] if args.lmi_gpu_cp else []),*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),
            *(['-DLMI_GPU_RPMH_PROBE'] if args.lmi_gpu_rpmh_probe else []),
            *(['-DLMI_GPU_RSCC_SDE_PROBE'] if args.lmi_gpu_rscc_sde_probe else []),
            *(['-DLMI_GPU_RPMH_INTERFACE_PROBE'] if args.lmi_gpu_rpmh_interface_probe else []),
            *(['-DLMI_GPU_RPMH_BUS_PROBE'] if args.lmi_gpu_rpmh_bus_probe else []),
            *(['-DLMI_GPU_RPMH_ARC_SLOT_PROBE'] if args.lmi_gpu_rpmh_arc_slot_probe else []),
            *(['-DLMI_GPU_CONTEXT_PROBE'] if args.lmi_gpu_cb0_context_probe else []),
            str(root/'tools/lmi-gpu-probe.c'),'-o',str(out/'gpu-probe.o')],check=True)
        touch_objects.append(str(out/'gpu-probe.o'))
        touch_targets['image_file']=symbols['_redwood_image_file']
        touch_targets['alloc_data']=symbols['_IOMallocData']
        touch_targets['free_data']=symbols['_IOFreeData']
        if args.lmi_gpu_ram_plan:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz' if gpu_compact else '-Os',*(['-flto'] if gpu_compact else []),'-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
                '-fno-stack-protector','-mno-outline-atomics','-mgeneral-regs-only',*(['-flto'] if gpu_compact else []),'-ffunction-sections','-fdata-sections','-c',
                *(['-DLMI_GPU_RAM_HFI'] if args.lmi_gpu_ram_hfi else []),*(['-DLMI_GPU_GMU_ROUTE'] if args.lmi_gpu_gmu_route_probe else []),*(['-DLMI_GPU_GMU_BOOT'] if args.lmi_gpu_gmu_boot else []),*(['-DLMI_GPU_HFI_IO'] if args.lmi_gpu_hfi_io else []),*(['-DLMI_GPU_TABLE_PLAN'] if args.lmi_gpu_table_plan else []),*(['-DLMI_GPU_HFI_PERF'] if args.lmi_gpu_hfi_perf else []),*(['-DLMI_GPU_HFI_CORE'] if args.lmi_gpu_hfi_core else []),*(['-DLMI_GPU_GX'] if args.lmi_gpu_gx else []),*(['-DLMI_GPU_CP_PLAN'] if args.lmi_gpu_cp_plan else []),*(['-DLMI_GPU_CORE_MEMORY'] if args.lmi_gpu_core_memory else []),*(['-DLMI_GPU_CP'] if args.lmi_gpu_cp else []),*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),
                str(root/'tools/lmi-gpu-ram.c'),'-o',str(out/'gpu-ram.o')],check=True)
            touch_objects.append(str(out/'gpu-ram.o'))
            if args.lmi_gpu_ram_hfi:
                subprocess.run(['clang','--target=aarch64-none-elf','-Oz' if gpu_compact else '-Os',*(['-flto'] if gpu_compact else []),'-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-c',str(root/'tools/lmi-gpu-hfi.c'),'-o',str(out/'gpu-hfi.o')],check=True)
                touch_objects.append(str(out/'gpu-hfi.o'))
        if args.lmi_gpu_wired_context:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector',
                *(['-DLMI_GPU_STAGE1_INIT'] if args.lmi_gpu_stage1_init else ['-flto']),
                '-c',str(root/'tools/lmi-gpu-context.c'),'-o',str(out/'gpu-context.o')],check=True)
            touch_objects.append(str(out/'gpu-context.o'))
        if args.lmi_gpu_arc_inventory:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector',*(['-DLMI_GPU_RPMH_PROBE'] if args.lmi_gpu_rpmh_probe else []),'-c',str(root/'tools/lmi-gpu-resources.c'),'-o',str(out/'gpu-resources.o')],check=True)
            touch_objects.append(str(out/'gpu-resources.o'))
        if args.lmi_gpu_rsc_init:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',*(['-DLMI_GPU_RSC_SEQUENCE'] if args.lmi_gpu_rsc_sequence_probe else []),*(['-DLMI_GPU_PDC_ENABLE'] if args.lmi_gpu_pdc_enable_probe else []),*(['-DLMI_GPU_RSC_PDC_VOTE'] if args.lmi_gpu_rsc_pdc_vote_probe else []),*(['-DLMI_GPU_GMU_200MHZ'] if args.lmi_gpu_gmu_200mhz_probe else []),*(['-DLMI_GPU_GMU_ROUTE'] if args.lmi_gpu_gmu_route_probe else []),*(['-DLMI_GPU_GMU_BOOT'] if args.lmi_gpu_gmu_boot else []),*(['-DLMI_GPU_HFI_IO'] if args.lmi_gpu_hfi_io else []),*(['-DLMI_GPU_TABLE_PLAN'] if args.lmi_gpu_table_plan else []),*(['-DLMI_GPU_HFI_PERF'] if args.lmi_gpu_hfi_perf else []),*(['-DLMI_GPU_HFI_CORE'] if args.lmi_gpu_hfi_core else []),*(['-DLMI_GPU_GX'] if args.lmi_gpu_gx else []),*(['-DLMI_GPU_CP_PLAN'] if args.lmi_gpu_cp_plan else []),*(['-DLMI_GPU_CORE_MEMORY'] if args.lmi_gpu_core_memory else []),*(['-DLMI_GPU_CP'] if args.lmi_gpu_cp else []),*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),str(root/'tools/lmi-gpu-rsc-init.c'),'-o',str(out/'gpu-rsc-init.o')],check=True)
            touch_objects.append(str(out/'gpu-rsc-init.o'))
        if args.lmi_gpu_gmu_200mhz_probe:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',*(['-DLMI_GPU_GMU_ROUTE'] if args.lmi_gpu_gmu_route_probe else []),*(['-DLMI_GPU_GMU_BOOT'] if args.lmi_gpu_gmu_boot else []),*(['-DLMI_GPU_HFI_IO'] if args.lmi_gpu_hfi_io else []),*(['-DLMI_GPU_TABLE_PLAN'] if args.lmi_gpu_table_plan else []),*(['-DLMI_GPU_HFI_PERF'] if args.lmi_gpu_hfi_perf else []),*(['-DLMI_GPU_HFI_CORE'] if args.lmi_gpu_hfi_core else []),*(['-DLMI_GPU_GX'] if args.lmi_gpu_gx else []),*(['-DLMI_GPU_CP_PLAN'] if args.lmi_gpu_cp_plan else []),*(['-DLMI_GPU_CORE_MEMORY'] if args.lmi_gpu_core_memory else []),*(['-DLMI_GPU_CP'] if args.lmi_gpu_cp else []),*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),str(root/'tools/lmi-gpu-clock.c'),'-o',str(out/'gpu-clock.o')],check=True)
            touch_objects.append(str(out/'gpu-clock.o'))
        if args.lmi_gpu_gmu_route_probe:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-flto','-c',*(['-DLMI_GPU_GMU_BOOT'] if args.lmi_gpu_gmu_boot else []),*(['-DLMI_GPU_HFI_IO'] if args.lmi_gpu_hfi_io else []),*(['-DLMI_GPU_TABLE_PLAN'] if args.lmi_gpu_table_plan else []),*(['-DLMI_GPU_HFI_PERF'] if args.lmi_gpu_hfi_perf else []),*(['-DLMI_GPU_HFI_CORE'] if args.lmi_gpu_hfi_core else []),*(['-DLMI_GPU_GX'] if args.lmi_gpu_gx else []),*(['-DLMI_GPU_CP_PLAN'] if args.lmi_gpu_cp_plan else []),*(['-DLMI_GPU_CORE_MEMORY'] if args.lmi_gpu_core_memory else []),*(['-DLMI_GPU_CP'] if args.lmi_gpu_cp else []),*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),str(root/'tools/lmi-gpu-route.c'),'-o',str(out/'gpu-route.o')],check=True)
            touch_objects.append(str(out/'gpu-route.o'))
        if args.lmi_gpu_gmu_boot:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',*(['-DLMI_GPU_HFI_IO'] if args.lmi_gpu_hfi_io else []),*(['-DLMI_GPU_TABLE_PLAN'] if args.lmi_gpu_table_plan else []),*(['-DLMI_GPU_HFI_PERF'] if args.lmi_gpu_hfi_perf else []),*(['-DLMI_GPU_HFI_CORE'] if args.lmi_gpu_hfi_core else []),*(['-DLMI_GPU_GX'] if args.lmi_gpu_gx else []),*(['-DLMI_GPU_CP_PLAN'] if args.lmi_gpu_cp_plan else []),*(['-DLMI_GPU_CORE_MEMORY'] if args.lmi_gpu_core_memory else []),*(['-DLMI_GPU_CP'] if args.lmi_gpu_cp else []),*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),str(root/'tools/lmi-gpu-boot.c'),'-o',str(out/'gpu-boot.o')],check=True)
            touch_objects.append(str(out/'gpu-boot.o'))
        if args.lmi_gpu_hfi_io:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-hfi-io.c'),'-o',str(out/'gpu-hfi-io.o')],check=True)
            touch_objects.append(str(out/'gpu-hfi-io.o'))
        if args.lmi_gpu_table_plan:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-table-plan.c'),'-o',str(out/'gpu-table-plan.o')],check=True)
            touch_objects.append(str(out/'gpu-table-plan.o'))
        if args.lmi_gpu_hfi_perf:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-hfi-perf.c'),'-o',str(out/'gpu-hfi-perf.o')],check=True)
            touch_objects.append(str(out/'gpu-hfi-perf.o'))
        if args.lmi_gpu_hfi_core:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-hfi-core.c'),'-o',str(out/'gpu-hfi-core.o')],check=True)
            touch_objects.append(str(out/'gpu-hfi-core.o'))
        if args.lmi_gpu_core_access:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-core-access.c'),'-o',str(out/'gpu-core-access.o')],check=True)
            touch_objects.append(str(out/'gpu-core-access.o'))
        if args.lmi_gpu_cp:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),str(root/'tools/lmi-gpu-cp.c'),'-o',str(out/'gpu-cp.o')],check=True)
            touch_objects.append(str(out/'gpu-cp.o'))
            if args.lmi_gpu_cp_config_ready:
                # SHF_MERGE strings otherwise coalesce at the first string
                # pool in this output section, defeating the explicit page3
                # placement and overflowing the fixed page1 canary address.
                # Keep the bytes read-only, but place this object's pool whole.
                subprocess.run(['llvm-objcopy','--set-section-flags=.rodata.str1.1=alloc,load,readonly,data,contents',str(out/'gpu-cp.o')],check=True)
        if args.lmi_gpu_unsecure:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-unsecure.c'),'-o',str(out/'gpu-unsecure.o')],check=True)
            subprocess.run(['llvm-objcopy','--set-section-flags=.rodata.str1.1=alloc,load,readonly,data,contents',str(out/'gpu-unsecure.o')],check=True)
            touch_objects.append(str(out/'gpu-unsecure.o'))
        if args.lmi_gpu_tile:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',*(['-DLMI_GPU_DESKTOP'] if args.lmi_gpu_desktop else []),str(root/'tools/lmi-gpu-tile.c'),'-o',str(out/'gpu-tile.o')],check=True)
            touch_objects.append(str(out/'gpu-tile.o'))
        if args.lmi_gpu_desktop:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-desktop.c'),'-o',str(out/'gpu-desktop.o')],check=True)
            subprocess.run(['llvm-objcopy','--set-section-flags=.rodata.str1.1=alloc,load,readonly,data,contents',str(out/'gpu-desktop.o')],check=True)
            touch_objects.append(str(out/'gpu-desktop.o'))
        if args.lmi_gpu_scm_query:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-scm.c'),'-o',str(out/'gpu-scm.o')],check=True)
            subprocess.run(['llvm-objcopy','--set-section-flags=.rodata.str1.1=alloc,load,readonly,data,contents',str(out/'gpu-scm.o')],check=True)
            touch_objects.append(str(out/'gpu-scm.o'))
        if args.lmi_gpu_zap_metadata:
            assert symbols['_pmap_cache_attributes']==0xfffffff00743f040 and symbols['_pmap_set_cache_attributes']==0xfffffff0074464dc
            touch_targets.update(pmap_cache_attributes=symbols['_pmap_cache_attributes'],pmap_set_cache_attributes=symbols['_pmap_set_cache_attributes'])
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-zap-metadata.c'),'-o',str(out/'gpu-zap-metadata.o')],check=True)
            subprocess.run(['llvm-objcopy','--set-section-flags=.rodata.str1.1=alloc,load,readonly,data,contents',str(out/'gpu-zap-metadata.o')],check=True)
            touch_objects.append(str(out/'gpu-zap-metadata.o'))
        if args.lmi_gpu_zap_load:
            assert symbols['_IOMallocContiguous']==0xfffffff007984f70
            touch_targets['alloc_contiguous']=symbols['_IOMallocContiguous']
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-zap-load.c'),'-o',str(out/'gpu-zap-load.o')],check=True)
            subprocess.run(['llvm-objcopy','--set-section-flags=.rodata.str1.1=alloc,load,readonly,data,contents',str(out/'gpu-zap-load.o')],check=True)
            touch_objects.append(str(out/'gpu-zap-load.o'))
        if args.lmi_gpu_core_memory:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',*(['-DLMI_GPU_CP'] if args.lmi_gpu_cp else []),*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),*(['-DLMI_GPU_TILE'] if args.lmi_gpu_tile else []),str(root/'tools/lmi-gpu-core-memory.c'),'-o',str(out/'gpu-core-memory.o')],check=True)
            touch_objects.append(str(out/'gpu-core-memory.o'))
        if args.lmi_gpu_cp_plan:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',str(root/'tools/lmi-gpu-cp-plan.c'),'-o',str(out/'gpu-cp-plan.o')],check=True)
            touch_objects.append(str(out/'gpu-cp-plan.o'))
        if args.lmi_gpu_gx:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector','-c',*(['-DLMI_GPU_CP_PLAN'] if args.lmi_gpu_cp_plan else []),*(['-DLMI_GPU_CORE_MEMORY'] if args.lmi_gpu_core_memory else []),*(['-DLMI_GPU_CP'] if args.lmi_gpu_cp else []),*(['-DLMI_GPU_CP_FENCE'] if args.lmi_gpu_cp_fence else []),*(['-DLMI_GPU_CP_SP_CLOCK'] if args.lmi_gpu_cp_sp_clock else []),*(['-DLMI_GPU_CORE_ACCESS'] if args.lmi_gpu_core_access else []),*(['-DLMI_GPU_FAL_VETO'] if args.lmi_gpu_fal_veto else []),*(['-DLMI_GPU_CP_CONFIG_PLAN'] if args.lmi_gpu_cp_config_plan else []),*(['-DLMI_GPU_CP_CONFIG_READY'] if args.lmi_gpu_cp_config_ready else []),*(['-DLMI_GPU_SCM_QUERY'] if args.lmi_gpu_scm_query else []),*(['-DLMI_GPU_ZAP_METADATA'] if args.lmi_gpu_zap_metadata else []),*(['-DLMI_GPU_ZAP_LOAD'] if args.lmi_gpu_zap_load else []),*(['-DLMI_GPU_UNSECURE'] if args.lmi_gpu_unsecure else []),str(root/'tools/lmi-gpu-gx.c'),'-o',str(out/'gpu-gx.o')],check=True)
            touch_objects.append(str(out/'gpu-gx.o'))
        if args.lmi_gpu_rpmh_probe:
            subprocess.run(['clang','--target=aarch64-none-elf','-Oz','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-mgeneral-regs-only','-fno-stack-protector',*(['-DLMI_GPU_RSCC_SDE_PROBE'] if args.lmi_gpu_rscc_sde_probe else []),*(['-DLMI_GPU_RPMH_INTERFACE_PROBE'] if args.lmi_gpu_rpmh_interface_probe else []),*(['-DLMI_GPU_RPMH_ARC_SLOT_PROBE'] if args.lmi_gpu_rpmh_arc_slot_probe else []),'-c',str(root/'tools/lmi-gpu-rpmh.c'),'-o',str(out/'gpu-rpmh.o')],check=True)
            touch_objects.append(str(out/'gpu-rpmh.o'))
        if args.lmi_gpu_ram_plan or args.lmi_gpu_cb0_context_probe:
            # Private inline/LinuxKPI functions share the short names and
            # overwrite them in the generic symbol map. Pin unique exports.
            assert symbols['_kmem_alloc_external']==0xfffffff00739dc70
            assert symbols['_kmem_free_external']==0xfffffff00739f9d0
            assert symbols['_kmem_alloc_guard_internal']==0xfffffff00739d200
            # The selected caller uses this exact six-argument private ABI.
            # Freeze the target address and known export call/return sequence.
            assert struct.unpack_from('<I',b,offset(0xfffffff00739dcb4))[0]==0x97fffd53
            assert struct.unpack_from('<I',b,offset(0xfffffff00739dcb8))[0]==0xf90002a1
            touch_targets.update(kmem_alloc_tagged=symbols['_kmem_alloc_guard_internal'],kmem_free3=symbols['_kmem_free_external'],
                pa_of=symbols['_kvtophys'],clean_cache=symbols['_clean_dcache'],
                kernel_map_value=symbols['_kernel_map'],boot_args_ptr=symbols['_BootArgs'],
                g_phys_base=symbols['_gPhysBase'],g_phys_size=symbols['_gPhysSize'],
                xnu_page_size=symbols['_page_size'],xnu_page_shift=symbols['_page_shift'])
    subprocess.run(['ld.lld','-T',str(out/'touch.ld'),'--entry=lmi_touch_thread',
        *(['--gc-sections','--undefined=lmi_gpu_probe'] if gpu_compact else []),
        *(['--undefined=lmi_desktop_'+v for v in {row[2] for row in desktop_profile['ABI'].values()}] if args.lmi_gpu_desktop else []),
        *[f'--defsym={k}={v:#x}' for k,v in touch_targets.items()],*touch_objects,'-o',str(out/'touch.elf')],check=True)
    sections=subprocess.check_output(['llvm-readelf','-SW',str(out/'touch.elf')],text=True)
    # Reject unexpected writable allocated state in the replaced RX region.
    assert not any(' WA ' in line or ' WAX ' in line for line in sections.splitlines())
    subprocess.run(['llvm-objcopy','-j','.text','-O','binary',str(out/'touch.elf'),str(out/'touch.bin')],check=True)
    touch=(out/'touch.bin').read_bytes()
    touch+=bytes((-len(touch))%4)
    assert touch_base+len(touch)<=touch_end and len(touch)%4==0
    at=offset(touch_base,len(touch)); original=bytes(b[at:at+len(touch)])
    b[at:at+len(touch)]=touch
    if gpu_split_region:
        subprocess.run(['llvm-objcopy','-j','.gpu_context','-O','binary',str(out/'touch.elf'),str(out/'gpu-context.bin')],check=True)
        context_code=(out/'gpu-context.bin').read_bytes()
        assert context_code and context_base+len(context_code)<=context_limit
        at=offset(context_base,len(context_code));old_context=bytes(b[at:at+len(context_code)])
        b[at:at+len(context_code)]=context_code
        (out/'gpu-context-region-audit.json').write_text(json.dumps(region_audit,indent=2))
        patches.append(dict(va=hex(context_base),bytes=len(context_code),limit=hex(context_limit),original_region_sha256=hashlib.sha256(old_context).hexdigest(),purpose='lmi GPU channel helpers in audited unreachable initializer body; no context writes' if args.lmi_gpu_rsc_pdc_vote_probe else 'lmi disabled stage1 context callback in unreachable original initializer body; entry redirected separately'))
    if args.lmi_gpu_gmu_boot:
        subprocess.run(['llvm-objcopy','-j','.gpu_boot','-O','binary',str(out/'touch.elf'),str(out/'gpu-boot.bin')],check=True)
        boot_code=(out/'gpu-boot.bin').read_bytes()
        assert boot_code and boot_base+len(boot_code)<=boot_limit, 'GMU boot exceeds audited padding'
        at=offset(boot_base,len(boot_code));assert b[at:at+len(boot_code)]==bytes(len(boot_code))
        b[at:at+len(boot_code)]=boot_code
        (out/'gpu-boot-region-audit.json').write_text(json.dumps(boot_audit,indent=2))
        patches.append(dict(va=hex(boot_base),bytes=len(boot_code),limit=hex(boot_limit),purpose='GMU boot in audited original RX segment padding; execution canary required'))
    if args.lmi_gpu_zap_load:
        subprocess.run(['llvm-objcopy','-j','.gpu_zap_load','-O','binary',str(out/'touch.elf'),str(out/'gpu-zap-load.bin')],check=True)
        frame_code=(out/'gpu-zap-load.bin').read_bytes()
        assert frame_code and frame_base+len(frame_code)<=frame_limit, 'ZAP load exceeds audited demo body'
        entry=int(frame_audit['entry'],16);at=offset(entry)
        assert list(struct.unpack_from('<2I',b,at))==[int(v,16) for v in frame_audit['original_entry_words']]
        struct.pack_into('<2I',b,at,0x52800000,0xd65f03c0)
        at=offset(frame_base,len(frame_code));old_frame=bytes(b[at:at+len(frame_code)]);b[at:at+len(frame_code)]=frame_code
        (out/'gpu-frame-region-audit.json').write_text(json.dumps(frame_audit,indent=2))
        patches.append(dict(va=hex(entry),old=frame_audit['original_entry_words'],new=['0x52800000','0xd65f03c0'],purpose='Disable obsolete board demo entry; old function-table calls return false'))
        patches.append(dict(va=hex(frame_base),bytes=len(frame_code),limit=hex(frame_limit),original_region_sha256=hashlib.sha256(old_frame).hexdigest(),purpose='ZAP loader in independently audited unreachable board-demo body'))
    if args.lmi_gpu_unsecure:
        subprocess.run(['llvm-objcopy','-j','.gpu_unsecure','-O','binary',str(out/'touch.elf'),str(out/'gpu-unsecure.bin')],check=True)
        normal_code=(out/'gpu-unsecure.bin').read_bytes()
        assert normal_code and unsecure_base+len(normal_code)<=unsecure_limit, 'Normal-mode helper exceeds audited demo body'
        entry=int(unsecure_audit['entry'],16);at=offset(entry)
        assert list(struct.unpack_from('<2I',b,at))==[int(v,16) for v in unsecure_audit['original_entry_words']]
        struct.pack_into('<2I',b,at,0x52800000,0xd65f03c0)
        at=offset(unsecure_base,len(normal_code));old_normal=bytes(b[at:at+len(normal_code)]);b[at:at+len(normal_code)]=normal_code
        (out/'gpu-unsecure-region-audit.json').write_text(json.dumps(unsecure_audit,indent=2))
        patches.append(dict(va=hex(entry),old=unsecure_audit['original_entry_words'],new=['0x52800000','0xd65f03c0'],purpose='Disable obsolete board ZAP demo entry; old function-table calls return false'))
        patches.append(dict(va=hex(unsecure_base),bytes=len(normal_code),limit=hex(unsecure_limit),original_region_sha256=hashlib.sha256(old_normal).hexdigest(),purpose='Authenticated CP normal-mode helper in independently audited obsolete board-demo body'))
        subprocess.run(['llvm-objcopy','-j','.gpu_normal_diag','-O','binary',str(out/'touch.elf'),str(out/'gpu-normal-diag.bin')],check=True)
        diag_code=(out/'gpu-normal-diag.bin').read_bytes()
        assert diag_code and normal_diag_base+len(diag_code)<=normal_diag_limit, 'Normal diagnostics exceed audited core-start body'
        entry=int(normal_diag_audit['entry'],16);at=offset(entry)
        assert list(struct.unpack_from('<2I',b,at))==[int(v,16) for v in normal_diag_audit['original_entry_words']]
        struct.pack_into('<2I',b,at,0x52800000,0xd65f03c0)
        at=offset(normal_diag_base,len(diag_code));old_diag=bytes(b[at:at+len(diag_code)]);b[at:at+len(diag_code)]=diag_code
        (out/'gpu-normal-diag-region-audit.json').write_text(json.dumps(normal_diag_audit,indent=2))
        patches.append(dict(va=hex(entry),old=normal_diag_audit['original_entry_words'],new=['0x52800000','0xd65f03c0'],purpose='Disable obsolete core-start entry, including recovery calls'))
        patches.append(dict(va=hex(normal_diag_base),bytes=len(diag_code),limit=hex(normal_diag_limit),original_region_sha256=hashlib.sha256(old_diag).hexdigest(),purpose='SP clock and read-only normal prerequisites in audited obsolete core-start body'))
    (out/'touch-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'touch.elf')]))
    patches.append(dict(va=hex(touch_base),bytes=len(touch),limit=hex(touch_end),
        original_region_sha256=hashlib.sha256(original).hexdigest(),purpose='lmi-only FT3518 I2C thread; reviewed boot mode gates GPIO power/reset; exact ID required'))
    if gpu_probe:
        linked_symbols={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(out/'touch.elf')],text=True).splitlines() if len(v:=line.split())==3}
        if args.lmi_gpu_desktop:
            subprocess.run(['llvm-objcopy','-j','.gpu_desktop','-O','binary',str(out/'touch.elf'),str(out/'gpu-desktop.bin')],check=True)
            desktop_code=(out/'gpu-desktop.bin').read_bytes()
            patches+=desktop_profile['patch'](b,offset,desktop_audit,desktop_code,linked_symbols,symbols)
            (out/'gpu-desktop-region-audit.json').write_text(json.dumps(desktop_audit,indent=2))
        if args.lmi_gpu_rsc_init:
            rd=linked_symbols['rsc_read']-context_base
            wr=linked_symbols['rsc_write']-context_base
            assert struct.unpack_from('<4I',context_code,rd)==(0xb9400008,0xd3407d08,0x2a0803e0,0xd65f03c0), 'RSC read ABI changed'
            assert struct.unpack_from('<3I',context_code,wr)==(0xb9000001,0xd5033f9f,0xd65f03c0), 'RSC write must use w1, never WZR'
        if args.lmi_gpu_rpmh_probe:
            rd=linked_symbols['vote_read']-context_base
            wr=linked_symbols['vote_write']-context_base
            assert struct.unpack_from('<4I',context_code,rd)==(0xb9400008,0xd3407d08,0x2a0803e0,0xd65f03c0), 'RPMh read ABI changed'
            assert struct.unpack_from('<3I',context_code,wr)==(0xb9000001,0xd5033f9f,0xd65f03c0), 'RPMh writes must use w1, never WZR'
        if args.lmi_gpu_stage1_init:
            rd=linked_symbols['ctx_read']-context_base
            wr=linked_symbols['ctx_write']-context_base
            assert struct.unpack_from('<4I',context_code,rd)==(0xb9400008,0xd3407d08,0x2a0803e0,0xd65f03c0), 'Context read ABI changed'
            assert struct.unpack_from('<3I',context_code,wr)==(0xb9000001,0xd5033f9f,0xd65f03c0), 'Context write must use w1, never WZR'
        if args.lmi_gpu_smmu_readonly and not args.lmi_gpu_gmu_route_probe:
            # Pin the audited trapped-load ABI, including explicit zero extension.
            rd=linked_symbols['smmu_rd32']-touch_base
            assert struct.unpack_from('<4I',touch,rd)==(0xb9400008,0xd3407d08,0x2a0803e0,0xd65f03c0), 'SMMU LDR/UXTW ABI changed; audit target disassembly'
        pc=symbols['_redwood_adreno_init'];at=offset(pc)
        old=struct.unpack_from('<I',b,at)[0]
        assert old==0xd10343ff,hex(old)
        target=linked_symbols['lmi_gpu_probe']
        assert -(1<<27)<=target-pc<(1<<27) and (target-pc)%4==0
        new=0x14000000|(((target-pc)//4)&0x3ffffff)
        struct.pack_into('<I',b,at,new)
        patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),target=hex(target),purpose='Replace redwood-only GPU initializer with boot-gated lmi GPU probe'))
        if args.lmi_gpu_zap_load:
            assert struct.unpack_from('<I',b,offset(pc))[0]==new and new&0xfc000000==0x14000000
            assert struct.unpack_from('<2I',b,offset(int(frame_audit['entry'],16)))==(0x52800000,0xd65f03c0)
        if args.lmi_gpu_unsecure:
            assert struct.unpack_from('<I',b,offset(pc))[0]==new and new&0xfc000000==0x14000000
            assert struct.unpack_from('<2I',b,offset(int(unsecure_audit['entry'],16)))==(0x52800000,0xd65f03c0)
            assert struct.unpack_from('<2I',b,offset(int(normal_diag_audit['entry'],16)))==(0x52800000,0xd65f03c0)
    if args.trace_poster_registers:
        touch_symbols={v[2]:int(v[0],16) for line in subprocess.check_output(['llvm-nm',str(out/'touch.elf')],text=True).splitlines() if len(v:=line.split())==3}
        pc=0xfffffff007473a44;at=offset(pc);old=0x97ffde0b
        assert struct.unpack_from('<I',b,at)[0]==old
        target=touch_symbols['lmi_ustacks_regs']
        assert -(1<<27)<=target-pc<(1<<27) and (target-pc)%4==0
        new=0x94000000|(((target-pc)//4)&0x3ffffff)
        struct.pack_into('<I',b,at,new)
        patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),target=hex(target),purpose='bounded ustacks saved-state diagnostic'))
(out/src.name).write_bytes(b)
(out/'probe-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'probe.elf')]))
report=dict(source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),sha256=hashlib.sha256(b).hexdigest(),patches=patches,
    thunk_va=hex(base),thunk_bytes=len(code),instrumented_checkpoints=[52,53,54,55,56,57,58,59,60,61,62]+([63] if args.continue_launchd else []),
    expected_platform_vtable=hex(symbols['__ZTV12GenericARMPE']+16),expected_cpu_vtable=hex(symbols['__ZTV13GenericARMCPU']+16),
    scope='Only PID1 named launchd.ios triggers checkpoint62 at native getpid. Read actual saved EL0 state; host must separately verify Apple image provenance. No desktop claim.',hardware_tested=False)
if args.continue_launchd:
    report.update(ram_only_return=True,return_method='linearize RAM log with IRQs off, then loader_checkpoint(63)',scope='Checkpoint62 remains a stopping probe; checkpoint63 records PID1 launchd.ios getpid then resumes native syscall. SMP stops and verifies other cores OFF before its timer orders the log head/ring and enters the checkpoint return. No storage or peripheral cleanup callback; no desktop claim.')
    report['forced_log_wrap_preflight']=args.force_log_wrap
    report['smp_cpus']=args.smp_cpus
    report['smp_touch_poll_diagnostics']=args.smp_cpus>1 and args.lmi_touch
    report['smp_return'] = dict(enabled=args.smp_cpus>1,source='tools/lmi-smp-return.S',source_sha256=hashlib.sha256((root/'tools/lmi-smp-return.S').read_bytes()).hexdigest(),other_cores_off_required=True,unknown_stop_retains_ram=True,atomic_hex_lines=args.smp_cpus>1,
        affinity_transition_wait_seconds=1,affinity_transition_states=[0,2],affinity_wait_shared_deadline=True)
    report['return_tcr_normalized']=args.normalize_return_tcr
    report['return_stub_readonly_executable']=args.return_stub_ro
    report['return_tables_explicitly_cleaned']=args.clean_return_tables
    report['graphics_mode_observer']=args.trace_graphics
    report['graphics_console_release']=args.release_graphics_console
    report['poster_saved_registers']=args.trace_poster_registers
    report['lmi_gpu_readonly']=dict(enabled=args.lmi_gpu_readonly,source='tools/lmi-gpu-probe.c',
        source_sha256=hashlib.sha256((root/'tools/lmi-gpu-probe.c').read_bytes()).hexdigest(),mmio_writes=False,
        firmware_writes=False,original_gpu_initializer_disabled=gpu_probe)
    report['lmi_gpu_cx_probe']=dict(enabled=args.lmi_gpu_cx_probe,source='tools/lmi-gpu-probe.c',
        source_sha256=hashlib.sha256((root/'tools/lmi-gpu-probe.c').read_bytes()).hexdigest(),
        mmio_writes=['GPUCC_CX_GDSCR clear collapse then restore'],firmware_writes=args.lmi_gpu_tcm_load)
    report['lmi_gpu_clock_probe']=dict(enabled=args.lmi_gpu_clock_probe,
        mmio_writes=['GPUCC crystal-source branch votes 1078/109c/1098 then restore enable bits'],
        firmware_writes=args.lmi_gpu_tcm_load,smmu_writes=False)
    report['lmi_gpu_gmu_readonly']=dict(enabled=args.lmi_gpu_gmu_readonly,
        gmu_mapping='0x03d6a000+0x30000',gmu_register_writes=args.lmi_gpu_tcm_load,
        reads=['CM3_SYSRESET','ALWAYS_ON_COUNTER_L'],timing='CNTVCT_EL0/CNTFRQ_EL0')
    report['lmi_gpu_tcm_load']=dict(enabled=args.lmi_gpu_tcm_load,firmware='a650_gmu.bin',
        firmware_sha256='df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c',
        volatile_tcm_bytes=18404,cm3_reset_released=False,smmu_writes=False,
        runtime_firmware_crc32='5c66275c',tcm_original_words_snapshotted=True,
        tcm_restore_readback_required=True,firmware_execution=False,persistent_storage_writes=False,
        recovery='Restore all18404 original TCM bytes and verify, then restore clocks/CX and reboot Android')
    report['lmi_gpu_smmu_readonly']=dict(enabled=args.lmi_gpu_smmu_readonly,
        mapping='0x03da0000+0x10000',gmu_reset_released=False,smmu_writes=False,
        registers='GR0 IDR0/1/2/7, nonsecure sCR0/sGFSR, at most128 SMR/S2CR pairs',
        excluded='secure aliases,GR1,CB,TCU,TBU',gcc_bus_clocks=['0x7100c','0x71018'],clock_vote_restore=True)
    report['lmi_gpu_arc_inventory']=dict(enabled=args.lmi_gpu_arc_inventory,source='tools/lmi-gpu-resources.c',source_sha256=hashlib.sha256((root/'tools/lmi-gpu-resources.c').read_bytes()).hexdigest(),physical='0x80860000',bytes=131072,rpmh_writes=False)
    report['lmi_gpu_tile']=dict(enabled=args.lmi_gpu_tile,source='tools/lmi-gpu-tile.c',source_sha256=hashlib.sha256((root/'tools/lmi-gpu-tile.c').read_bytes()).hexdigest(),mode=46,width=16,height=16,pitch=64,iova='0x1010100',pixel_validation='all256 pixels, both128-byte guards, all surrounding scratch words, old and fresh GPU fences',hardware_acceleration_verified=False)
    report['lmi_gpu_desktop']=dict(enabled=args.lmi_gpu_desktop,source='tools/lmi-gpu-desktop.c',source_sha256=hashlib.sha256((root/'tools/lmi-gpu-desktop.c').read_bytes()).hexdigest(),mode=46,desktop_acceleration_verified=False,hardware_acceleration_verified=False)
    report['lmi_gpu_unsecure']=dict(enabled=args.lmi_gpu_unsecure,mode=46,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-unsecure.c').read_bytes()).hexdigest(),normal_packet=[0x70e60001,0],writeback_iova='0x1010004',trust_control_register_writes=False)
    report['lmi_gpu_zap_load']=dict(enabled=args.lmi_gpu_zap_load,mode=45,pas=13,payload_sha256='a415e5452fa8f597670a6e51010e97bfabca7d20fbce8044caed64d9d5873113',source_sha256=hashlib.sha256((root/'tools/lmi-gpu-zap-load.c').read_bytes()).hexdigest(),secure_mode_packet_sent=False)
    report['lmi_gpu_zap_metadata']=dict(enabled=args.lmi_gpu_zap_metadata,mode=44,pas=13,operation='INIT_IMAGE only',metadata_sha256='5bcec6a60f2d5753fa69671bd409bba1adcaf5dedf265ab1f8fa474ab4e552bb',cache_policy='owned managed pages Normal-NC via pmap API; retain',source_sha256=hashlib.sha256((root/'tools/lmi-gpu-zap-metadata.c').read_bytes()).hexdigest())
    report['lmi_gpu_scm_query']=dict(enabled=args.lmi_gpu_scm_query,mode=43,pas_state_changed=False,memory_shared=False,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-scm.c').read_bytes()).hexdigest())
    report['lmi_gpu_cp_config_ready']=dict(enabled=args.lmi_gpu_cp_config_ready,mode=42)
    report['lmi_gpu_cp_config_plan']=dict(enabled=args.lmi_gpu_cp_config_plan,mode=41,cp_started=False)
    report['lmi_gpu_fal_veto']=dict(enabled=args.lmi_gpu_fal_veto,mode=40)
    report['lmi_gpu_core_access']=dict(enabled=args.lmi_gpu_core_access,mode=39,read_only=True,cp_started=False)
    report['lmi_gpu_cp_sp_clock']=dict(enabled=args.lmi_gpu_cp_sp_clock,mode=38)
    report['lmi_gpu_cp_fence']=dict(enabled=args.lmi_gpu_cp_fence,mode=37)
    report['lmi_gpu_cp']=dict(enabled=args.lmi_gpu_cp,mode=36,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-cp.c').read_bytes()).hexdigest(),secure_writes=False)
    report['lmi_gpu_core_memory']=dict(enabled=args.lmi_gpu_core_memory,mode=35,pages=20,cb=1,asid=2,sid=0,mask=0x401,cp_started=False,source='tools/lmi-gpu-core-memory.c',source_sha256=hashlib.sha256((root/'tools/lmi-gpu-core-memory.c').read_bytes()).hexdigest())
    report['lmi_gpu_cp_plan']=dict(enabled=args.lmi_gpu_cp_plan,mode=34,read_only=True,cp_started=False)
    report['lmi_gpu_gx']=dict(enabled=args.lmi_gpu_gx,mode=33,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-gx.c').read_bytes()).hexdigest(),frequency_index=1,gpu_oob_held=True,cp_submission=False)
    report['lmi_gpu_hfi_core']=dict(enabled=args.lmi_gpu_hfi_core,mode=32,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-hfi-core.c').read_bytes()).hexdigest(),off_bandwidth_only=True,gx_power_requested=False)
    report['lmi_gpu_hfi_perf']=dict(enabled=args.lmi_gpu_hfi_perf,mode=31,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-hfi-perf.c').read_bytes()).hexdigest(),hfi_ring_offset=256,gx_power_requested=False)
    report['lmi_gpu_table_plan']=dict(enabled=args.lmi_gpu_table_plan,mode=30,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-table-plan.c').read_bytes()).hexdigest(),read_only=True,gx_power_requested=False)
    report['lmi_gpu_hfi_io']=dict(enabled=args.lmi_gpu_hfi_io,mode=29,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-hfi-io.c').read_bytes()).hexdigest(),bidirectional_dma_requested=True,hardware_acceleration_verified=False)
    report['lmi_gpu_gmu_boot']=dict(enabled=args.lmi_gpu_gmu_boot,mode=28,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-boot.c').read_bytes()).hexdigest(),chipid='0x06050200',load_mode=2,fw_init_expected='0x100 mask0x1ff',hfi_status_expected=1,dependencies_retained_until_reset=True,submit_fence_pixels_verified=False)
    report['lmi_gpu_gmu_route_probe']=dict(enabled=args.lmi_gpu_gmu_route_probe,mode=27,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-route.c').read_bytes()).hexdigest(),sid=5,mask=0x400,smmu_writes=True,translation_enable=True,detach_required=not args.lmi_gpu_gmu_boot,firmware_execution=args.lmi_gpu_gmu_boot)
    report['lmi_gpu_gmu_200mhz_probe']=dict(enabled=args.lmi_gpu_gmu_200mhz_probe,mode=26,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-clock.c').read_bytes()).hexdigest(),pll_writes=False,configuration_only=True,frequency_measured=False,restore_required=not args.lmi_gpu_gmu_boot)
    report['lmi_gpu_rsc_pdc_vote_probe']=dict(enabled=args.lmi_gpu_rsc_pdc_vote_probe,mode=25,hidden_writes=False,smmu_writes=False,firmware_execution=False)
    report['lmi_gpu_pdc_enable_probe']=dict(enabled=args.lmi_gpu_pdc_enable_probe,mode=24,hidden_writes=False,pdc_sequence_upload=False,trigger=False)
    report['lmi_gpu_rsc_sequence_probe']=dict(enabled=args.lmi_gpu_rsc_sequence_probe,mode=46 if args.lmi_gpu_unsecure else 45 if args.lmi_gpu_zap_load else 44 if args.lmi_gpu_zap_metadata else 43 if args.lmi_gpu_scm_query else 42 if args.lmi_gpu_cp_config_ready else 41 if args.lmi_gpu_cp_config_plan else 40 if args.lmi_gpu_fal_veto else 39 if args.lmi_gpu_core_access else 38 if args.lmi_gpu_cp_sp_clock else 37 if args.lmi_gpu_cp_fence else 36 if args.lmi_gpu_cp else 35 if args.lmi_gpu_core_memory else 34 if args.lmi_gpu_cp_plan else 33 if args.lmi_gpu_gx else 32 if args.lmi_gpu_hfi_core else 31 if args.lmi_gpu_hfi_perf else 30 if args.lmi_gpu_table_plan else 29 if args.lmi_gpu_hfi_io else 28 if args.lmi_gpu_gmu_boot else 27 if args.lmi_gpu_gmu_route_probe else 26 if args.lmi_gpu_gmu_200mhz_probe else 25 if args.lmi_gpu_rsc_pdc_vote_probe else 24 if args.lmi_gpu_pdc_enable_probe else 23,sequence_words=5,hidden_writes=False,pdc_writes=args.lmi_gpu_pdc_enable_probe)
    report['lmi_gpu_rsc_init']=dict(enabled=args.lmi_gpu_rsc_init,mode=46 if args.lmi_gpu_unsecure else 45 if args.lmi_gpu_zap_load else 44 if args.lmi_gpu_zap_metadata else 43 if args.lmi_gpu_scm_query else 42 if args.lmi_gpu_cp_config_ready else 41 if args.lmi_gpu_cp_config_plan else 40 if args.lmi_gpu_fal_veto else 39 if args.lmi_gpu_core_access else 38 if args.lmi_gpu_cp_sp_clock else 37 if args.lmi_gpu_cp_fence else 36 if args.lmi_gpu_cp else 35 if args.lmi_gpu_core_memory else 34 if args.lmi_gpu_cp_plan else 33 if args.lmi_gpu_gx else 32 if args.lmi_gpu_hfi_core else 31 if args.lmi_gpu_hfi_perf else 30 if args.lmi_gpu_table_plan else 29 if args.lmi_gpu_hfi_io else 28 if args.lmi_gpu_gmu_boot else 27 if args.lmi_gpu_gmu_route_probe else 26 if args.lmi_gpu_gmu_200mhz_probe else 25 if args.lmi_gpu_rsc_pdc_vote_probe else 24 if args.lmi_gpu_pdc_enable_probe else 23 if args.lmi_gpu_rsc_sequence_probe else 22,source_sha256=hashlib.sha256((root/'tools/lmi-gpu-rsc-init.c').read_bytes()).hexdigest(),gpu_owned_only=True,exact_restore_required=not args.lmi_gpu_gmu_boot,rpmh_requests=args.lmi_gpu_rsc_pdc_vote_probe,firmware_execution=args.lmi_gpu_gmu_boot)
    report['lmi_gpu_rsc_state']=dict(enabled=args.lmi_gpu_rsc_state,mode=21,register_count=56,mmio_writes=False,qmp_messages=False,cm3_reset_required=True)
    report['lmi_gpu_rscc_readonly']=dict(enabled=args.lmi_gpu_rscc_readonly,physical='0x03de0000',bytes=65536,expected_config='0x4000000a',tcs_count=10,commands_per_tcs=8,rpmh_writes=False)
    report['lmi_gpu_rpmh_probe']=dict(enabled=args.lmi_gpu_rpmh_probe,source='tools/lmi-gpu-rpmh.c',source_sha256=hashlib.sha256((root/'tools/lmi-gpu-rpmh.c').read_bytes()).hexdigest(),gpu_drv0=True,apss_drv2_writes=False,votes_retained_until_reset=True,frequency_change=False,firmware_execution=False)
    report['lmi_gpu_rscc_sde_probe']=dict(enabled=args.lmi_gpu_rscc_sde_probe,register='RSCC STATUS0 BIT24',restore_on_idle=True,retained_on_pending=True)
    report['lmi_gpu_rpmh_arc_slot_probe']=dict(enabled=args.lmi_gpu_rpmh_arc_slot_probe,slot=1,irq_mask=2,firmware_sha256='df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c')
    report['lmi_gpu_rpmh_bus_probe']=dict(enabled=args.lmi_gpu_rpmh_bus_probe,clock_offsets=['0x7100c','0x71018'],before_gpu_requests=True,retain_on_pending=True)
    report['lmi_gpu_rpmh_interface_probe']=dict(enabled=args.lmi_gpu_rpmh_interface_probe,register='0x03d7e3a0',mask='0xf11',cm3_reset_required=True,firmware_init_required=0,restore_on_idle=True,retained_on_pending=True)
    report['lmi_gpu_stage1_init']=dict(enabled=args.lmi_gpu_stage1_init,mode=13,cbar_requested='0x1f300',cbar_restored=False,teardown='leave disabled without routes until bounded reboot',local_tlb_sync=True,asid=1,translation_enabled=False,firmware_execution=False)
    report['lmi_gpu_wired_context']=dict(enabled=args.lmi_gpu_wired_context,mode=46 if args.lmi_gpu_unsecure else 45 if args.lmi_gpu_zap_load else 44 if args.lmi_gpu_zap_metadata else 43 if args.lmi_gpu_scm_query else 42 if args.lmi_gpu_cp_config_ready else 41 if args.lmi_gpu_cp_config_plan else 40 if args.lmi_gpu_fal_veto else 39 if args.lmi_gpu_core_access else 38 if args.lmi_gpu_cp_sp_clock else 37 if args.lmi_gpu_cp_fence else 36 if args.lmi_gpu_cp else 35 if args.lmi_gpu_core_memory else 34 if args.lmi_gpu_cp_plan else 33 if args.lmi_gpu_gx else 32 if args.lmi_gpu_hfi_core else 31 if args.lmi_gpu_hfi_perf else 30 if args.lmi_gpu_table_plan else 29 if args.lmi_gpu_hfi_io else 28 if args.lmi_gpu_gmu_boot else 27 if args.lmi_gpu_gmu_route_probe else 26 if args.lmi_gpu_gmu_200mhz_probe else 25 if args.lmi_gpu_rsc_pdc_vote_probe else 24 if args.lmi_gpu_pdc_enable_probe else 23 if args.lmi_gpu_rsc_sequence_probe else 22 if args.lmi_gpu_rsc_init else 21 if args.lmi_gpu_rsc_state else 20 if args.lmi_gpu_rpmh_arc_slot_probe else 19 if args.lmi_gpu_rpmh_bus_probe else 18 if args.lmi_gpu_rpmh_interface_probe else 17 if args.lmi_gpu_rscc_sde_probe else 16 if args.lmi_gpu_rpmh_probe else 15 if args.lmi_gpu_rscc_readonly else 14 if args.lmi_gpu_arc_inventory else 13 if args.lmi_gpu_stage1_init else 12,source='tools/lmi-gpu-context.c',source_sha256=hashlib.sha256((root/'tools/lmi-gpu-context.c').read_bytes()).hexdigest(),tcr2_requested='0x38071',cbar_written=args.lmi_gpu_stage1_init,translation_enabled=False,stream_published=False,firmware_execution=False)
    report['lmi_gpu_ram_hfi']=dict(enabled=args.lmi_gpu_ram_hfi,hfi_iova='0x60001000',hfi_bytes=20480)
    report['lmi_gpu_ram_plan']=dict(enabled=args.lmi_gpu_ram_plan,source='tools/lmi-gpu-ram.c',
        source_sha256=hashlib.sha256((root/'tools/lmi-gpu-ram.c').read_bytes()).hexdigest(),
        firmware_sha256='df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c',
        payload_pages=42 if args.lmi_gpu_ram_hfi else 37,table_pages=5,page_bytes=4096,physical_bits=36,
        allocator_symbol='_kmem_alloc_guard_internal',free_symbol='_kmem_free_external',allocator_abi='map,size,mask,flags,guard(tag3),NULL; status/address aggregate',
        mmio_access=args.lmi_gpu_wired_context or args.lmi_gpu_gmu_route_probe,smmu_writes=args.lmi_gpu_wired_context or args.lmi_gpu_gmu_route_probe,firmware_execution=args.lmi_gpu_gmu_boot,
        cleanup='retain while firmware active or state uncertain until bounded reset' if args.lmi_gpu_gmu_boot else 'free only after confirmed SMR revocation, local TLB sync and context restoration; retain otherwise' if args.lmi_gpu_gmu_route_probe else 'free only after complete context restoration; retain on unconfirmed detach' if args.lmi_gpu_wired_context else 'free complete original wired allocation after CPU verification; no DMA references published')
    report['lmi_gpu_cb0_readonly']=dict(enabled=args.lmi_gpu_cb0_readonly,
        context=0,read_only=not (args.lmi_gpu_cb0_format_probe or args.lmi_gpu_cb0_context_probe),ownership_granted=False,smmu_writes=args.lmi_gpu_cb0_format_probe or args.lmi_gpu_cb0_context_probe,
        snapshots=3,spacing_us=1000)
    report['lmi_gpu_cb0_table_probe']=dict(enabled=args.lmi_gpu_cb0_table_probe,root_zero_filled=True,cbar_written=False,translation_enabled=False)
    report['lmi_gpu_cb0_context_probe']=dict(enabled=args.lmi_gpu_cb0_context_probe,translation_enabled=False,stream_published=False,firmware_execution=False)
    report['lmi_gpu_cb0_format_probe']=dict(enabled=args.lmi_gpu_cb0_format_probe,
        writes=['CBA2R0.RW64 set then original restore'],translation_enabled=False,
        stream_published=False,firmware_execution=False)
    report['lmi_touch_driver']=dict(enabled=args.lmi_touch,source='tools/lmi-touch.c',
        timing_header='tools/lmi-touch-timing.h',timing_header_sha256=hashlib.sha256((root/'tools/lmi-touch-timing.h').read_bytes()).hexdigest(),
        gpio_edge_timing='19.2MHz CNTVCT busy minimum5us; long waits retain yielding delay_for_interval',
        compact_diagnostics=args.lmi_gpu_gmu_route_probe,
        optimization='-Oz' if gpu_compact else '-Os' if gpu_probe else '-O2',
        source_sha256=hashlib.sha256((root/'tools/lmi-touch.c').read_bytes()).hexdigest(),
        firmware_writes=False,regulator_policy='Modes5/6 vote DT resource ldoc1=1800mV/enable/HPM through verified cmd-db and idle active TCS; mode6 requires all command completion bits',
        power_reset_policy='Modes3/4/5/6 enable board GPIO72 and pulse reset38; restore GPIOs after exit',
        requires_boot_arg='touchscreen=1 lmi_touch=1 (inherited probe),2 (inherited samples),3 (GPIO power probe),4 (GPIO power samples),5 (ldoc1 power probe),6 (ldoc1 power samples)')
    report['return_trace']=dict(enabled=args.trace_return,thunk_va=hex(trace_base),thunk_bytes=len(trace) if args.trace_return else 0)
    if args.normalize_return_tcr:
        report['return_tcr_policy']='Checkpoint63 only: local return TCR value uses TG0=4KiB and T0SZ=26; live TCR remains unchanged until the native TTBR0/table handoff. TTBR1 fields and non63 behavior preserved.'
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
