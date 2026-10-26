"""Build the complete upstream loader with a guarded lmi USB bring-up profile."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil
import struct
import subprocess
import argparse
import re
from lmi_checkpoint_policy import STAGE_CHOICES,checkpoints_through

parser=argparse.ArgumentParser()
parser.add_argument('--checkpoints', action='store_true', help='Enable only explicitly reviewed XNU checkpoints')
parser.add_argument('--smp-cpus',type=int,choices=(1,2,4,8),default=1,help='Checkpoint63-only lmi SMP; requires matching SMP RAM-return kernel')
parser.add_argument('--fb-threads',type=int,choices=range(1,9),default=1,help='Desktop framebuffer scaling workers, bounded by enabled CPU count')
parser.add_argument('--fb-queue',type=int,choices=(1,2),default=2,help='Desktop pending-frame limit')
parser.add_argument('--fb-beat',type=int,choices=(0,1),default=1,help='Desktop software pacing; not panel vsync')
parser.add_argument('--display-census',action='store_true',help='Read-only fixed DPU register snapshots before and after checkpoint63')
parser.add_argument('--max-checkpoint', type=int, choices=STAGE_CHOICES, default=1)
parser.add_argument('--ios-observe-seconds',type=int,choices=(2,25,45,180),default=25,help='Bounded checkpoint63 observation;180 seconds allows first-boot database seeding')
parser.add_argument('--ios-startup-stacks',action='store_true',help='Two bounded SpringBoard main-thread snapshots at32/42 seconds during checkpoint63')
parser.add_argument('--ios-lsd-stacks',action='store_true',help='Two bounded lsd snapshots, at most96 threads each;32/42s or60/120s for the180s profile')
parser.add_argument('--ios-poster-stacks',action='store_true',help='Bounded CollectionsPoster snapshots at130/150 seconds during180second run')
parser.add_argument('--ios-top-stacks',action='store_true',help='Two existing native CPU-accounting snapshots at60/120 seconds; desktop180 only')
parser.add_argument('--ios-process-stacks',choices=('Preferences','PosterBoard','backboardd','cfprefsd'),help='Two bounded service snapshots at130/155 seconds; desktop180 only')
parser.add_argument('--lmi-touch-probe',action='store_true',help='Checkpoint63 only: inherited-power FT3518 I2C ID probe; no sample posting')
parser.add_argument('--lmi-touch-power-probe',action='store_true',help='Checkpoint63 only: FT3518 ID probe with board-DT GPIO72 enable / reset38 pulse; no PMIC or firmware writes')
parser.add_argument('--lmi-touch-supply-probe',action='store_true',help='Checkpoint63 only: board-DT ldoc1 1.8V vote plus GPIO power/reset, ID probe only')
parser.add_argument('--lmi-touch-input',action='store_true',help='Checkpoint63 only: verified lmi FT3518 power and ID gated physical input')
parser.add_argument('--lmi-gpu-readonly',action='store_true',help='Checkpoint63 only: read-only lmi GPU external clock and fuse inventory')
parser.add_argument('--lmi-gpu-cx-probe',action='store_true',help='Checkpoint63 only: cold CX-domain power-on and restore')
parser.add_argument('--lmi-gpu-clock-probe',action='store_true',help='Extend cold CX probe with reversible crystal-source GMU clocks')
parser.add_argument('--lmi-gpu-gmu-readonly',action='store_true',help='Extend clock probe with read-only CM3 reset and AO counter')
parser.add_argument('--lmi-gpu-tcm-load',action='store_true',help='Extend GMU probe with TCM load/readback under asserted RESET')
parser.add_argument('--lmi-gpu-smmu-readonly',action='store_true',help='Extend GMU probe with SMMU GR0/stream inventory and reversible bus clocks')
parser.add_argument('--lmi-gpu-ram-plan',action='store_true',help='Owned RAM GMU prealloc/software tables only; no GPU MMIO')
parser.add_argument('--lmi-gpu-cb0-readonly',action='store_true',help='Extend SMMU inventory with finite read-only CB0 snapshot')
parser.add_argument('--lmi-gpu-cb0-format-probe',action='store_true',help='Reversible disabled-CB0 format bit capability test')
parser.add_argument('--trace-return-stub',action='store_true',help='Physical GOP markers after MMUoff, context restore and UEFI MMUon; lmi checkpoint63 diagnostic')
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
parser.add_argument('--lmi-gpu-tile',action='store_true',help='Explicit mode46 owned16x16 GPU clear with exact pixels and guards')
parser.add_argument('--lmi-gpu-desktop',action='store_true',help='Opt-in desktop service after mode46 normal and tile proof')
parser.add_argument('--lmi-gpu-zap-load',action='store_true',help='Mode45: owned aligned original GPU13 payload with MEM_SETUP/AUTH_AND_RESET after accepted MDT')
args=parser.parse_args()
assert args.smp_cpus==1 or (args.checkpoints and args.max_checkpoint==63 and args.trace_return_stub)
assert args.fb_threads<=args.smp_cpus and (args.fb_threads==1 or args.lmi_gpu_desktop)
assert args.lmi_gpu_desktop or (args.fb_queue==2 and args.fb_beat==1 and not args.display_census)
assert not args.display_census or (args.max_checkpoint==63 and args.trace_return_stub)
assert not args.lmi_gpu_tile or args.lmi_gpu_unsecure
assert not args.lmi_gpu_desktop or args.lmi_gpu_tile
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
assert not args.lmi_gpu_clock_probe or args.lmi_gpu_cx_probe
assert not args.lmi_gpu_gmu_readonly or args.lmi_gpu_clock_probe
assert not args.lmi_gpu_tcm_load or args.lmi_gpu_gmu_readonly
assert not args.lmi_gpu_smmu_readonly or (args.lmi_gpu_gmu_readonly and not args.lmi_gpu_tcm_load)
# Only the authenticated normal-mode desktop profile may use the longer GLES window.
gpu_observation_bounded = args.ios_observe_seconds==25 or (args.lmi_gpu_desktop and args.ios_observe_seconds in (45,180))
# The existing FT3518 path uses ldoc1 on apps DRV2; GPU votes use GPU DRV0.
# Restore input only with the normal/tile/desktop chain, preserving both paths' guards.
gpu_touch_combined = args.lmi_gpu_desktop and args.lmi_touch_input and args.ios_observe_seconds in (45,180)
assert not args.lmi_gpu_ram_plan or (args.checkpoints and args.max_checkpoint==63 and gpu_observation_bounded and not any((args.lmi_gpu_readonly,args.lmi_gpu_cx_probe and not (args.lmi_gpu_wired_context or args.lmi_gpu_gmu_route_probe),args.lmi_touch_probe,args.lmi_touch_power_probe,args.lmi_touch_supply_probe,args.lmi_touch_input and not gpu_touch_combined)))
assert args.checkpoints or args.max_checkpoint==1
assert not args.trace_return_stub or (args.checkpoints and args.max_checkpoint==63)
assert not args.ios_startup_stacks or (args.checkpoints and args.max_checkpoint==63 and args.ios_observe_seconds==45)
assert not args.ios_lsd_stacks or (args.checkpoints and args.max_checkpoint==63 and args.ios_observe_seconds in (45,180))
assert not (args.ios_startup_stacks and args.ios_lsd_stacks)
assert not args.ios_poster_stacks or (args.checkpoints and args.max_checkpoint==63 and args.ios_observe_seconds==180)
assert not args.ios_top_stacks or (args.checkpoints and args.max_checkpoint==63 and args.lmi_gpu_desktop and args.ios_observe_seconds==180)
assert not args.ios_process_stacks or (args.checkpoints and args.max_checkpoint==63 and args.lmi_gpu_desktop and args.ios_observe_seconds==180)
assert sum((args.ios_startup_stacks,args.ios_lsd_stacks,args.ios_poster_stacks,args.ios_top_stacks,bool(args.ios_process_stacks)))<=1
assert not args.lmi_touch_probe or (args.checkpoints and args.max_checkpoint==63)
assert not args.lmi_touch_power_probe or (args.checkpoints and args.max_checkpoint==63)
assert not (args.lmi_touch_probe and args.lmi_touch_power_probe)
assert not args.lmi_touch_supply_probe or (args.checkpoints and args.max_checkpoint==63)
assert not args.lmi_touch_input or (args.checkpoints and args.max_checkpoint==63 and (args.ios_observe_seconds==180 or gpu_touch_combined))
assert sum((args.lmi_touch_probe,args.lmi_touch_power_probe,args.lmi_touch_supply_probe,args.lmi_touch_input))<=1
assert not args.lmi_gpu_readonly or (args.checkpoints and args.max_checkpoint==63 and args.ios_observe_seconds==25 and not args.lmi_touch_input)
assert not args.lmi_gpu_cx_probe or (args.checkpoints and args.max_checkpoint==63 and gpu_observation_bounded and (not args.lmi_touch_input or gpu_touch_combined) and not args.lmi_gpu_readonly)
# Checkpoint IDs reflect instrumentation history, not execution order.
checkpoints=checkpoints_through(args.max_checkpoint)
permitted=[999,*checkpoints] if args.checkpoints else []
kernel_floor=0x100000000 if args.checkpoints and args.max_checkpoint>=17 else 0

root=Path(__file__).resolve().parents[1]
up=root/'hackios/xnuloader'
out=root/'out/lmi-loader'
out.mkdir(parents=True,exist_ok=True)
original=(up/'loader.c').read_text()
assert hashlib.sha256(original.encode()).hexdigest()=='95ce0c52edb90d95c972a6cd865203e2b1d037289f5093c59196e6eb993578c6'
s=original

def replace_once(before,after):
    global s
    assert s.count(before)==1,before[:80]
    s=s.replace(before,after,1)

def replace_function(signature,next_marker,replacement):
    global s
    start=s.index(signature)
    end=s.index(next_marker,start)
    s=s[:start]+replacement+s[end:]

if args.display_census:
    census=(root/'tools/lmi-display-census.c').read_text()
    replace_once('static char log_buf[32768];','static char log_buf[131072];')
    anchor='static int\nrun_kernel(int have_checkpoint, uint64_t checkpoint)'
    replace_once(anchor,census+'\n'+anchor)
    guard='checkpoint==63 && PLAT==&platform_lmi && SCREEN.base==0x9c000000ULL && SCREEN.width==1080 && SCREEN.height==2400 && SCREEN.stride==4320 && running_live==NULL'
    replace_once('\tif (loader_save_ctx() == 0) {',
        f'\tlmi_display_census("before", {guard});\n\tif (loader_save_ctx() == 0) {{')
    replace_once('\thc_take_back("the kernel came back");   /* before anything here touches the storage */',
        '\thc_take_back("the kernel came back");   /* before anything here touches the storage */\n'+f'\tlmi_display_census("after", {guard});')

if args.trace_return_stub:
    # No stack, calls or memory reads: the first mark runs with MMU/cache off.
    # x0-x10 and x18-x30 retain the native stub's live values. GOP geometry is
    # the captured lmi BGRX framebuffer, not the virtual iPhone surface.
    def stub_mark(stage,color):
        x=960+32*(stage%4);y=2304+24*(stage//4)
        addr=0x9c000000+(y*1080+x)*4
        assert addr+15*4320+64<=0x9c000000+4320*2400
        ops=[f'movz x11, #{addr&0xffff}',f'movk x11, #{addr>>16}, lsl #16',
             f'movz w12, #{color&0xffff}',f'movk w12, #{color>>16}, lsl #16',
             'mov w13, #16','6:','mov w14, #16','7:',
             'str w12, [x11], #4','subs w14, w14, #1','b.ne 7b',
             # Only the last mark uses UEFI's cacheable mapping. A row can
             # straddle two64-byte lines because the pitch is4320 bytes.
             *(['sub x15, x11, #64','dc cvac, x15','sub x15, x11, #1','dc cvac, x15'] if stage>=2 else []),
             'add x11, x11, #0x1000','add x11, x11, #0xa0',
             'subs w13, w13, #1','b.ne 6b','dsb sy']
        return ''.join('        '+__import__('json').dumps('  '+op+'\n')+'\n' for op in ops)
    mark_before_gic=stub_mark(3,0x0000ffff)
    mark_after_gic=stub_mark(4,0x00ff00ff)
    mark_after_daif=stub_mark(5,0x00ffff00)
    mark_function='''
static void lmi_return_mark(unsigned stage, uint32_t color)
{
    unsigned index=stage>=16?stage-16:stage;
    unsigned x=(stage>=16?800:960)+32*(index%4),y=2304+24*(index/4);
    uintptr_t base=0x9c000000ULL+(y*1080+x)*4;
    volatile uint32_t *p=(volatile uint32_t *)base;
    for (unsigned y=0;y<16;y++) {
        for (unsigned x=0;x<16;x++) p[x]=color;
        uintptr_t row=(uintptr_t)p;
        uintptr_t end=row+64;
        for (uintptr_t line=row&~63ULL;line<end;line+=64) __asm__ volatile("dc cvac, %0"::"r"(line));
        p=(volatile uint32_t *)((uintptr_t)p+4320);
    }
    __asm__ volatile("dsb sy" ::: "memory");
}
static int lmi_usb_trace;
static uint32_t lmi_usb_seen;
static void lmi_usb_mark(unsigned stage,uint32_t color)
{
    if (!lmi_usb_trace || stage<15 || stage>26) return;
    uint32_t mask=1u<<(stage-15);
    if (lmi_usb_seen&mask) return;
    lmi_usb_seen|=mask;
    lmi_return_mark(stage,color);
}
'''
    start=s.index('        "loader_return_stub:\\n"')
    end=s.index('\n        );',start)
    stub=s[start:end]
    before='        "  isb\\n"\n        "  adrp x10, loader_ctx\\n"'
    assert stub.count(before)==1
    stub=stub.replace(before,'        "  isb\\n"\n'+stub_mark(0,0x00ff0000)+'        "  adrp x10, loader_ctx\\n"',1)
    before='        "  ldr x9, [x10, #24]\\n  msr sctlr_el1, x9\\n"\n        "  isb\\n"'
    assert stub.count(before)==1
    stub=stub.replace(before,stub_mark(1,0x0000ff00)+before+'\n'+stub_mark(2,0x000000ff),1)
    s=s[:start]+stub+s[end:]

replace_once('#define PAYLOAD_BASE        0xF0000000ULL',
    'static uint64_t lmi_payload_base;\n#define PAYLOAD_BASE        (lmi_payload_base)')
if kernel_floor:
    # Stay in UEFI ConventionalMemory; do not force a base or allocate reservations.
    # VM may manage its entire window, so exclude Android's low reserved ranges.
    replace_once('uint64_t lo = d->phys_start, hi = d->phys_start + (d->pages << 12);',
        'uint64_t lo = d->phys_start, hi = d->phys_start + (d->pages << 12);\n'
        '        if (lo<0x100000000ULL) lo=0x100000000ULL;\n'
        '        if (hi<=lo) continue;')
platform='''static const struct platform platform_lmi = {
    .name="lmi", .io_base=0x00400000, .io_size=0x3fc00000,
    .gic_dist=0x17a00000, .gic_redist=0x17a60000,
    .uart=0, .psci_hvc=0, .log_other_cpu=0,
    .cores=8, .core_shift=8, .small_cores=0x0f, .fb_base=0x9c000000,
};

'''
replace_once('static const struct platform platform_redwood = {',platform+'static const struct platform platform_redwood = {')
replace_once('static const struct platform *const platforms[] = {','static const struct platform *const platforms[] = {\n\t&platform_lmi,')
replace_function('static efi_block_io *\nfind_log_partition(void)',
    '/*\n * The "staged" buffer',
    'static efi_block_io *\nfind_log_partition(void) { return NULL; }\n\n')
replace_function('static void\nwrite_logs(const char *klog, uint64_t klog_len)',
    'static void\nflush_log(',
    'static void\nwrite_logs(const char *klog, uint64_t klog_len) { compose_logs(klog,klog_len); }\n\n')
replace_once('block_write_part = (int)block_shared.parts;',
             'block_write_part = -1; /* lmi: no writable storage partition */')
replace_once('s = bio->write_blocks(bio, bio->media->media_id, lba, bytes, block_buffer);',
             's = EFI_ERROR_BIT | 8; /* EFI_WRITE_PROTECTED: Android storage stays read-only */')
s=s.replace('bio->flush_blocks(bio);','(void)0; /* persistent storage flushing disabled */')
assert '->write_blocks' not in s and '->flush_blocks' not in s

# Keep commands that only query, copy RAM or reset. Kernel execution and
# board-specific peripheral tests remain unreachable from this bring-up server.
replace_once('fb_command(char *cmd)\n{','''fb_command(char *cmd)
{
    if (!(starts_with(cmd,"getvar:") || starts_with(cmd,"download:") ||
          str_eq(cmd,"upload") || str_eq(cmd,"oem log") || str_eq(cmd,"oem screenshot") ||
          str_eq(cmd,"oem memmap") || str_eq(cmd,"reboot") || str_eq(cmd,"oem reboot"))) {
        fb_reply("FAIL","lmi bring-up: kernel execution disabled");
        return;
    }
''')
if args.checkpoints:
    replace_once('str_eq(cmd,"oem memmap") || str_eq(cmd,"reboot") || str_eq(cmd,"oem reboot")))',
        'str_eq(cmd,"oem memmap") || str_eq(cmd,"reboot") || str_eq(cmd,"oem reboot") ||\n'
        '          str_eq(cmd,"oem selftest") || '+ ' || '.join(f'str_eq(cmd,"oem run {n}")' for n in checkpoints)+'))')
    replace_once('lmi bring-up: kernel execution disabled', 'lmi: only selftest and checkpoints '+','.join(map(str,checkpoints))+' permitted')
    # Even a future caller cannot bypass the checkpoint limit or inject boot
    # arguments. SMP is an explicit checkpoint63 profile only.
    replace_once('\tconst uint8_t *kernel = pi.kernel;', '''    if (!have_checkpoint || !(LMI_CHECKPOINT_ALLOWED)) {
        print("lmi: refusing unrestricted kernel execution\\n"); return 0;
    }
    pi.cmdline="-v";
    pi.forced_base=0;
    pi.resident_rd=0;
\tconst uint8_t *kernel = pi.kernel;''')
    s=s.replace('LMI_CHECKPOINT_ALLOWED',' || '.join(f'checkpoint=={n}' for n in permitted))
if 62 in checkpoints:
    # Root images may exceed the USB payload, but still live exclusively in
    # the successfully claimed LoaderData window. No partition command added.
    replace_once('str_eq(cmd,"oem selftest") || ',
        'str_eq(cmd,"oem selftest") || str_eq(cmd,"oem ramdisk") || str_eq(cmd,"oem ramdisk none") || ')
    replace_once('    pi.cmdline="-v";',
        f'    pi.cmdline=(checkpoint==63) ? "-v systrace=0 applog=1 loader_return_after={args.ios_observe_seconds}'
        + (f' cpus={args.smp_cpus} small_cores_after=0' if args.smp_cpus>1 else '')
        + (' ustacks=SpringBoard ustacks_at=32 ustacks_ms=10000 ustacks_count=2 ustacks_threads=1 ustacks_tname=*' if args.ios_startup_stacks else '')
        + (f' ustacks=lsd ustacks_at={60 if args.ios_observe_seconds==180 else 32} ustacks_ms={60000 if args.ios_observe_seconds==180 else 10000} ustacks_count=2 ustacks_threads=96 ustacks_tname=*' if args.ios_lsd_stacks else '')
        # proc_name_address returns p_comm[MAXCOMLEN+1], with MAXCOMLEN=16.
        + (' ustacks=CollectionsPoste ustacks_at=130 ustacks_ms=20000 ustacks_count=2 ustacks_threads=96 ustacks_tname=*' if args.ios_poster_stacks else '')
        + (' ustacks=top ustacks_at=60 ustacks_ms=60000 ustacks_count=2' if args.ios_top_stacks else '')
        + (f' ustacks={args.ios_process_stacks} ustacks_at=130 ustacks_ms=25000 ustacks_count=2 ustacks_threads=96 ustacks_tname=*' if args.ios_process_stacks else '')
        + (' touchscreen=1 lmi_touch=1' if args.lmi_touch_probe else '')
        + (' touchscreen=1 lmi_touch=3' if args.lmi_touch_power_probe else '')
        + (' touchscreen=1 lmi_touch=5' if args.lmi_touch_supply_probe else '')
        + (' touchscreen=1 lmi_touch=6' if args.lmi_touch_input else '')
        + (' lmi_gpu=1' if args.lmi_gpu_readonly else '')
        + (' lmi_gpu=46' if args.lmi_gpu_unsecure else ' lmi_gpu=45' if args.lmi_gpu_zap_load else ' lmi_gpu=44' if args.lmi_gpu_zap_metadata else ' lmi_gpu=43' if args.lmi_gpu_scm_query else ' lmi_gpu=42' if args.lmi_gpu_cp_config_ready else ' lmi_gpu=41' if args.lmi_gpu_cp_config_plan else ' lmi_gpu=40' if args.lmi_gpu_fal_veto else ' lmi_gpu=39' if args.lmi_gpu_core_access else ' lmi_gpu=38' if args.lmi_gpu_cp_sp_clock else ' lmi_gpu=37' if args.lmi_gpu_cp_fence else ' lmi_gpu=36' if args.lmi_gpu_cp else ' lmi_gpu=35' if args.lmi_gpu_core_memory else ' lmi_gpu=34' if args.lmi_gpu_cp_plan else ' lmi_gpu=33' if args.lmi_gpu_gx else ' lmi_gpu=32' if args.lmi_gpu_hfi_core else ' lmi_gpu=31' if args.lmi_gpu_hfi_perf else ' lmi_gpu=30' if args.lmi_gpu_table_plan else ' lmi_gpu=29' if args.lmi_gpu_hfi_io else ' lmi_gpu=28' if args.lmi_gpu_gmu_boot else ' lmi_gpu=27' if args.lmi_gpu_gmu_route_probe else ' lmi_gpu=26' if args.lmi_gpu_gmu_200mhz_probe else ' lmi_gpu=25' if args.lmi_gpu_rsc_pdc_vote_probe else ' lmi_gpu=24' if args.lmi_gpu_pdc_enable_probe else ' lmi_gpu=23' if args.lmi_gpu_rsc_sequence_probe else ' lmi_gpu=22' if args.lmi_gpu_rsc_init else ' lmi_gpu=21' if args.lmi_gpu_rsc_state else ' lmi_gpu=20' if args.lmi_gpu_rpmh_arc_slot_probe else ' lmi_gpu=19' if args.lmi_gpu_rpmh_bus_probe else ' lmi_gpu=18' if args.lmi_gpu_rpmh_interface_probe else ' lmi_gpu=17' if args.lmi_gpu_rscc_sde_probe else ' lmi_gpu=16' if args.lmi_gpu_rpmh_probe else ' lmi_gpu=15' if args.lmi_gpu_rscc_readonly else ' lmi_gpu=14' if args.lmi_gpu_arc_inventory else ' lmi_gpu=13' if args.lmi_gpu_stage1_init else ' lmi_gpu=12' if args.lmi_gpu_wired_context else ' lmi_gpu=11' if args.lmi_gpu_cb0_table_probe else ' lmi_gpu=10' if args.lmi_gpu_cb0_context_probe else ' lmi_gpu=9' if args.lmi_gpu_cb0_format_probe else ' lmi_gpu=8' if args.lmi_gpu_cb0_readonly else ' lmi_gpu=6' if args.lmi_gpu_smmu_readonly else ' lmi_gpu=5' if args.lmi_gpu_tcm_load else ' lmi_gpu=4' if args.lmi_gpu_gmu_readonly else ' lmi_gpu=3' if args.lmi_gpu_clock_probe else ' lmi_gpu=2' if args.lmi_gpu_cx_probe else '')
        + (' lmi_gpu_tile=1' if args.lmi_gpu_tile else '')
        + (' lmi_gpu_desktop=1' if args.lmi_gpu_desktop else '')
        + (f' fb_threads={args.fb_threads}' if args.lmi_gpu_desktop else '')
        + (f' fb_queue={args.fb_queue} fb_beat={args.fb_beat}' if args.lmi_gpu_desktop else '')
        + (' lmi_gpu=7' if args.lmi_gpu_ram_plan and not args.lmi_gpu_wired_context and not args.lmi_gpu_gmu_route_probe else '')
        + '" : (checkpoint==62 ? "-v systrace=1 applog=1 loader_return_after=25" : "-v");')
    replace_once('\t\t\tparse_payload(&pi, 0);\n\t\t\tlog_len = 0;',
        '\t\t\tparse_payload(&pi, 0);\n            pi.forced_base=0;\n\t\t\tlog_len = 0;')
    replace_once('} else if (str_eq(var, "version")) {','''} else if (str_eq(var,"resident-size")) {
                uint32_t mark=log_len;
                print("%x",resident_rd_size); log_buf[log_len]=0;
                fb_reply("OKAY",log_buf+mark); log_len=mark;
            } else if (str_eq(var,"resident-crc32")) {
                if (!resident_rd_size || win_size<=RESIDENT_RD_OFFSET+RESIDENT_RD_RESERVE ||
                    resident_rd_size>win_size-RESIDENT_RD_OFFSET-RESIDENT_RD_RESERVE) {
                    fb_reply("FAIL","no bounded resident RAM image");
                } else {
                    uint32_t mark=log_len;
                    print("%x",(uint64_t)ufs_crc32((const uint8_t *)(uintptr_t)(win_base+RESIDENT_RD_OFFSET),resident_rd_size));
                    log_buf[log_len]=0; fb_reply("OKAY",log_buf+mark); log_len=mark;
                }
            } else if (str_eq(var, "version")) {''')
replace_once('fb_reply("OKAY", "xnuloader");','fb_reply("OKAY", "lmi-xnuloader-readonly");')
replace_once('if (d->pages >= 256) {','if (d->pages != 0) { /* include small descriptors in the audit */')
replace_once('} else if (str_eq(var, "version")) {','''} else if (str_eq(var,"payload-base")) {
                uint32_t mark=log_len;
                print("%x",PAYLOAD_BASE); log_buf[log_len]=0;
                fb_reply("OKAY",log_buf+mark); log_len=mark;
            } else if (str_eq(var,"platform")) {
                fb_reply("OKAY",PLAT->name);
            } else if (str_eq(var,"payload-crc32")) {
                struct payload_header *h=(struct payload_header *)(uintptr_t)PAYLOAD_BASE;
                if (h->magic!=PAYLOAD_MAGIC || h->size>PAYLOAD_MAX_SIZE-sizeof(*h)) {
                    fb_reply("FAIL","invalid payload header");
                } else {
                    uint32_t mark=log_len;
                    print("%x",(uint64_t)ufs_crc32((const uint8_t *)h,h->size+sizeof(*h)));
                    log_buf[log_len]=0; fb_reply("OKAY",log_buf+mark); log_len=mark;
                }
            } else if (str_eq(var, "version")) {''')

replace_once('static uint32_t log_len;','static uint32_t log_len;\nstatic uint64_t lmi_started;')
if 50 in checkpoints:
    # Exact early single-CPU profile: snapshot before handoff and restore before
    # the stub unmasks UEFI interrupts. Refuse distributor-mode/WAKER changes.
    fragment=(root/'tools/lmi-gic-guard.c').read_text()
    fragment=f'#define LMI_SMP_RETURN {int(args.smp_cpus>1)}\n'+fragment
    if 55 in checkpoints:
        # machine_load_context installs a different d8-d15 context. Preserve
        # the AArch64 ABI's low 64-bit nonvolatile SIMD registers for UEFI.
        replace_once('CTX_ICC_PMR, CTX_ICC_IGRPEN1, CTX_ICC_BPR1, CTX_COUNT',
            'CTX_ICC_PMR, CTX_ICC_IGRPEN1, CTX_ICC_BPR1, CTX_D8, CTX_D9, CTX_D10, CTX_D11, CTX_D12, CTX_D13, CTX_D14, CTX_D15, CTX_COUNT')
        # Assemble the explicit FP operations separately; keep the C loader
        # under -mgeneral-regs-only so no helper implicitly changes SIMD state.
        simd=[]
        for op in ('stp','ldp'):
            simd.extend(f'{op} d{n}, d{n+1}, [x10, #{368+(n-8)*8}]' for n in range(8,16,2))
        (out/'simd-reference.S').write_text('.text\n'+ '\n'.join(simd)+'\n')
        subprocess.run(['clang','--target=aarch64-none-elf','-c',str(out/'simd-reference.S'),'-o',str(out/'simd-reference.o')],check=True)
        subprocess.run(['llvm-objcopy','-O','binary',str(out/'simd-reference.o'),str(out/'simd-reference.bin')],check=True)
        simd_words=struct.unpack('<8I',(out/'simd-reference.bin').read_bytes())
        (out/'simd-reference-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-d',str(out/'simd-reference.o')]))
        fragment=fragment.replace('    lmi_gic.armed=0;',
            '    lmi_gic.armed=0;\n    if (!(READ_SYSREG(CPACR_EL1)&0x100000ULL)) { print("lmi: FP access disabled; refusing SIMD context save\\n"); return 0; }')
        needle='        "  mrs x9, icc_bpr1_el1\\n    str x9, [x10, #360]\\n"'
        replace_once(needle,needle+'\n'+''.join(f'        "  .inst {word:#x}\\n" /* {op} */\n' for word,op in zip(simd_words[:4],simd[:4])))
        needle='        "  ldr x9, [x10, #336]\\n msr s3_3_c4_c4_1, x9\\n"'
        replace_once(needle,needle+'\n'+''.join(f'        "  .inst {word:#x}\\n" /* {op} */\n' for word,op in zip(simd_words[4:],simd[4:])))
    if 57 in checkpoints:
        # An actual EL1 interrupt can install a different SP_EL1 even when
        # resident UEFI uses SP_EL0 for ordinary calls. Preserve that bank too.
        replace_once('CTX_D15, CTX_COUNT','CTX_D15, CTX_SP_EL1, CTX_COUNT')
        needle='        "  str x18, [x10, #112]\\n"'
        replace_once(needle,
            '        "  mrs x9, spsel\\n"\n'
            '        "  cbnz x9, 4f\\n"\n'
            '        "  mrs x11, daif\\n"\n'
            '        "  msr daifset, #15\\n"\n'
            '        "  msr spsel, #1\\n"\n'
            '        "  mov x9, sp\\n"\n'
            '        "  str x9, [x10, #432]\\n"\n'
            '        "  msr spsel, #0\\n"\n'
            '        "  msr daif, x11\\n"\n'
            '        "4:\\n"\n'+needle)
        replace_once('        "1:\\n"\n        "  msr spsel, #0\\n"\n        "2:\\n"',
            '        "1:\\n"\n        "  msr spsel, #1\\n"\n'
            '        "  ldr x9, [x10, #432]\\n"\n        "  mov sp, x9\\n"\n'
            '        "  msr spsel, #0\\n"\n        "2:\\n"')
    replace_once('int loader_save_ctx(void);',fragment+'\nint loader_save_ctx(void);')
    replace_once('\tif (loader_save_ctx() == 0) {',
                 '\tif (!lmi_gic_capture(checkpoint)) return 0;\n\tif (loader_save_ctx() == 0) {'+('''
        if (checkpoint==63) {
            print("lmi stub trace: stub=%x ctx=%x SP=%x SP_EL0=%x SP_EL1=%x TTBR0=%x\\n",
                (uint64_t)(uintptr_t)loader_return_stub,(uint64_t)(uintptr_t)loader_ctx,
                loader_ctx[CTX_SP],loader_ctx[CTX_SP_EL0],loader_ctx[CTX_SP_EL1],loader_ctx[CTX_TTBR0]);
            print("lmi stub marks: bottom-right16px red=MMUoff green=context blue=UEFI-MMUon\\n");
            for (unsigned y=2304;y<2392;y++) {
                uintptr_t p=0x9c000000ULL+(y*1080+800)*4;
                for (unsigned x=0;x<280;x++) ((volatile uint32_t *)p)[x]=0;
                for (uintptr_t q=p&~63ULL;q<p+1120;q+=64) __asm__ volatile("dc cvac, %0"::"r"(q));
            }
            __asm__ volatile("dsb sy");
        }
''' if args.trace_return_stub else ''))
    replace_once('\t\t\tjump_to_kernel(entry_va + slide, ba_pa);',
        '\t\t\tif (!lmi_gic_isolate()) { write_logs(NULL,0); return 0; }\n\t\t\tjump_to_kernel(entry_va + slide, ba_pa);')
    needle='        "  ldr x9, [x10, #64]\\n  msr daif, x9\\n"'
    replace_once(needle,
        '        "  stp x10, x30, [sp, #-16]!\\n"\n'
        +(mark_before_gic if args.trace_return_stub else '')+
        '        "  bl lmi_gic_restore\\n"\n'
        '        "  ldp x10, x30, [sp], #16\\n"\n'
        +(mark_after_gic if args.trace_return_stub else '')+
        '        "  cbz x0, 3f\\n"\n'+needle+'\n'+(mark_after_daif if args.trace_return_stub else '')+'        "3:\\n"')
    replace_once('\t/* --- the kernel came back ------------------------------------------- */',
        ('\tif (checkpoint==63) lmi_return_mark(8,0x000000ff); /* returned to loader C */\n' if args.trace_return_stub else '')+
        '\tif (lmi_gic.armed) {\n'
        '\t\tprint("lmi GIC return: restored=%d matches=%d\\n",(uint64_t)lmi_gic.restored,(uint64_t)lmi_gic.matches);\n'
        '\t\tprint("lmi GIC observed: group=%x enabled=%x priority=%x\\n",(uint64_t)lmi_gic.seen_group,(uint64_t)lmi_gic.seen_enabled,(uint64_t)lmi_gic.seen_priority);\n'
        '\t\tif (lmi_gic.isolated) print("lmi IRQ return: isolated=%d matches=%d\\n",(uint64_t)lmi_gic.isolation_ok,(uint64_t)lmi_gic.matches);\n'
        '\t\tif (!lmi_gic.matches) { print("lmi GIC mismatch: rebooting\\n"); ST->rt->reset_system(0,0,0,NULL); for (;;) {} }\n'
        '\t}\n\t/* --- the kernel came back ------------------------------------------- */')
macro='#define READ_SYSREG(name) ({ uint64_t _v; __asm__ volatile ("mrs %0, " #name : "=r" (_v)); _v; })'
replace_once(macro,macro+'''
static void lmi_deadline(void) {
    if (lmi_started && READ_SYSREG(CNTVCT_EL0)-lmi_started >= 90*READ_SYSREG(CNTFRQ_EL0)) {
        ST->rt->reset_system(0,0,0,NULL);
        for (;;) {}
    }
}
''')
if args.trace_return_stub:
    # place before its callers, after macro-dependent generation is complete
    anchor='static void lmi_deadline(void) {'
    assert s.count(anchor)==1
    s=s.replace(anchor,mark_function+'\n'+anchor,1)
    # Checkpoint63-only C breadcrumbs: leave the normal return behavior intact.
    # Each rectangle survives even if a later firmware/USB call never returns.
    for anchor,stage,color in [
        ('\t/* --- the kernel came back ------------------------------------------- */',9,0x0000ffff),
        ('\tif (hc_known) {\n\t\tflush_dcache',10,0x00ff00ff),
        ('\trecording_data = NULL;\n\trecording_len = 0;',11,0x00ffff00),
        ('\tconst char *klog = (const char *)loader_ctx[CTX_LOG_PA];',12,0x00ff0000),
        ('\twrite_logs(klog, klog_len);',13,0x0000ff00),
    ]:
        replace_once(anchor,f'\tif (checkpoint==63) lmi_return_mark({stage},{color:#x});\n'+anchor)
    replace_once('\twrite_logs(klog, klog_len);\n\treturn 1;',
        '\twrite_logs(klog, klog_len);\n\tif (checkpoint==63) lmi_return_mark(14,0x000000ff);\n\treturn 1;')
    replace_once('\t\t\tif (!run_kernel(have_cp, cp)) {',
        '\t\t\tint started=run_kernel(have_cp,cp);\n'
        '\t\t\tif (cp==63) { lmi_usb_seen=0; lmi_usb_trace=1; lmi_usb_mark(15,0x0000ffff); }\n'
        '\t\t\tif (!started) {')
    replace_once('\t\tfb_command(cmd);\n\t}\n}',
        '\t\tlmi_usb_mark(21,0x00ffff00);\n\t\tfb_command(cmd);\n\t\tlmi_usb_mark(25,0x00ff00ff);\n\t}\n}')
    replace_once('\t\tif (!usb_connected) {\n\t\t\tusb_wait(0xff);',
        '\t\tlmi_usb_mark(26,usb_connected?0x0000ff00:0x00ff0000);\n\t\tif (!usb_connected) {\n\t\t\tusb_wait(0xff);')
    replace_once('} else if (EFI_ERROR(USB->send(USB_EP_OUT, len, buf))) {\n\t\treturn -1;\n\t}\n\treturn usb_wait(USB_EP_OUT);',
        '} else {\n\t\tlmi_usb_mark(16,0x00ff0000);\n'
        '\t\tefi_status status=USB->send(USB_EP_OUT,len,buf);\n'
        '\t\tlmi_usb_mark(17,EFI_ERROR(status)?0x00ff0000:0x0000ff00);\n\t\tif (EFI_ERROR(status)) return -1;\n\t}\n'
        '\tint64_t received=usb_wait(USB_EP_OUT);\n\tlmi_usb_mark(20,0x00ff00ff);\n\treturn received;')
    # The same handle_event spelling also occurs in usb_poll_command. Change
    # only usb_wait, preserving the firmware call and transfer semantics.
    start=s.index('usb_wait(uint8_t endpoint)\n{');end=s.index('\nstatic int usb_rx_queued;',start)
    wait=s[start:end];needle='\t\tUSB->handle_event(&msg, &size, &data);'
    assert wait.count(needle)==1
    wait=wait.replace(needle,'\t\tlmi_usb_mark(18,0x000000ff);\n'+needle+'\n\t\tlmi_usb_mark(19,0x0000ffff);')
    s=s[:start]+wait+s[end:]
    replace_once('\tif (EFI_ERROR(USB->send(USB_EP_IN, len, usb_tx_buf))) {\n\t\treturn -1;\n\t}\n\treturn usb_wait(USB_EP_IN);',
        '\tlmi_usb_mark(22,0x00ff0000);\n\tefi_status status=USB->send(USB_EP_IN,len,usb_tx_buf);\n'
        '\tlmi_usb_mark(23,EFI_ERROR(status)?0x00ff0000:0x0000ff00);\n\tif (EFI_ERROR(status)) return -1;\n'
        '\tint64_t sent=usb_wait(USB_EP_IN);\n\tlmi_usb_mark(24,0x000000ff);\n\treturn sent;')
if 62 in checkpoints:
    s=s.replace('>= 90*READ_SYSREG(CNTFRQ_EL0)','>= 600*READ_SYSREG(CNTFRQ_EL0)')
replace_once('wdt_pet(void)\n{','wdt_pet(void)\n{\n\tlmi_deadline();')
replace_once('usb_command_loop(void)\n{','usb_command_loop(void)\n{\n\tlmi_deadline();')
replace_once('\twdt_arm();','\twdt_armed=0; /* unreviewed redwood hypervisor SMCs are not used */')
start=s.index('\tint have_payload = parse_payload(&pi, 0);',s.index('efi_main('))
end=s.index('\treboot();',start)
s=s[:start]+'''
    lmi_started=READ_SYSREG(CNTVCT_EL0);
    if (PLAT!=&platform_lmi) {
        print("lmi: unexpected GOP/platform; refusing RAM allocation\\n");
        reboot(); return EFI_ERROR_BIT|3;
    }
    uint64_t payload=0;
    efi_status status=BS->allocate_pages(AllocateAnyPages,EfiLoaderData,PAYLOAD_MAX_SIZE>>12,&payload);
    print("lmi payload allocation status=%x base=%x size=%x\\n",status,payload,PAYLOAD_MAX_SIZE);
    if (EFI_ERROR(status)) { reboot(); return status; }
    lmi_payload_base=payload;
    struct payload_header *header=(struct payload_header *)(uintptr_t)payload;
    header->magic=PAYLOAD_MAGIC; header->size=0;
    print("lmi bring-up: storage writes and kernel execution disabled\\n");
    print_memory_map();
    if (usb_start()) { flush_log(); usb_command_loop(); }
'''+s[end:]
if args.checkpoints:
    replace_once('lmi bring-up: storage writes and kernel execution disabled',
                 'lmi bring-up: storage writes disabled; selftest/checkpoints '+','.join(map(str,checkpoints))+' only')
replace_once('\tstruct payload_info pi;\n\n\tST = st;','\n\tST = st;')

gpu_modes=re.findall(r'\blmi_gpu=(\d+)\b',s)
assert len(gpu_modes)<=1, 'Conflicting GPU boot modes in generated loader'
if args.lmi_gpu_gmu_route_probe:assert gpu_modes==(['46'] if args.lmi_gpu_unsecure else ['45'] if args.lmi_gpu_zap_load else ['44'] if args.lmi_gpu_zap_metadata else ['43'] if args.lmi_gpu_scm_query else ['42'] if args.lmi_gpu_cp_config_ready else ['41'] if args.lmi_gpu_cp_config_plan else ['40'] if args.lmi_gpu_fal_veto else ['39'] if args.lmi_gpu_core_access else ['38'] if args.lmi_gpu_cp_sp_clock else ['37'] if args.lmi_gpu_cp_fence else ['36'] if args.lmi_gpu_cp else ['35'] if args.lmi_gpu_core_memory else ['34'] if args.lmi_gpu_cp_plan else ['33'] if args.lmi_gpu_gx else ['32'] if args.lmi_gpu_hfi_core else ['31'] if args.lmi_gpu_hfi_perf else ['30'] if args.lmi_gpu_table_plan else ['29'] if args.lmi_gpu_hfi_io else ['28'] if args.lmi_gpu_gmu_boot else ['27'])
(out/'loader.c').write_text(s)
for name in ('efi.h','identity.h'):shutil.copy2(up/name,out/name)
(out/'lmi-loader.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile='a/xnuloader/loader.c',tofile='b/xnuloader/loader.c')))
flags=['--target=aarch64-unknown-windows','-ffreestanding','-fno-builtin','-fno-stack-protector','-fshort-wchar','-mgeneral-regs-only','-O1','-Wall','-Wextra','-Wno-unused-parameter','-Wno-unused-function']
subprocess.run(['clang',*flags,'-c',str(out/'loader.c'),'-o',str(out/'loader.obj')],check=True)
subprocess.run(['lld-link','/subsystem:efi_application','/entry:efi_main','/nodefaultlib','/base:0xA1000000',f'/out:{out}/loader.efi',str(out/'loader.obj')],check=True)
(out/'loader-disassembly.txt').write_bytes(subprocess.check_output(['llvm-objdump','-dr',str(out/'loader.obj')]))
b=(out/'loader.efi').read_bytes();pe=struct.unpack_from('<I',b,60)[0]
assert b[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',b,pe+4)[0]==0xaa64
header='/* Generated lmi full-loader bring-up application */\nSTATIC CONST UINT8 mLmiUsbProbe[] = {\n'
for i in range(0,len(b),24):header+=','.join(f'0x{x:02x}' for x in b[i:i+24])+',\n'
(out/'LmiUsbProbe.h').write_text(header+'};\n')
wrapper=(root/'out/lmi-usb-probe/XnuLoader-lmi-usb-probe.c').read_text()
wrapper=wrapper.replace('Starting RAM-only USB probe; 90-second timeout.','Starting lmi loader USB bring-up; 90-second timeout.')
if 62 in checkpoints:wrapper=wrapper.replace('90-second timeout.','600-second timeout for RAM image staging.')
(out/'XnuLoader-lmi-usb-probe.c').write_text(wrapper)
report=dict(application='loader.efi',bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),platform='lmi',payload_allocation='UEFI AllocateAnyPages, EfiLoaderData, 64 MiB',persistent_storage_writes=False,kernel_execution_enabled=False,hardware_tested=False)
report['kernel_execution_enabled']=args.checkpoints
report['permitted_checkpoints']=permitted
report['kernel_memory_floor']=hex(kernel_floor)
report['gic_return_guard']=dict(enabled=50 in checkpoints,scope='Single CPU, exact reviewed GIC/VM/bootstrap and IRQ/driver checkpoints. PPI 27 configuration and resident IRQ enable masks restored before UEFI interrupts are unmasked; no general boot')
report['simd_nonvolatile_saved']=55 in checkpoints
report['irq_isolation_checkpoints']=[n for n in checkpoints if n in (57,58,59,60,61,62,63)]
report['banked_sp_el1_saved']=57 in checkpoints
report['resident_ram_image_enabled']=62 in checkpoints
report['usb_session_seconds']=600 if 62 in checkpoints else 90
if 63 in checkpoints:report['ios_observe_seconds']=args.ios_observe_seconds
report['ios_startup_stacks']=dict(enabled=args.ios_startup_stacks,process='SpringBoard',at_seconds=32,interval_ms=10000,count=2,threads=1,loader_log=True)
report['ios_poster_stacks']=dict(enabled=args.ios_poster_stacks,process='CollectionsPoste',bundle_executable='CollectionsPoster',at_seconds=130,interval_ms=20000,count=2,threads=96,loader_log=True)
report['lmi_touch_probe']=args.lmi_touch_probe
report['lmi_touch_power_probe']=args.lmi_touch_power_probe
report['lmi_touch_supply_probe']=args.lmi_touch_supply_probe
report['lmi_touch_input']=args.lmi_touch_input
report['lmi_gpu_readonly']=args.lmi_gpu_readonly
report['lmi_gpu_cx_probe']=args.lmi_gpu_cx_probe
report['lmi_gpu_clock_probe']=args.lmi_gpu_clock_probe
report['lmi_gpu_gmu_readonly']=args.lmi_gpu_gmu_readonly
report['lmi_gpu_tcm_load']=args.lmi_gpu_tcm_load
report['lmi_gpu_smmu_readonly']=args.lmi_gpu_smmu_readonly
report['lmi_gpu_ram_plan']=args.lmi_gpu_ram_plan
report['lmi_gpu_wired_context']=args.lmi_gpu_wired_context
report['lmi_gpu_stage1_init']=args.lmi_gpu_stage1_init
report['lmi_gpu_arc_inventory']=args.lmi_gpu_arc_inventory
report['lmi_gpu_rsc_sequence_probe']=args.lmi_gpu_rsc_sequence_probe
report['lmi_gpu_pdc_enable_probe']=args.lmi_gpu_pdc_enable_probe
report['lmi_gpu_rsc_pdc_vote_probe']=args.lmi_gpu_rsc_pdc_vote_probe
report['lmi_gpu_gmu_200mhz_probe']=args.lmi_gpu_gmu_200mhz_probe
report['lmi_gpu_unsecure']=args.lmi_gpu_unsecure
report['lmi_gpu_tile']=args.lmi_gpu_tile
report['lmi_gpu_desktop']=args.lmi_gpu_desktop
report['lmi_gpu_zap_load']=args.lmi_gpu_zap_load
report['lmi_gpu_zap_metadata']=args.lmi_gpu_zap_metadata
report['lmi_gpu_scm_query']=args.lmi_gpu_scm_query
report['lmi_gpu_cp_config_ready']=args.lmi_gpu_cp_config_ready
report['lmi_gpu_cp_config_plan']=args.lmi_gpu_cp_config_plan
report['lmi_gpu_fal_veto']=args.lmi_gpu_fal_veto
report['lmi_gpu_core_access']=args.lmi_gpu_core_access
report['lmi_gpu_cp_sp_clock']=args.lmi_gpu_cp_sp_clock
report['lmi_gpu_cp_fence']=args.lmi_gpu_cp_fence
report['lmi_gpu_cp']=args.lmi_gpu_cp
report['lmi_gpu_core_memory']=args.lmi_gpu_core_memory
report['lmi_gpu_cp_plan']=args.lmi_gpu_cp_plan
report['lmi_gpu_gx']=args.lmi_gpu_gx
report['lmi_gpu_hfi_core']=args.lmi_gpu_hfi_core
report['lmi_gpu_hfi_perf']=args.lmi_gpu_hfi_perf
report['lmi_gpu_table_plan']=args.lmi_gpu_table_plan
report['lmi_gpu_hfi_io']=args.lmi_gpu_hfi_io
report['lmi_gpu_gmu_boot']=args.lmi_gpu_gmu_boot
report['lmi_gpu_gmu_route_probe']=args.lmi_gpu_gmu_route_probe
report['lmi_gpu_rsc_init']=args.lmi_gpu_rsc_init
report['lmi_gpu_rsc_state']=args.lmi_gpu_rsc_state
report['lmi_gpu_rscc_readonly']=args.lmi_gpu_rscc_readonly
report['lmi_gpu_rpmh_probe']=args.lmi_gpu_rpmh_probe
report['lmi_gpu_rscc_sde_probe']=args.lmi_gpu_rscc_sde_probe
report['lmi_gpu_rpmh_arc_slot_probe']=args.lmi_gpu_rpmh_arc_slot_probe
report['lmi_gpu_rpmh_bus_probe']=args.lmi_gpu_rpmh_bus_probe
report['lmi_gpu_rpmh_interface_probe']=args.lmi_gpu_rpmh_interface_probe
report['lmi_gpu_ram_hfi']=args.lmi_gpu_ram_hfi
report['lmi_gpu_cb0_readonly']=args.lmi_gpu_cb0_readonly
report['lmi_gpu_cb0_format_probe']=args.lmi_gpu_cb0_format_probe
report['lmi_gpu_cb0_context_probe']=args.lmi_gpu_cb0_context_probe
report['lmi_gpu_cb0_table_probe']=args.lmi_gpu_cb0_table_probe
report['ios_lsd_stacks']=dict(enabled=args.ios_lsd_stacks,process='lsd',at_seconds=60 if args.ios_observe_seconds==180 else 32,interval_ms=60000 if args.ios_observe_seconds==180 else 10000,count=2,threads=96,loader_log=True)
report['ios_top_stacks']=dict(enabled=args.ios_top_stacks,at_seconds=60,interval_ms=60000,count=2,loader_log=True)
report['ios_process_stacks']=dict(enabled=bool(args.ios_process_stacks),process=args.ios_process_stacks,at_seconds=130,interval_ms=25000,count=2,threads=96,loader_log=True)
report['desktop_framebuffer_threads']=args.fb_threads if args.lmi_gpu_desktop else None
report['smp_cpus']=args.smp_cpus
report['fb_threads']=args.fb_threads
report['fb_queue']=args.fb_queue
report['fb_beat']=args.fb_beat
report['display_census']=args.display_census
if args.display_census:
    report['display_census_source_sha256']=hashlib.sha256((root/'tools/lmi-display-census.c').read_bytes()).hexdigest()
report['smp_gic_sgis_restored']=args.smp_cpus>1
report['physical_return_stub_trace']=dict(enabled=args.trace_return_stub,gop_pa='0x9c000000',pitch_bytes=4320,clear_rectangle=[960,2304,120,88],stages=[dict(index=i,color=c,event=e,rectangle=[960+32*(i%4),2304+24*(i//4),16,16]) for i,c,e in [(0,'red','MMU off'),(1,'green','context loaded before MMU on'),(2,'blue','UEFI MMU on'),(3,'cyan','context restore complete before GIC'),(4,'magenta','GIC restore returned'),(5,'yellow','original DAIF restored before stub ret'),(8,'blue','loader C resumed after stub ret'),(9,'cyan','GIC report complete; native kernel came back block'),(10,'magenta','hc_take_back returned'),(11,'yellow','other CPU queries complete'),(12,'red','recording and sound inspection complete'),(13,'green','before write_logs and compose_logs'),(14,'blue','write_logs returned before run_kernel return')]])
report['physical_return_stub_trace']['clear_rectangle']=[800,2304,280,88]
usb_stages=[(15,'cyan','run_kernel returned to fb_command'),(16,'red','before OUT send'),(17,'green','OUT send returned'),(18,'blue','before handle_event'),(19,'cyan','handle_event returned'),(20,'magenta','usb_rx returned'),(21,'yellow','before command dispatch'),(22,'red','before IN send'),(23,'green','IN send returned'),(24,'blue','IN wait returned'),(25,'magenta','fb_command returned to USB loop'),(26,'green/red','loop entry: connected/disconnected')]
report['physical_return_stub_trace']['stages'] += [dict(index=i,color=c,event=e,rectangle=[(960 if i<16 else 800)+32*((i if i<16 else i-16)%4),2304+24*((i if i<16 else i-16)//4),16,16]) for i,c,e in usb_stages]
for stage in report['physical_return_stub_trace']['stages']:
    if stage['index'] in (17,23):
        stage.update(color='green/red',event=stage['event']+' (success/error)')
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
