"""Temporary boot: return self-test and explicitly reviewed checkpoints. No flashing."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, shutil, struct, subprocess, time, traceback, zlib
from lmi_checkpoint_policy import STAGE_CHOICES,checkpoints_through

parser=argparse.ArgumentParser()
parser.add_argument('--max-checkpoint',type=int,choices=STAGE_CHOICES,default=1)
parser.add_argument('--early-return-fix',action='store_true',help='Use the explicitly patched single-CPU diagnostic kernel')
parser.add_argument('--return-guard',action='store_true',help='Use the initialization-aware PE boot-arg guard')
parser.add_argument('--console-probe',action='store_true',help='Print a diagnostic marker using XNU console APIs at checkpoint 20')
parser.add_argument('--preirq-probe',action='store_true',help='Use the pinned kernel with the checkpoint before GIC initialization')
parser.add_argument('--bootstrap-probe',action='store_true',help='Use the pinned kernel with bounded VM/OSLOG bootstrap instrumentation')
parser.add_argument('--irq-probe',action='store_true',help='Use the pinned kernel with bounded native IRQ instrumentation')
parser.add_argument('--driver-probe',action='store_true',help='Use the pinned kernel stopping before BSD init after IOKit matching')
parser.add_argument('--bsd-probe',action='store_true',help='Use the pinned kernel stopping after BSD setup before root selection')
parser.add_argument('--root-probe',action='store_true',help='Use the pinned kernel stopping after native RAM-root mount')
parser.add_argument('--user-probe',action='store_true',help='Verify PID1 SYS_exit with actual saved EL0 registers')
parser.add_argument('--ios-probe',action='store_true',help='Stage verified iOS RAM images and observe original launchd.ios in EL0')
parser.add_argument('--ios-continue',action='store_true',help='Checkpoint63: continue launchd and collect the bounded RAM-only return')
parser.add_argument('--source-runtime',action='store_true',help='Use the separately audited v36 source reconstruction with the frozen lmi runtime')
parser.add_argument('--display-v40',action='store_true',help='Use the separately pinned v40 read-only DPU observer and relocated runtime')
parser.add_argument('--display-v41',action='store_true',help='Use the separately pinned v41 raw-return-log DPU observer')
parser.add_argument('--display-v42',action='store_true',help='Use the separately pinned v42 synchronized CPU presentation prototype')
parser.add_argument('--display-v43',action='store_true',help='Read-only QSEED/MDSS SMMU inventory before owned-buffer DMA')
parser.add_argument('--display-v44',action='store_true',help='Automatic spatial pattern verification of owned DMA, QSEED and A/B flips')
parser.add_argument('--display-v45',action='store_true',help='Owned DMA/scaler probe with exact preparation refusal evidence')
parser.add_argument('--display-v46',action='store_true',help='Owned DMA/scaler probe with bypass SEP tolerance and stable first-frame baseline')
parser.add_argument('--display-v47',action='store_true',help='Same-run spatial verification and conditional hardware-scaled double-buffer desktop')
parser.add_argument('--display-v48',action='store_true',help='Wait for graphics before probing and retain final refusal diagnostics')
parser.add_argument('--display-v49',action='store_true',help='ASIDPNE=0 with exact SCTLR readback for display mappings')
parser.add_argument('--display-v50',action='store_true',help='QSEED4 preload/blend correction and retained spatial trace')
parser.add_argument('--display-v51',action='store_true',help='Measured blend bit31=0 with exact QSEED4 readback')
parser.add_argument('--display-v52',action='store_true',help='Exact measured global SMMU profiles with stable preparation')
parser.add_argument('--display-v53',action='store_true',help='Batched scaler diagnostics; never enables new desktop')
parser.add_argument('--display-v54',action='store_true',help='Bypass vs identity vs scaled diagnostics; no new desktop')
parser.add_argument('--display-v59',action='store_true',help='One-copy complete BGRA frames with native queue/record and unchanged DPU mappings')
parser.add_argument('--display-v58',action='store_true',help='One outstanding asynchronous GPU submission with guarded cache/mapping/exit drains')
parser.add_argument('--display-v57',action='store_true',help='Stock speed-bin index7 GPU frequency request with v56 display')
parser.add_argument('--display-v56',action='store_true',help='CPU cache and frame preservation performance experiment')
parser.add_argument('--display-v55',action='store_true',help='Explicit color-normalized hardware desktop experiment')
parser.add_argument('--prepare-only',action='store_true',help='Freeze and verify all test inputs, then exit before any device access')
parser.add_argument('--ios-images',type=Path,default=Path('out/lmi-ios-images'))
parser.add_argument('--root-image',type=Path,help='Small APFS RAM-root image for the root probe')
parser.add_argument('--ios-boot-image',type=Path,help='Audited GPU GLES RAM image manifest (checkpoint63 md1 only)')
parser.add_argument('--evidence-suffix',default='',help='Unique suffix to preserve earlier hardware evidence')
parser.add_argument('--ios-result-delay-seconds',type=int,choices=(0,30,50,185),default=None,help='Checkpoint63 query delay: native duration plus5s; explicit0 retains the early-query control')
args=parser.parse_args()
assert not args.display_v59 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v58 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v57 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v56 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v55 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v54 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v53 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert sum(bool(getattr(args,'display_v'+str(v))) for v in range(40,60))<=1
assert not args.display_v52 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.source_runtime or (args.ios_continue and args.max_checkpoint==63)
assert not args.display_v40 or (not args.source_runtime and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v41 or (not args.source_runtime and not args.display_v40 and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v42 or (not args.source_runtime and not args.display_v40 and not args.display_v41 and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v43 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v44 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42,args.display_v43)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v45 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42,args.display_v43,args.display_v44)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v46 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42,args.display_v43,args.display_v44,args.display_v45)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v47 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42,args.display_v43,args.display_v44,args.display_v45,args.display_v46)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v48 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42,args.display_v43,args.display_v44,args.display_v45,args.display_v46,args.display_v47)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v49 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42,args.display_v43,args.display_v44,args.display_v45,args.display_v46,args.display_v47,args.display_v48)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v50 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42,args.display_v43,args.display_v44,args.display_v45,args.display_v46,args.display_v47,args.display_v48,args.display_v49)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.display_v51 or (not any((args.source_runtime,args.display_v40,args.display_v41,args.display_v42,args.display_v43,args.display_v44,args.display_v45,args.display_v46,args.display_v47,args.display_v48,args.display_v49,args.display_v50)) and args.ios_continue and args.max_checkpoint==63 and args.ios_boot_image and args.evidence_suffix)
assert not args.ios_boot_image or (args.ios_continue and args.max_checkpoint == 63)
assert not args.ios_result_delay_seconds or args.ios_continue
assert not args.evidence_suffix or re.fullmatch(r'[a-zA-Z0-9-]+',args.evidence_suffix)
assert not args.early_return_fix or args.max_checkpoint==10
assert not (args.return_guard and args.early_return_fix)
assert args.max_checkpoint<=10 or args.return_guard
assert not args.console_probe or (args.return_guard and args.max_checkpoint==20)
assert not args.preirq_probe or (args.return_guard and args.max_checkpoint in (50,21))
assert args.max_checkpoint not in (50,21) or args.preirq_probe
assert not args.bootstrap_probe or (args.return_guard and not args.preirq_probe and args.max_checkpoint in (52,53,54,55,56))
assert args.max_checkpoint not in (52,53,54,55,56) or args.bootstrap_probe
assert not args.irq_probe or (args.return_guard and not args.bootstrap_probe and not args.preirq_probe and args.max_checkpoint==57)
assert args.max_checkpoint!=57 or args.irq_probe
assert not args.driver_probe or (args.return_guard and not any((args.bootstrap_probe,args.preirq_probe,args.irq_probe,args.console_probe)) and args.max_checkpoint==58)
assert args.max_checkpoint!=58 or args.driver_probe
assert not args.bsd_probe or (args.return_guard and not any((args.bootstrap_probe,args.preirq_probe,args.irq_probe,args.console_probe,args.driver_probe)) and args.max_checkpoint==59)
assert args.max_checkpoint!=59 or args.bsd_probe
assert not args.root_probe or (args.return_guard and not any((args.bootstrap_probe,args.preirq_probe,args.irq_probe,args.console_probe,args.driver_probe,args.bsd_probe)) and args.max_checkpoint==60 and args.root_image)
assert args.max_checkpoint!=60 or args.root_probe
assert not args.user_probe or (args.return_guard and not any((args.bootstrap_probe,args.preirq_probe,args.irq_probe,args.console_probe,args.driver_probe,args.bsd_probe,args.root_probe)) and args.max_checkpoint==61 and args.root_image)
assert args.max_checkpoint!=61 or args.user_probe
assert not args.ios_continue or (args.ios_probe and args.max_checkpoint==63)
assert not args.ios_probe or (args.return_guard and not any((args.bootstrap_probe,args.preirq_probe,args.irq_probe,args.console_probe,args.driver_probe,args.bsd_probe,args.root_probe,args.user_probe)) and args.max_checkpoint in (62,63) and args.root_image)
assert args.max_checkpoint not in (62,63) or args.ios_probe
assert args.max_checkpoint!=63 or args.ios_continue
assert not args.root_image or args.root_probe or args.user_probe or args.ios_probe
checkpoints=checkpoints_through(args.max_checkpoint)

root=Path(__file__).resolve().parents[1]
out=root/('out/lmi-checkpoint-test' if args.max_checkpoint==1 else f'out/lmi-checkpoint-{args.max_checkpoint}-test')
if args.early_return_fix:out=root/'out/lmi-checkpoint-10-return-fix-test'
if args.return_guard:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-return-guard-test'
if args.console_probe:out=root/'out/lmi-checkpoint-20-console-probe-test'
if args.preirq_probe:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-preirq-probe-test'
if args.bootstrap_probe:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-bootstrap-probe-test'
if args.irq_probe:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-irq-probe-test'
if args.driver_probe:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-driver-probe-test'
if args.bsd_probe:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-bsd-probe-test'
if args.root_probe:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-root-probe-test'
if args.user_probe:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-user-probe-test'
if args.ios_probe:out=root/f'out/lmi-checkpoint-{args.max_checkpoint}-ios-probe-test'
if args.evidence_suffix:out=out.with_name(out.name+'-'+args.evidence_suffix)
if (out/'hardware-test.json').exists():
    raise RuntimeError(f'Preserve the existing evidence before reusing {out}')
out.mkdir(exist_ok=True)
image=root/'out/lmi-loader-test/lmi-diagnostics.img'
meta=json.loads((image.parent/'manifest.json').read_text())
profile=json.loads((root/'out/lmi-loader/manifest.json').read_text())
if args.ios_result_delay_seconds is None:
    args.ios_result_delay_seconds=profile['ios_observe_seconds']+5 if args.ios_continue and profile.get('ios_observe_seconds') in (25,45,180) else 0
assert not profile['persistent_storage_writes'] and profile['permitted_checkpoints']==[999,*checkpoints]
assert int(profile.get('kernel_memory_floor','0'),16)==(0x100000000 if args.max_checkpoint>=17 else 0)
assert meta['loader_sha256']==profile['sha256'] and meta['permitted_checkpoints']==profile['permitted_checkpoints']
if args.preirq_probe or args.bootstrap_probe or args.irq_probe or args.driver_probe or args.bsd_probe or args.root_probe or args.user_probe or args.ios_probe:assert profile.get('gic_return_guard',{}).get('enabled')
if args.max_checkpoint in (55,56,57,58,59,60,61,62,63):assert profile.get('simd_nonvolatile_saved')
if args.irq_probe or args.driver_probe or args.bsd_probe or args.root_probe or args.user_probe or args.ios_probe:
    assert args.max_checkpoint in profile.get('irq_isolation_checkpoints',[])
    assert profile.get('banked_sp_el1_saved')
assert hashlib.sha256(image.read_bytes()).hexdigest()==meta['sha256']
kernel=root/'hackios/prebuilt/mach.development.bcm2837'
assert hashlib.sha256(kernel.read_bytes()).hexdigest()=='9239d4adb7a2c433d7ed5729b47b63acc5281af73d8a81640ef3c678c8afd26c'
if args.early_return_fix or args.return_guard:
    folder='lmi-kernel-return-guard' if args.return_guard else 'lmi-kernel-early-return'
    if args.console_probe:folder='lmi-kernel-console-probe'
    if args.preirq_probe:folder='lmi-kernel-preirq-probe'
    if args.bootstrap_probe:folder='lmi-kernel-bootstrap-probe'
    if args.irq_probe:folder='lmi-kernel-irq-probe'
    if args.driver_probe:folder='lmi-kernel-driver-probe'
    if args.bsd_probe:folder='lmi-kernel-bsd-probe'
    if args.root_probe:folder='lmi-kernel-root-probe'
    if args.user_probe:folder='lmi-kernel-user-probe'
    if args.ios_probe:folder='lmi-kernel-ios-probe'
    if args.ios_continue:folder='lmi-kernel-ios-continue'
    if args.source_runtime:folder='lmi-kernel-source-runtime-v36'
    kernel=root/'out'/folder/'mach.development.bcm2837'
    kernel_meta=json.loads((kernel.parent/'manifest.json').read_text())
    if args.display_v40 or args.display_v41 or args.display_v42 or args.display_v43 or args.display_v44 or args.display_v45 or args.display_v46 or args.display_v47 or args.display_v48 or args.display_v49 or args.display_v50 or args.display_v51 or args.display_v52 or args.display_v53 or args.display_v54 or args.display_v55 or args.display_v56 or args.display_v57 or args.display_v58 or args.display_v59:
        from lmi_display_v40_policy import IMAGE_SHA
        if args.display_v59:from lmi_display_v59_policy import stage
        elif args.display_v58:from lmi_display_v58_policy import stage
        elif args.display_v57:from lmi_display_v57_policy import stage
        elif args.display_v56:from lmi_display_v56_policy import stage
        elif args.display_v55:from lmi_display_v55_policy import stage
        elif args.display_v54:from lmi_display_v54_policy import stage
        elif args.display_v53:from lmi_display_v53_policy import stage
        elif args.display_v52:from lmi_display_v52_policy import stage
        elif args.display_v51:from lmi_display_v51_policy import stage
        elif args.display_v50:from lmi_display_v50_policy import stage
        elif args.display_v49:from lmi_display_v49_policy import stage
        elif args.display_v48:from lmi_display_v48_policy import stage
        elif args.display_v47:from lmi_display_v47_policy import stage
        elif args.display_v46:from lmi_display_v46_policy import stage
        elif args.display_v45:from lmi_display_v45_policy import stage
        elif args.display_v44:from lmi_display_v44_policy import stage
        elif args.display_v43:from lmi_display_v43_policy import stage
        elif args.display_v42:from lmi_display_v42_policy import stage
        elif args.display_v41:from lmi_display_v41_policy import stage
        else:from lmi_display_v40_policy import stage
        assert profile.get('lmi_gpu_desktop') and profile.get('smp_cpus')==8
        assert hashlib.sha256(args.ios_boot_image.read_bytes()).hexdigest()==IMAGE_SHA
        kernel,kernel_meta=stage(root,out)
    if args.source_runtime:
        assert profile.get('lmi_gpu_desktop') and profile.get('smp_cpus')==8
        assert kernel_meta['sha256']=='98ef20d5c5bf4a902982840ee0529f36c0594995e7d2ed6c1caed93e4798b8fc'
        rebuild=kernel_meta['source_rebuild']
        rebuild_audit=kernel.parent/'source-runtime-audit.json'
        assert hashlib.sha256(rebuild_audit.read_bytes()).hexdigest()==rebuild['audit_sha256']
        assert hashlib.sha256((root/'tools/build-lmi-source-runtime.py').read_bytes()).hexdigest()==rebuild['builder_sha256']
        rebuilt=json.loads(rebuild_audit.read_text())
        assert rebuilt['result']=='PASS' and rebuilt['candidate_sha256']==kernel_meta['sha256']
        assert rebuilt['runtime_sha256']==rebuild['baseline_runtime_sha256']
    if args.bootstrap_probe or args.irq_probe or args.driver_probe or args.bsd_probe or args.root_probe or args.user_probe or args.ios_probe:assert args.max_checkpoint in kernel_meta['instrumented_checkpoints']
    assert hashlib.sha256(kernel.read_bytes()).hexdigest()==kernel_meta['sha256']
    if args.ios_continue:assert kernel_meta['ram_only_return']
    if profile.get('lmi_gpu_readonly'):
        assert args.ios_continue and kernel_meta.get('lmi_gpu_readonly',{}).get('enabled')
        assert not kernel_meta['lmi_gpu_readonly']['mmio_writes']
    if profile.get('lmi_gpu_cx_probe'):
        assert args.ios_continue and kernel_meta.get('lmi_gpu_cx_probe',{}).get('enabled')
    assert bool(profile.get('lmi_gpu_clock_probe'))==bool(kernel_meta.get('lmi_gpu_clock_probe',{}).get('enabled')), 'GPU clock probe profile mismatch'
    assert bool(profile.get('lmi_gpu_gmu_readonly'))==bool(kernel_meta.get('lmi_gpu_gmu_readonly',{}).get('enabled')), 'GPU GMU probe profile mismatch'
    assert bool(profile.get('lmi_gpu_tcm_load'))==bool(kernel_meta.get('lmi_gpu_tcm_load',{}).get('enabled')), 'GPU TCM probe profile mismatch'
    assert bool(profile.get('lmi_gpu_smmu_readonly'))==bool(kernel_meta.get('lmi_gpu_smmu_readonly',{}).get('enabled')), 'GPU SMMU profile mismatch'
    assert bool(profile.get('lmi_gpu_wired_context'))==bool(kernel_meta.get('lmi_gpu_wired_context',{}).get('enabled')), 'GPU wired context profile mismatch'
    assert bool(profile.get('lmi_gpu_stage1_init'))==bool(kernel_meta.get('lmi_gpu_stage1_init',{}).get('enabled')), 'GPU stage1 init profile mismatch'
    assert bool(profile.get('lmi_gpu_arc_inventory'))==bool(kernel_meta.get('lmi_gpu_arc_inventory',{}).get('enabled')), 'GPU ARC inventory profile mismatch'
    assert bool(profile.get('lmi_gpu_rsc_sequence_probe'))==bool(kernel_meta.get('lmi_gpu_rsc_sequence_probe',{}).get('enabled')), 'GPU RSC SRAM probe profile mismatch'
    assert bool(profile.get('lmi_gpu_pdc_enable_probe'))==bool(kernel_meta.get('lmi_gpu_pdc_enable_probe',{}).get('enabled')), 'GPU PDC enable probe profile mismatch'
    assert bool(profile.get('lmi_gpu_rsc_pdc_vote_probe'))==bool(kernel_meta.get('lmi_gpu_rsc_pdc_vote_probe',{}).get('enabled')), 'GPU RSC/PDC vote profile mismatch'
    assert bool(profile.get('lmi_gpu_gmu_200mhz_probe'))==bool(kernel_meta.get('lmi_gpu_gmu_200mhz_probe',{}).get('enabled')), 'GPU GMU 200MHz probe profile mismatch'
    assert bool(profile.get('lmi_gpu_gmu_route_probe'))==bool(kernel_meta.get('lmi_gpu_gmu_route_probe',{}).get('enabled')), 'GPU GMU route profile mismatch'
    assert bool(profile.get('lmi_gpu_unsecure'))==bool(kernel_meta.get('lmi_gpu_unsecure',{}).get('enabled')), 'GPU normal-mode profile mismatch'
    assert bool(profile.get('lmi_gpu_tile'))==bool(kernel_meta.get('lmi_gpu_tile',{}).get('enabled')), 'GPU tile profile mismatch'
    assert re.findall(rb'\blmi_gpu_tile=(\d+)\b',(root/'out/lmi-loader/loader.efi').read_bytes())==([b'1'] if profile.get('lmi_gpu_tile') else []), 'GPU tile bootarg mismatch'
    assert not profile.get('lmi_gpu_tile') or profile.get('lmi_gpu_unsecure'), 'GPU tile requires normal mode'
    assert bool(profile.get('lmi_gpu_desktop'))==bool(kernel_meta.get('lmi_gpu_desktop',{}).get('enabled')), 'GPU desktop profile mismatch'
    assert re.findall(rb'\blmi_gpu_desktop=(\d+)\b',(root/'out/lmi-loader/loader.efi').read_bytes())==([b'1'] if profile.get('lmi_gpu_desktop') else []), 'GPU desktop bootarg mismatch'
    assert not profile.get('lmi_gpu_desktop') or profile.get('lmi_gpu_tile'), 'GPU desktop requires tile'
    assert bool(profile.get('lmi_gpu_zap_load'))==bool(kernel_meta.get('lmi_gpu_zap_load',{}).get('enabled')), 'GPU ZAP load profile mismatch'
    assert bool(profile.get('lmi_gpu_zap_metadata'))==bool(kernel_meta.get('lmi_gpu_zap_metadata',{}).get('enabled')), 'GPU ZAP metadata profile mismatch'
    assert bool(profile.get('lmi_gpu_scm_query'))==bool(kernel_meta.get('lmi_gpu_scm_query',{}).get('enabled')), 'GPU SCM query profile mismatch'
    assert bool(profile.get('lmi_gpu_cp_config_ready'))==bool(kernel_meta.get('lmi_gpu_cp_config_ready',{}).get('enabled')), 'GPU CP config ready mismatch'
    assert bool(profile.get('lmi_gpu_cp_config_plan'))==bool(kernel_meta.get('lmi_gpu_cp_config_plan',{}).get('enabled')), 'GPU CP config plan mismatch'
    assert bool(profile.get('lmi_gpu_fal_veto'))==bool(kernel_meta.get('lmi_gpu_fal_veto',{}).get('enabled')), 'GPU FAL veto mismatch'
    assert bool(profile.get('lmi_gpu_core_access'))==bool(kernel_meta.get('lmi_gpu_core_access',{}).get('enabled')), 'GPU core access mismatch'
    assert bool(profile.get('lmi_gpu_cp_sp_clock'))==bool(kernel_meta.get('lmi_gpu_cp_sp_clock',{}).get('enabled')), 'GPU CP SP clock mismatch'
    assert bool(profile.get('lmi_gpu_cp_fence'))==bool(kernel_meta.get('lmi_gpu_cp_fence',{}).get('enabled')), 'GPU CP fence mismatch'
    assert bool(profile.get('lmi_gpu_cp'))==bool(kernel_meta.get('lmi_gpu_cp',{}).get('enabled')), 'GPU CP mismatch'
    assert bool(profile.get('lmi_gpu_core_memory'))==bool(kernel_meta.get('lmi_gpu_core_memory',{}).get('enabled')), 'GPU core memory mismatch'
    assert bool(profile.get('lmi_gpu_cp_plan'))==bool(kernel_meta.get('lmi_gpu_cp_plan',{}).get('enabled')), 'GPU CP plan mismatch'
    assert bool(profile.get('lmi_gpu_gx'))==bool(kernel_meta.get('lmi_gpu_gx',{}).get('enabled')), 'GPU GX profile mismatch'
    assert bool(profile.get('lmi_gpu_hfi_core'))==bool(kernel_meta.get('lmi_gpu_hfi_core',{}).get('enabled')), 'GPU HFI core profile mismatch'
    assert bool(profile.get('lmi_gpu_hfi_perf'))==bool(kernel_meta.get('lmi_gpu_hfi_perf',{}).get('enabled')), 'GPU HFI PERF profile mismatch'
    assert bool(profile.get('lmi_gpu_table_plan'))==bool(kernel_meta.get('lmi_gpu_table_plan',{}).get('enabled')), 'GPU table plan profile mismatch'
    assert bool(profile.get('lmi_gpu_hfi_io'))==bool(kernel_meta.get('lmi_gpu_hfi_io',{}).get('enabled')), 'HFI DMA profile mismatch'
    assert bool(profile.get('lmi_gpu_gmu_boot'))==bool(kernel_meta.get('lmi_gpu_gmu_boot',{}).get('enabled')), 'GMU boot profile mismatch'
    if profile.get('lmi_gpu_gmu_route_probe'):
        assert re.findall(rb'\blmi_gpu=(\d+)\b',(root/'out/lmi-loader/loader.efi').read_bytes())==([b'46'] if profile.get('lmi_gpu_unsecure') else [b'45'] if profile.get('lmi_gpu_zap_load') else [b'44'] if profile.get('lmi_gpu_zap_metadata') else [b'43'] if profile.get('lmi_gpu_scm_query') else [b'42'] if profile.get('lmi_gpu_cp_config_ready') else [b'41'] if profile.get('lmi_gpu_cp_config_plan') else [b'40'] if profile.get('lmi_gpu_fal_veto') else [b'39'] if profile.get('lmi_gpu_core_access') else [b'38'] if profile.get('lmi_gpu_cp_sp_clock') else [b'37'] if profile.get('lmi_gpu_cp_fence') else [b'36'] if profile.get('lmi_gpu_cp') else [b'35'] if profile.get('lmi_gpu_core_memory') else [b'34'] if profile.get('lmi_gpu_cp_plan') else [b'33'] if profile.get('lmi_gpu_gx') else [b'32'] if profile.get('lmi_gpu_hfi_core') else [b'31'] if profile.get('lmi_gpu_hfi_perf') else [b'30'] if profile.get('lmi_gpu_table_plan') else [b'29'] if profile.get('lmi_gpu_hfi_io') else [b'28'] if profile.get('lmi_gpu_gmu_boot') else [b'27']), 'Conflicting/missing GPU boot argument'
    assert bool(profile.get('lmi_gpu_rsc_init'))==bool(kernel_meta.get('lmi_gpu_rsc_init',{}).get('enabled')), 'GPU RSC initialization profile mismatch'
    assert bool(profile.get('lmi_gpu_rsc_state'))==bool(kernel_meta.get('lmi_gpu_rsc_state',{}).get('enabled')), 'GPU RSC state profile mismatch'
    assert bool(profile.get('lmi_gpu_rscc_readonly'))==bool(kernel_meta.get('lmi_gpu_rscc_readonly',{}).get('enabled')), 'GPU RSCC census profile mismatch'
    assert bool(profile.get('lmi_gpu_rpmh_probe'))==bool(kernel_meta.get('lmi_gpu_rpmh_probe',{}).get('enabled')), 'GPU RPMh request profile mismatch'
    assert bool(profile.get('lmi_gpu_rscc_sde_probe'))==bool(kernel_meta.get('lmi_gpu_rscc_sde_probe',{}).get('enabled')), 'GPU SDE clock-gate profile mismatch'
    assert bool(profile.get('lmi_gpu_rpmh_interface_probe'))==bool(kernel_meta.get('lmi_gpu_rpmh_interface_probe',{}).get('enabled')), 'GPU RPMh interface profile mismatch'
    assert bool(profile.get('lmi_gpu_rpmh_bus_probe'))==bool(kernel_meta.get('lmi_gpu_rpmh_bus_probe',{}).get('enabled')), 'GPU RPMh bus profile mismatch'
    assert bool(profile.get('lmi_gpu_rpmh_arc_slot_probe'))==bool(kernel_meta.get('lmi_gpu_rpmh_arc_slot_probe',{}).get('enabled')), 'GPU RPMh ARC slot profile mismatch'
    assert bool(profile.get('lmi_gpu_ram_hfi'))==bool(kernel_meta.get('lmi_gpu_ram_hfi',{}).get('enabled')), 'GPU HFI profile mismatch'
    assert bool(profile.get('lmi_gpu_ram_plan'))==bool(kernel_meta.get('lmi_gpu_ram_plan',{}).get('enabled')), 'GPU RAM plan profile mismatch'
    assert bool(profile.get('lmi_gpu_cb0_readonly'))==bool(kernel_meta.get('lmi_gpu_cb0_readonly',{}).get('enabled')), 'GPU CB0 profile mismatch'
    assert bool(profile.get('lmi_gpu_cb0_table_probe'))==bool(kernel_meta.get('lmi_gpu_cb0_table_probe',{}).get('enabled')), 'GPU table profile mismatch'
    assert bool(profile.get('lmi_gpu_cb0_context_probe'))==bool(kernel_meta.get('lmi_gpu_cb0_context_probe',{}).get('enabled')), 'GPU context profile mismatch'
    assert bool(profile.get('lmi_gpu_cb0_format_probe'))==bool(kernel_meta.get('lmi_gpu_cb0_format_probe',{}).get('enabled')), 'GPU CB0 format profile mismatch'
    if profile.get('lmi_touch_probe') or profile.get('lmi_touch_power_probe') or profile.get('lmi_touch_supply_probe') or profile.get('lmi_touch_input'):
        assert args.ios_continue and kernel_meta.get('lmi_touch_driver',{}).get('enabled'), 'lmi touch requires matching board-specific kernel'
    if args.ios_continue:
        assert profile.get('ios_observe_seconds') in (2,25,45,180) and kernel_meta['return_method']=='linearize RAM log with IRQs off, then loader_checkpoint(63)'
        assert profile.get('smp_cpus',1)==kernel_meta.get('smp_cpus',1),'SMP CPU/return profile mismatch'
        if profile.get('smp_cpus',1)>1:
            smp=kernel_meta['smp_return']
            assert smp['enabled'] and smp['other_cores_off_required'] and smp['unknown_stop_retains_ram']
            assert hashlib.sha256((root/smp['source']).read_bytes()).hexdigest()==smp['source_sha256']
    shutil.copytree(kernel.parent,out/'diagnostic-kernel',dirs_exist_ok=True)
    # Build payloads from the recorded snapshot, including the later iOS
    # payload, so a separate offline build cannot change this test in flight.
    kernel=out/'diagnostic-kernel'/kernel.name
    assert hashlib.sha256(kernel.read_bytes()).hexdigest()==kernel_meta['sha256']
for name in ['lmi-diagnostics.img','manifest.json']:
    shutil.copy2(image.parent/name,out/name)
image=out/'lmi-diagnostics.img'
assert hashlib.sha256(image.read_bytes()).hexdigest()==meta['sha256']
shutil.copytree(root/'out/lmi-loader',out/'source',dirs_exist_ok=True)
provenance=out/'tools';provenance.mkdir(exist_ok=True)
if profile.get('smp_cpus',1)>1:
    for name in ['lmi-smp-return.S','check-lmi-smp-return.py','lmi-touch.c','lmi-touch-timing.h','build-lmi-ios-probe.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_readonly') or profile.get('lmi_gpu_cx_probe') or profile.get('lmi_gpu_ram_plan'):
    shutil.copy2(root/'tools/lmi-gpu-probe.c',provenance/'lmi-gpu-probe.c')
if profile.get('lmi_gpu_ram_plan'):
    shutil.copy2(root/'tools/lmi-gpu-ram.c',provenance/'lmi-gpu-ram.c')
if profile.get('lmi_gpu_stage1_init'):
    shutil.copy2(root/'tools/audit-lmi-gpu-init-region.py',provenance/'audit-lmi-gpu-init-region.py')
if profile.get('lmi_gpu_arc_inventory'):
    for name in ['lmi-gpu-resources.c','lmi-gpu-resources.h']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_rpmh_probe'):
    for name in ['lmi-gpu-rpmh.c','check-lmi-gpu-rpmh.c']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_rsc_init'):
    for name in ['lmi-gpu-rsc-init.c','check-lmi-gpu-rsc-init.c','check-lmi-gpu-rsc-pdc-vote.c','verify-lmi-gpu-rsc-init.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_unsecure'):
    for name in ['lmi-gpu-unsecure.c','check-lmi-gpu-unsecure.c','verify-lmi-gpu-unsecure.py','audit-lmi-gpu-unsecure-region.py','audit-lmi-gpu-normal-diag-region.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_tile'):
    for name in ['lmi-gpu-tile.c','check-lmi-gpu-tile.c','verify-lmi-gpu-tile.py','check-lmi-gpu-tile-source.py','check-lmi-gpu-tile-verifier.py','check-lmi-gpu-normal-preflight.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
    preflight_name='mode46-desktop-preflight.json' if profile.get('lmi_gpu_desktop') else 'mode46-tile-preflight.json'
    preflight=json.loads((root/'out/lmi-gpu-research'/preflight_name).read_text())
    assert preflight['result']=='PASS' and preflight['tile']
    assert bool(preflight.get('desktop'))==bool(profile.get('lmi_gpu_desktop'))
    expected_runtime=(kernel_meta['display_v59']['baseline_runtime_sha256'] if args.display_v59 else kernel_meta['display_v58']['baseline_runtime_sha256'] if args.display_v58 else kernel_meta['display_v57']['baseline_runtime_sha256'] if args.display_v57 else kernel_meta['display_v56']['baseline_runtime_sha256'] if args.display_v56 else kernel_meta['display_v55']['baseline_runtime_sha256'] if args.display_v55 else kernel_meta['display_v54']['baseline_runtime_sha256'] if args.display_v54 else kernel_meta['display_v53']['baseline_runtime_sha256'] if args.display_v53 else kernel_meta['display_v52']['baseline_runtime_sha256'] if args.display_v52 else kernel_meta['display_v51']['baseline_runtime_sha256'] if args.display_v51 else kernel_meta['display_v50']['baseline_runtime_sha256'] if args.display_v50 else kernel_meta['display_v49']['baseline_runtime_sha256'] if args.display_v49 else kernel_meta['display_v48']['baseline_runtime_sha256'] if args.display_v48 else kernel_meta['display_v47']['baseline_runtime_sha256'] if args.display_v47 else kernel_meta['display_v46']['baseline_runtime_sha256'] if args.display_v46 else kernel_meta['display_v45']['baseline_runtime_sha256'] if args.display_v45 else kernel_meta['display_v44']['baseline_runtime_sha256'] if args.display_v44 else kernel_meta['display_v43']['baseline_runtime_sha256'] if args.display_v43 else kernel_meta['display_v42']['baseline_runtime_sha256'] if args.display_v42 else kernel_meta['display_v41']['baseline_runtime_sha256'] if args.display_v41 else kernel_meta['display_v40']['baseline_runtime_sha256'] if args.display_v40 else kernel_meta['source_rebuild']['baseline_runtime_sha256'] if args.source_runtime else kernel_meta['sha256'])
    assert preflight['kernel_sha256']==expected_runtime and preflight['loader_sha256']==profile['sha256'] and preflight['diagnostic_sha256']==meta['sha256']
    for name,sha in preflight['source_sha256'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,'Stale tile preflight source: '+name
    for name in [preflight_name,'mode46-tile-source-audit.json','mode46-tile-offline-validation.json']:
        shutil.copy2(root/'out/lmi-gpu-research'/name,out/name)
    shutil.copy2(root/'out/lmi-gpu-tile-host.log',out/'tile-host.log')
if profile.get('lmi_gpu_desktop'):
    for name in ['lmi-gpu-desktop.c','check-lmi-gpu-desktop.c','lmi-gpu-desktop-profile.py','verify-lmi-gpu-desktop.py','audit-lmi-gpu-desktop-region.py','check-lmi-gpu-desktop-region.py','check-lmi-gpu-desktop-source.py','check-lmi-gpu-desktop-verifier.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
    for name in ['mode46-desktop-source-audit.json','mode46-desktop-offline-validation.json','desktop-region-negative-check.json']:
        shutil.copy2(root/'out/lmi-gpu-research'/name,out/name)
    shutil.copy2(root/'out/lmi-gpu-desktop-host.log',out/'desktop-host.log')
if profile.get('display_census'):
    for name in ['lmi-display-census.c','check-lmi-display-census.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
    census_check=json.loads((root/'out/lmi-display-census-host/result.json').read_text())
    assert census_check['result']=='PASS' and census_check['source_sha256']==profile['display_census_source_sha256']
    shutil.copy2(root/'out/lmi-display-census-host/result.json',out/'display-census-host.json')
if args.ios_boot_image:
    assert profile.get('lmi_gpu_desktop'), 'GLES candidate requires the desktop GPU backend'
    for name in ['verify-lmi-gpu-gl.py','check-lmi-gpu-gl-verifier.py','lmi-gpu-gl-probe.c','build-lmi-gpu-gl-image.py','lmi-wallpaper-probe.c','lmi-kernel-log.c']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_zap_load'):
    for name in ['lmi-gpu-zap-load.c','check-lmi-gpu-zap-load.c','verify-lmi-gpu-zap-load.py','audit-lmi-gpu-frame-region.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_zap_metadata'):
    for name in ['lmi-gpu-zap-metadata.c','check-lmi-gpu-zap-metadata.c','verify-lmi-gpu-zap-metadata.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_scm_query'):
    for name in ['lmi-gpu-scm.c','check-lmi-gpu-scm.c','verify-lmi-gpu-scm.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_gmu_route_probe'):
    for name in ['lmi-gpu-route.c','check-lmi-gpu-route.c','verify-lmi-gpu-route.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_core_access'):
    for name in ['lmi-gpu-core-access.c','check-lmi-gpu-core-access.c','verify-lmi-gpu-core-access.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_cp'):
    for name in ['lmi-gpu-cp.c','check-lmi-gpu-cp.c','verify-lmi-gpu-cp.py','verify-lmi-gpu-cp-config-plan.py','check-lmi-gpu-cp-verifier.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_core_memory'):
    for name in ['lmi-gpu-core-memory.c','check-lmi-gpu-core-memory.c','verify-lmi-gpu-core-memory.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_cp_plan'):
    for name in ['lmi-gpu-cp-plan.c','check-lmi-gpu-cp-plan.c','verify-lmi-gpu-cp-plan.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_gx'):
    for name in ['lmi-gpu-gx.c','check-lmi-gpu-gx.c','verify-lmi-gpu-gx.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_hfi_core'):
    for name in ['lmi-gpu-hfi-core.c','check-lmi-gpu-hfi-core.c','verify-lmi-gpu-hfi-core.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_hfi_perf'):
    for name in ['lmi-gpu-hfi-perf.c','lmi-gpu-hfi-transfer.h','check-lmi-gpu-hfi-perf.c','verify-lmi-gpu-hfi-perf.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_table_plan'):
    for name in ['lmi-gpu-table-plan.c','lmi-gpu-table-plan.h','check-lmi-gpu-table-plan.c','verify-lmi-gpu-table-plan.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_hfi_io'):
    for name in ['lmi-gpu-hfi-io.c','check-lmi-gpu-hfi-io.c','verify-lmi-gpu-hfi-io.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_gmu_boot'):
    for name in ['lmi-gpu-boot.c','lmi-gpu-boot-regs.h','lmi-gpu-runtime.h','check-lmi-gpu-boot.c','check-lmi-gpu-boot-source.py','audit-lmi-gpu-padding.py','verify-lmi-gpu-boot.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
if profile.get('lmi_gpu_gmu_200mhz_probe'):
    for name in ['lmi-gpu-clock.c','check-lmi-gpu-clock.c','verify-lmi-gpu-clock.py']:
        shutil.copy2(root/'tools'/name,provenance/name)
for name in ['lmi-gpu-context.c','lmi-gpu-hfi.c','test-lmi-checkpoints.py','lmi_checkpoint_policy.py','build-lmi-loader.py','lmi-gic-guard.c','build-lmi-preirq-probe.py','build-lmi-bootstrap-probe.py','build-lmi-irq-probe.py','build-lmi-driver-probe.py','build-lmi-bsd-probe.py','build-lmi-root-probe.py','build-lmi-minimal-root.py','build-lmi-user-probe.py','build-lmi-aligned-hello.py','build-lmi-ios-probe.py','lmi-touch.c','prepare-lmi-ios-images.py','verify-ios165-downloads.py']:
    shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v40 or args.display_v41 or args.display_v42 or args.display_v43 or args.display_v44 or args.display_v45 or args.display_v46 or args.display_v47 or args.display_v48 or args.display_v49 or args.display_v50 or args.display_v51 or args.display_v52 or args.display_v53 or args.display_v54 or args.display_v55 or args.display_v56 or args.display_v57 or args.display_v58 or args.display_v59:
    shutil.copy2(root/'tools/lmi_display_v40_policy.py',provenance/'lmi_display_v40_policy.py')
if args.display_v41 or args.display_v42 or args.display_v43:
    shutil.copy2(root/'tools/lmi_display_v41_policy.py',provenance/'lmi_display_v41_policy.py')
if args.display_v43:
    shutil.copy2(root/'tools/lmi_display_v43_policy.py',provenance/'lmi_display_v43_policy.py')
if args.display_v42:
    shutil.copy2(root/'tools/lmi_display_v42_policy.py',provenance/'lmi_display_v42_policy.py')
if args.display_v57 or args.display_v58 or args.display_v59:
    for name in ('lmi_display_v57_policy.py','lmi-gpu-gx-v57.c','build-lmi-display-v57.py','check-lmi-gpu-gx-v57.py','check-lmi-gpu-gx-v57.c','check-lmi-display-v57-policy.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v59:
    for name in ('lmi_display_v59_policy.py','lmi-display-fast-v59.c','lmi-display-fast-v59.h','lmi-display-surface-abi.h','lmi-display-direct-plan.c','lmi-display-direct-plan.h','build-lmi-display-v59.py','check-lmi-display-fast-v59.py','check-lmi-display-fast-v59.c','check-lmi-display-v59-policy.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v58 or args.display_v59:
    for name in ('lmi_display_v58_policy.py','lmi-gpu-desktop-v58.c','build-lmi-gpu-async-v58.py','check-lmi-gpu-async-v58.py','check-lmi-display-v58-policy.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v56 or args.display_v57 or args.display_v58 or args.display_v59:
    for name in ('lmi_display_v56_policy.py','lmi_display_v55_policy.py','lmi_display_v54_policy.py','lmi-display-native-v56.c','lmi-display-compositor-v56.c','build-lmi-display-v56.py','lmi-display-probe-v55.c','lmi-display-dma-v56.c','lmi-display-pipeline-v51.c','check-lmi-display-dma-v56.c','check-lmi-display-dma-v56.py','check-lmi-display-v56-startup.py','check-lmi-display-v56-desktop.py','check-lmi-display-probe-v56.py','check-lmi-display-probe-v56.c','check-lmi-display-v56-policy.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v55:
    for name in ('lmi_display_v55_policy.py','lmi_display_v54_policy.py','lmi-display-native-v55.c','lmi-display-probe-v55.c','lmi-display-dma-v55.c','lmi-display-pipeline-v51.c','check-lmi-display-dma-v55.c','check-lmi-display-dma-v55.py','check-lmi-display-v55-startup.py','check-lmi-display-v55-desktop.py','check-lmi-display-probe-v55.py','check-lmi-display-probe-v55.c','check-lmi-display-v55-policy.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v54:
    for name in ('lmi_display_v54_policy.py','lmi-display-native-v54.c','lmi-display-diagnostic-v54.c','lmi-display-dma-v54.c','lmi-display-pipeline-v51.c','check-lmi-display-dma-v54.c','check-lmi-display-dma-v54.py','check-lmi-display-native-v54.py','check-lmi-display-diagnostic-v54.py','check-lmi-display-diagnostic-v54.c','check-lmi-display-v54-policy.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v53:
    for name in ('lmi_display_v53_policy.py','lmi-display-native-v53.c','lmi-display-diagnostic-v53.c','lmi-display-dma-v53.c','lmi-display-pipeline-v51.c','check-lmi-display-dma-v53.c','check-lmi-display-dma-v53.py','check-lmi-display-native-v53.py','check-lmi-display-diagnostic-v53.py','check-lmi-display-diagnostic-v53.c'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v52:
    for name in ('lmi_display_v52_policy.py','lmi-display-dma-v52.c','lmi-display-pipeline-v51.c','check-lmi-display-dma-v52.c','check-lmi-display-dma-v52.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v51:
    for name in ('lmi_display_v51_policy.py','lmi-display-dma-v49.c','lmi-display-pipeline-v51.c','check-lmi-display-dma-v51.c','check-lmi-display-dma-v51.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v50:
    for name in ('lmi_display_v50_policy.py','lmi-display-dma-v49.c','lmi-display-pipeline-v50.c','check-lmi-display-dma-v50.c','check-lmi-display-dma-v50.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v49:
    for name in ('lmi_display_v49_policy.py','lmi-display-dma-v49.c','check-lmi-display-dma-v49.c','check-lmi-display-dma-v49.py'):
        shutil.copy2(root/'tools'/name,provenance/name)
if args.display_v48:
    shutil.copy2(root/'tools/lmi_display_v48_policy.py',provenance/'lmi_display_v48_policy.py')
if args.display_v47:
    shutil.copy2(root/'tools/lmi_display_v47_policy.py',provenance/'lmi_display_v47_policy.py')
if args.display_v46:
    shutil.copy2(root/'tools/lmi_display_v46_policy.py',provenance/'lmi_display_v46_policy.py')
if args.display_v45:
    shutil.copy2(root/'tools/lmi_display_v45_policy.py',provenance/'lmi_display_v45_policy.py')
if args.display_v44:
    shutil.copy2(root/'tools/lmi_display_v44_policy.py',provenance/'lmi_display_v44_policy.py')
shutil.copy2(root/'tools/lmi-touch-timing.h',provenance/'lmi-touch-timing.h')
payload=out/'kernel-checkpoint.bin'
items=[f'kernel={kernel}']
if args.root_image:
    root_image=args.root_image.resolve()
    assert root_image.is_file() and root_image.stat().st_size+kernel.stat().st_size+4096<0x03f00000
    root_image_meta=dict(bytes=root_image.stat().st_size,sha256=hashlib.sha256(root_image.read_bytes()).hexdigest())
    shutil.copy2(root_image,out/'root.apfs')
    items.append(f'ramdisk={out / "root.apfs"}')
if args.ios_probe:
    assert profile.get('resident_ram_image_enabled') and profile['usb_session_seconds']==600
    ios_dir=args.ios_images.resolve();ios_meta=json.loads((ios_dir/'manifest.json').read_text())
    if profile.get('lmi_gpu_tcm_load') or profile.get('lmi_gpu_ram_plan'):
        firmware=ios_meta.get('gpu_firmware',{})
        assert firmware.get('device')=='lmi' and firmware.get('plain_directory')=='fw'
        selected='lmi_gpu_ram_plan' if profile.get('lmi_gpu_ram_plan') else 'lmi_gpu_tcm_load'
        assert firmware['files']['a650_gmu.bin']['sha256']==kernel_meta[selected]['firmware_sha256']
        assert firmware['files']['a650_gmu.bin']['android_sha256_matches']
        assert ios_meta['images']['root.apfs']['sha256']=='9e1e2fe844d9925d8820f6a406002eb0930e0b33571a8946f405d92375661dd0', 'Unreviewed TCM firmware RAM image'
    assert ios_meta['apple_launchd']['unmodified'] and not ios_meta['persistent_storage_writes']
    for filename in ('system.apfs','root.apfs'):
        path=ios_dir/filename;sha=hashlib.sha256();crc=0;size=0
        with path.open('rb') as f:
            while chunk:=f.read(16*1024*1024):sha.update(chunk);crc=zlib.crc32(chunk,crc);size+=len(chunk)
        record=ios_meta['images'][filename]
        assert record['bytes']==size and record['sha256']==sha.hexdigest() and int(record['crc32'],16)==crc
    assert ios_meta['images']['root.apfs']['bytes']+kernel.stat().st_size+4096<0x03f00000
    assert ios_meta['images']['system.apfs']['bytes']<0x180000000-0x08000000-0x30000000
    os.link(ios_dir/'system.apfs',out/'ios-system.apfs')
    shutil.copy2(ios_dir/'root.apfs',out/'ios-boot.apfs')
    shutil.copy2(ios_dir/'manifest.json',out/'ios-images.json')
    shutil.copy2(ios_dir/'download-verification.json',out/'ios-download-verification.json')
    if args.ios_boot_image:
        candidate = args.ios_boot_image.resolve()
        gl_manifest = json.loads((candidate.parent / 'manifest.json').read_text())
        assert gl_manifest['bytes'] == candidate.stat().st_size
        assert gl_manifest['sha256'] == hashlib.sha256(candidate.read_bytes()).hexdigest()
        assert gl_manifest['baseline_sha256'] == ios_meta['images']['root.apfs']['sha256']
        assert gl_manifest['firmware_preserved'] and gl_manifest['apfs_checked']
        assert candidate.stat().st_size + kernel.stat().st_size + 4096 < 0x03f00000
        shutil.copy2(candidate, out / 'ios-boot.apfs')
        assert hashlib.sha256((out / 'ios-boot.apfs').read_bytes()).hexdigest() == gl_manifest['sha256']
        shutil.copy2(candidate.parent / 'manifest.json', out / 'gl-image.json')
        if gl_manifest.get('gles_copy_regression'):
            regression=gl_manifest['gles_copy_regression']
            for name,expected in regression['source_sha256'].items():
                path=root/name
                assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,'Stale GLES copy source: '+name
                frozen=provenance/'gles-copy'/name
                frozen.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,frozen)
            shutil.copy2(root/'tools/verify-lmi-gl-copy.py',provenance/'verify-lmi-gl-copy.py')
        if gl_manifest.get('bounded_input_trace'):
            for name,expected in gl_manifest['input_trace_source_sha256'].items():
                path=candidate.parent/name
                assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
                shutil.copy2(path,provenance/name)
            if 'inject_sb.c' in gl_manifest['input_trace_source_sha256']:
                observer_check=root/'out/lmi-input-observers-host/result.json'
                observer=json.loads(observer_check.read_text())
                assert observer['result']=='PASS' and observer['abi_scenarios']==6 and observer['unchanged_forwards']==414
                assert observer['source_sha256']==gl_manifest['input_trace_source_sha256']['inject_sb.c']
                shutil.copy2(observer_check,out/'input-observers-host-check.json')
                shutil.copy2(root/'tools/check-lmi-input-observers.py',provenance/'check-lmi-input-observers.py')
        if gl_manifest.get('hid_simple_retry'):
            hid_check=root/'out/lmi-hid-startup-host/result.json'
            hid=json.loads(hid_check.read_text())
            assert hid['result']=='PASS' and hid['retry_scenarios']==hid['legacy_controls']==4
            assert hid['source_sha256']==gl_manifest['input_trace_source_sha256']['inject.c']
            assert hashlib.sha256((candidate.parent/'inject.c').read_bytes()).hexdigest()==hid['source_sha256']
            shutil.copy2(hid_check,out/'hid-startup-host-check.json')
            shutil.copy2(candidate.parent/'inject.c',provenance/'inject.c')
            shutil.copy2(root/'tools/check-lmi-hid-startup.py',provenance/'check-lmi-hid-startup.py')
        if gl_manifest.get('hid_routing_trace'):
            routing_check=root/'out/lmi-hid-routing-host/result.json'
            routing=json.loads(routing_check.read_text())
            assert routing['result']=='PASS' and routing['refusal_controls']==5
            assert routing['unchanged_forwards'] in (140,210) and routing['bounded_logs']==64
            assert routing['source_sha256']==gl_manifest['input_trace_source_sha256']['inject.c']
            shutil.copy2(routing_check,out/'hid-routing-host-check.json')
            shutil.copy2(root/'tools/check-lmi-hid-routing.py',provenance/'check-lmi-hid-routing.py')
        if gl_manifest.get('hid_usage_recheck'):
            usage_check=root/'out/lmi-hid-usage-host/result.json'
            usage=json.loads(usage_check.read_text())
            assert usage['result']=='PASS' and usage['scenarios'] in (14,117)
            if gl_manifest.get('hid_partial_usage_recheck'):
                assert usage['scenarios']==117 and usage['cache_states']==9
                assert usage['repaired_cache_states']==['0/0','13/0','0/4']
                assert usage['invalid_native_controls']==12
                partial=gl_manifest['hid_partial_usage_recheck']
                builder=root/'tools/build-lmi-hid-partial-image.py'
                assert hashlib.sha256(usage_check.read_bytes()).hexdigest()==partial['host_check_sha256']
                assert hashlib.sha256(builder.read_bytes()).hexdigest()==partial['builder_sha256']
                assert partial['baseline_image_sha256']=='4fe1b6afda3bf9543be923240c31accfac8e6e19316b926f7fc85a7e70aada3b'
                assert partial['changed_files']==['lib/libredwood.dylib']
                shutil.copy2(builder,provenance/builder.name)
            assert usage['source_sha256']==gl_manifest['input_trace_source_sha256']['inject.c']
            assert hashlib.sha256((candidate.parent/'inject.c').read_bytes()).hexdigest()==usage['source_sha256']
            shutil.copy2(usage_check,out/'hid-usage-host-check.json')
            shutil.copy2(root/'tools/check-lmi-hid-usage.py',provenance/'check-lmi-hid-usage.py')
            if gl_manifest.get('hid_initial_retry'):
                retry_check=root/'out/lmi-hid-initial-retry-host/result.json'
                retry=json.loads(retry_check.read_text())
                initial=gl_manifest['hid_initial_retry']
                builder=root/'tools/build-lmi-hid-initial-image.py'
                assert retry['result']=='PASS' and retry['scenarios']==1350
                assert retry['max_native_calls']==initial['max_native_calls']==3
                assert retry['manual_setters'] is False
                assert retry['source_sha256']==usage['source_sha256']
                assert hashlib.sha256(retry_check.read_bytes()).hexdigest()==initial['host_check_sha256']
                assert hashlib.sha256(builder.read_bytes()).hexdigest()==initial['builder_sha256']
                assert initial['baseline_image_sha256']=='4fe1b6afda3bf9543be923240c31accfac8e6e19316b926f7fc85a7e70aada3b'
                assert initial['changed_files']==['lib/libredwood.dylib']
                shutil.copy2(retry_check,out/'hid-initial-retry-host-check.json')
                shutil.copy2(root/'tools/check-lmi-hid-initial-retry.py',provenance/'check-lmi-hid-initial-retry.py')
                shutil.copy2(builder,provenance/builder.name)
subprocess.run(['python',str(root/'hackios/xnuloader/mkpayload.py'),'-o',str(payload),*items,'--cmdline=-v','--checkpoint=1'],check=True)
if args.prepare_only:
    (out/'prepared-only.json').write_text(json.dumps(dict(
        result='HOST_PREPARED_ONLY', device_access=False,
        kernel_sha256=kernel_meta['sha256'], display_v40=args.display_v40,display_v41=args.display_v41,display_v42=args.display_v42,display_v43=args.display_v43,display_v44=args.display_v44,display_v45=args.display_v45,display_v46=args.display_v46,display_v47=args.display_v47,display_v48=args.display_v48,display_v49=args.display_v49,display_v50=args.display_v50,display_v51=args.display_v51,display_v52=args.display_v52,display_v53=args.display_v53,display_v54=args.display_v54,display_v55=args.display_v55,display_v56=args.display_v56,display_v57=args.display_v57,display_v58=args.display_v58,display_v59=args.display_v59),indent=2)+'\n')
    print('HOST_PREPARED_ONLY: no device access',flush=True)
    raise SystemExit(0)
adb=['D:/Gaoji/adb.exe','-s','YOUR_ADB_SERIAL']
fb=['D:/Gaoji/fastboot.exe']
target=fb+['-s','xnuloader']
records=[]
result=dict(started=datetime.datetime.now().astimezone().isoformat(),image_sha256=meta['sha256'],records=records)
result['kernel_sha256']=hashlib.sha256(kernel.read_bytes()).hexdigest()
result['early_return_fix']=args.early_return_fix
result['return_guard']=args.return_guard
result['console_probe']=args.console_probe
result['preirq_probe']=args.preirq_probe
result['bootstrap_probe']=args.bootstrap_probe
result['irq_probe']=args.irq_probe
result['driver_probe']=args.driver_probe
result['bsd_probe']=args.bsd_probe
result['root_probe']=args.root_probe
result['user_probe']=args.user_probe
result['ios_probe']=args.ios_probe
result['ios_continue']=args.ios_continue
if args.source_runtime:result['source_rebuild']=kernel_meta['source_rebuild']
if args.display_v40:result['display_v40']=kernel_meta['display_v40']
if args.display_v41:result['display_v41']=kernel_meta['display_v41']
if args.display_v43:result['display_v43']=kernel_meta['display_v43']
if args.display_v42:result['display_v42']=kernel_meta['display_v42']
if args.display_v44:result['display_v44']=kernel_meta['display_v44']
if args.display_v45:result['display_v45']=kernel_meta['display_v45']
if args.display_v46:result['display_v46']=kernel_meta['display_v46']
if args.display_v59:result['display_v59']=kernel_meta['display_v59']
if args.display_v58:result['display_v58']=kernel_meta['display_v58']
if args.display_v57:result['display_v57']=kernel_meta['display_v57']
if args.display_v56:result['display_v56']=kernel_meta['display_v56']
if args.display_v55:result['display_v55']=kernel_meta['display_v55']
if args.display_v54:result['display_v54']=kernel_meta['display_v54']
if args.display_v53:result['display_v53']=kernel_meta['display_v53']
if args.display_v52:result['display_v52']=kernel_meta['display_v52']
if args.display_v51:result['display_v51']=kernel_meta['display_v51']
if args.display_v50:result['display_v50']=kernel_meta['display_v50']
if args.display_v49:result['display_v49']=kernel_meta['display_v49']
if args.display_v48:result['display_v48']=kernel_meta['display_v48']
if args.display_v47:result['display_v47']=kernel_meta['display_v47']
result['ios_result_query_delay_seconds']=args.ios_result_delay_seconds
if args.ios_probe:result['ios_images']=ios_meta
if args.ios_boot_image:result['gl_image']=gl_manifest
if args.root_image:result['root_image']=root_image_meta
result['kernel_memory_floor']=profile.get('kernel_memory_floor','0x0')

def run(args,timeout=15,check=True):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    text=p.stdout+p.stderr
    records.append(dict(command=args,returncode=p.returncode,output=text))
    print(text,flush=True)
    if check and p.returncode: raise RuntimeError(text)
    return text

def wait_fb(serial,seconds=40):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        try:
            p=subprocess.run(fb+['devices'],capture_output=True,text=True,timeout=4)
            if serial in p.stdout:return
        except subprocess.TimeoutExpired:pass
        time.sleep(1)
    raise RuntimeError(f'{serial} did not enumerate')

try:
    assert 'lmi' in run(adb+['shell','getprop','ro.product.device']).splitlines()
    run(adb+['reboot','bootloader'])
    wait_fb('YOUR_ADB_SERIAL')
    assert 'product: lmi' in run(fb+['-s','YOUR_ADB_SERIAL','getvar','product'])
    assert 'unlocked: yes' in run(fb+['-s','YOUR_ADB_SERIAL','getvar','unlocked'])
    run(fb+['-s','YOUR_ADB_SERIAL','boot',str(image)],timeout=40)
    wait_fb('xnuloader')
    assert 'product: lmi-xnuloader-readonly' in run(target+['getvar','product'])
    assert 'only selftest and checkpoints' in run(target+['oem','run'],check=False)
    if args.max_checkpoint>=20:
        assert '1080 2400 4320' in run(target+['getvar','screen'])
        run(target+['oem','screenshot'])
        run(target+['get_staged',str(out/'framebuffer-before.raw')],timeout=20)
    run(target+['stage',str(payload)],timeout=25)
    crc=run(target+['getvar','payload-crc32'])
    assert int(re.search(r'payload-crc32:\s*([0-9a-fA-F]+)',crc)[1],16)==zlib.crc32(payload.read_bytes())&0xffffffff
    result['payload_crc_verified']=True
    checks=[(['oem','selftest'],'selftest-ok 0 0','selftest')]
    checkpoints_to_run=[n for n in checkpoints if not (args.ios_probe and n==61) and not (args.ios_continue and n==62)]
    result['executed_checkpoints']=checkpoints_to_run
    result['skipped_checkpoints']=[n for n in checkpoints if n not in checkpoints_to_run]
    checks.extend((['oem','run',str(n)],f'checkpoint {n} 0',f'checkpoint-{n}') for n in checkpoints_to_run)
    for command,expected,label in checks:
        result['pending_checkpoint']=label
        (out/'hardware-test.json').write_text(json.dumps(result,indent=2)+'\n')
        if label in ('checkpoint-62','checkpoint-63'):
            # Replay the small-root checkpoints first, then replace md0 with
            # the large resident iOS image and make the payload boot disk md1.
            run(target+['oem','ramdisk'])
            run(target+['stage',str(out/'ios-system.apfs')],timeout=300)
            size_reply=run(target+['getvar','resident-size'])
            assert int(re.search(r'resident-size:\s*([0-9a-fA-F]+)',size_reply)[1],16)==ios_meta['images']['system.apfs']['bytes']
            crc_reply=run(target+['getvar','resident-crc32'],timeout=200)
            assert int(re.search(r'resident-crc32:\s*([0-9a-fA-F]+)',crc_reply)[1],16)==int(ios_meta['images']['system.apfs']['crc32'],16)
            result['resident_crc_verified']=True
            ios_payload=out/'kernel-ios.bin'
            subprocess.run(['python',str(root/'hackios/xnuloader/mkpayload.py'),'-o',str(ios_payload),f'kernel={kernel}',f'ramdisk={out / "ios-boot.apfs"}','--cmdline=-v',f'--checkpoint={args.max_checkpoint}'],check=True)
            run(target+['stage',str(ios_payload)],timeout=25)
            crc_reply=run(target+['getvar','payload-crc32'])
            assert int(re.search(r'payload-crc32:\s*([0-9a-fA-F]+)',crc_reply)[1],16)==zlib.crc32(ios_payload.read_bytes())&0xffffffff
            result['ios_payload_crc_verified']=True
        run_started=time.monotonic()
        run(target+command,timeout=50 if label in ('checkpoint-62','checkpoint-63') else 15)
        if label=='checkpoint-63' and args.ios_result_delay_seconds:
            print(f'Host-only control: waiting{args.ios_result_delay_seconds}s without USB queries before reading result',flush=True)
            time.sleep(args.ios_result_delay_seconds)
        response=run(target+['getvar','result'],timeout=50 if label in ('checkpoint-62','checkpoint-63') else 25)
        if label=='checkpoint-63':result['ios_host_run_seconds']=time.monotonic()-run_started
        result[label]=response
        if label=='selftest':
            run(target+['oem','memmap'])
            run(target+['oem','log'])
        # run_kernel already staged the combined loader and returned XNU log.
        # Idle `oem log` recomposes only the loader log and discards XNU text.
        run(target+['get_staged',str(out/f'{label}.log')])
        if label=='checkpoint-63' and (args.display_v41 or args.display_v42 or args.display_v43 or args.display_v44 or args.display_v45 or args.display_v46 or args.display_v47 or args.display_v48 or args.display_v49 or args.display_v50 or args.display_v51 or args.display_v52 or args.display_v53 or args.display_v54 or args.display_v55 or args.display_v56 or args.display_v57 or args.display_v58 or args.display_v59):
            import runpy
            observation=runpy.run_path(str(provenance/('lmi_display_v59_policy.py' if args.display_v59 else 'lmi_display_v58_policy.py' if args.display_v58 else 'lmi_display_v57_policy.py' if args.display_v57 else 'lmi_display_v56_policy.py' if args.display_v56 else 'lmi_display_v55_policy.py' if args.display_v55 else 'lmi_display_v54_policy.py' if args.display_v54 else 'lmi_display_v53_policy.py' if args.display_v53 else 'lmi_display_v52_policy.py' if args.display_v52 else 'lmi_display_v51_policy.py' if args.display_v51 else 'lmi_display_v50_policy.py' if args.display_v50 else 'lmi_display_v49_policy.py' if args.display_v49 else 'lmi_display_v48_policy.py' if args.display_v48 else 'lmi_display_v47_policy.py' if args.display_v47 else 'lmi_display_v46_policy.py' if args.display_v46 else 'lmi_display_v45_policy.py' if args.display_v45 else 'lmi_display_v44_policy.py' if args.display_v44 else 'lmi_display_v43_policy.py' if args.display_v43 else 'lmi_display_v42_policy.py' if args.display_v42 else 'lmi_display_v41_policy.py')))['observe']((out/f'{label}.log').read_text())
            result['dpu_observation']=observation
            (out/'dpu-observation.json').write_text(json.dumps(observation,indent=2)+'\n')
        if label=='checkpoint-63':
            # Preserve the visible outcome even if the kernel panicked early.
            run(target+['oem','screenshot'])
            run(target+['get_staged',str(out/'framebuffer-checkpoint-63.raw')],timeout=20)
        assert expected in response, f'{label} did not return as expected'
        if label=='selftest':
            log=(out/f'{label}.log').read_text()
            claim=re.search(r'phys window ([0-9a-f]+) size ([0-9a-f]+), claim status 0',log)
            assert claim, 'No successful UEFI kernel window allocation recorded'
            base,size=int(claim[1],16),int(claim[2],16)
            assert base>=int(result['kernel_memory_floor'],16)
            maps=re.findall(r'^\s+([0-9a-f]+) - ([0-9a-f]+)\s+type (\d+)\s+',log,re.M)
            assert any(int(k)==2 and int(lo,16)<=base and base+size<=int(hi,16) for lo,hi,k in maps)
            result['kernel_window']=dict(base=hex(base),size=hex(size),uefi_loader_data_verified=True)
        if label=='checkpoint-50':
            log=(out/f'{label}.log').read_text()
            assert 'lmi GIC snapshot:' in log and 'lmi GIC return: restored=0 matches=1' in log, 'GIC snapshot/readback not verified'
        if label in ('checkpoint-21','checkpoint-52','checkpoint-53','checkpoint-54','checkpoint-55','checkpoint-56','checkpoint-57','checkpoint-58','checkpoint-59','checkpoint-60','checkpoint-61','checkpoint-62','checkpoint-63'):
            log=(out/f'{label}.log').read_bytes().decode('utf-8',errors='replace').replace('\r\n','\n')
            assert 'lmi GIC return: restored=1 matches=1' in log, 'GIC restoration not verified'
            assert re.search(r'lmi GIC observed: group=[0-9a-f]+ enabled=[0-9a-f]+ priority=a0\b',log), 'Expected XNU virtual-timer priority was not observed'
        if label=='checkpoint-63' and (profile.get('lmi_gpu_readonly') or profile.get('lmi_gpu_cx_probe')):
            if profile.get('lmi_gpu_rpmh_probe'):
                code=re.search(r'LMI_GPU_RPMH_RESULT\n([0-9a-f]{16})\n',log)
                requests=re.findall(r'LMI_GPU_RPMH_REQUEST_ADDRESS\n([0-9a-f]{16})\nLMI_GPU_RPMH_REQUEST_SELECTOR\n([0-9a-f]{16})\n',log)
                reasons={0:'refused or bad completion',1:'complete',2:'pre-request/state/storage uncertain',3:'AMC-enable readback failed',4:'IRQ completion timeout',5:'completed but TCS non-idle',6:'control clear failed',7:'IRQ clear failed',8:'SDE gate disable/restore readback failed'}
                result['gpu_rpmh_attempt']=dict(result_code=int(code[1],16) if code else None,requests=[dict(address=hex(int(a,16)),selector=int(v,16)) for a,v in requests],dependencies_retained='LMI_GPU_RPMH_KEEP_CLOCKS_UNTIL_RESET\n' in log,voltage_verified=False)
                assert code and int(code[1],16)==1, 'GPU RPMh: '+(reasons.get(int(code[1],16),'unknown result') if code else 'result missing')
            assert profile.get('lmi_gpu_wired_context') or profile.get('lmi_gpu_rsc_pdc_vote_probe') or ('LMI_GPU_READONLY_BEGIN\n' in log and 'LMI_GPU_READONLY_END\n' in log), 'GPU inventory did not finish'
            assert 'LMI_GPU_NO_GCC_MAP' not in log, 'GPU GCC mapping failed'
            values=re.findall(r'LMI_GPU_GCC_OFFSET\n([0-9a-f]{16})\nLMI_GPU_GCC_VALUE\n([0-9a-f]{16})\n',log)
            assert len(values)==(0 if profile.get('lmi_gpu_wired_context') or profile.get('lmi_gpu_rsc_pdc_vote_probe') else 5), 'Missing GPU external clock register values'
            result['gpu_inventory']=dict(readonly=bool(profile.get('lmi_gpu_readonly')),hardware_acceleration_verified=False,
                gcc={hex(int(k,16)):hex(int(v,16)) for k,v in values},
                gpucc_skipped_clock_off='LMI_GPU_GPUCC_CLOCK_OFF_SKIP' in log)
            if profile.get('lmi_gpu_cx_probe') and not profile.get('lmi_gpu_gmu_boot'):
                def gpu_value(key):
                    value=re.search(key+r'\n([0-9a-f]{16})\n',log)
                    assert value,key
                    return int(value[1],16)
                assert 'LMI_GPU_CX_POWER_END' in log, 'CX probe did not finish'
                on=gpu_value('LMI_GPU_CX_POWER_STATUS');hw=gpu_value('LMI_GPU_CX_HW_STATUS')
                restored=gpu_value('LMI_GPU_CX_RESTORED_STATUS');restored_hw=gpu_value('LMI_GPU_CX_RESTORED_HW')
                assert (on|hw)&(1<<31), 'CX power-on not observed'
                assert restored&1 and not ((restored|restored_hw)&(1<<31)), 'CX domain not restored off'
                result['gpu_cx_power']=dict(power_on_verified=True,restored_off=True,hardware_acceleration_verified=False)
                if profile.get('lmi_gpu_clock_probe'):
                    assert 'LMI_GPU_CLOCK_END' in log, 'Clock probe did not finish'
                    clocks=re.findall(r'LMI_GPU_CLOCK_OFFSET\n([0-9a-f]{16})\nLMI_GPU_CLOCK_STATUS\n([0-9a-f]{16})\n',log)
                    assert {int(k,16) for k,v in clocks}=={0x1078,0x109c,0x1098}
                    # Critical AHB uses HALT_DELAY, not a reliable halt status.
                    assert all(not(int(v,16)&(1<<31)) for k,v in clocks if int(k,16)!=0x1078), 'GMU/crystal clock halted'
                    restores=re.findall(r'LMI_GPU_CLOCK_RESTORE_OFFSET\n([0-9a-f]{16})\nLMI_GPU_CLOCK_RESTORE_EXPECTED\n([0-9a-f]{16})\nLMI_GPU_CLOCK_RESTORE_ACTUAL\n([0-9a-f]{16})\n',log)
                    assert {int(k,16) for k,_,_ in restores}=={0x1078,0x109c,0x1098} and all(expected==actual for _,expected,actual in restores), 'Clock vote restore mismatch'
                    assert gpu_value('LMI_GPU_CLOCK_SOURCE')&0x371f==1
                    result['gpu_clocks']=dict(crystal_source=True,branch_status={hex(int(k,16)):hex(int(v,16)) for k,v in clocks},votes_restored=True,hardware_acceleration_verified=False)
                    if profile.get('lmi_gpu_gmu_readonly'):
                        assert 'LMI_GPU_GMU_END' in log, 'GMU register probe did not finish'
                        assert gpu_value('LMI_GPU_GMU_SYSRESET')==1
                        if not profile.get('lmi_gpu_rpmh_probe'):
                            delta=gpu_value('LMI_GPU_GMU_COUNTER_DELTA');ticks=gpu_value('LMI_GPU_GMU_CPU_TICKS');cpu_hz=gpu_value('LMI_GPU_GMU_CPU_HZ')
                            assert ticks>0 and cpu_hz>0, 'Invalid CPU counter timing'
                            hz=delta*cpu_hz/ticks
                            assert 18000000<hz<20500000, f'GMU AO counter not crystal rate: {hz}'
                            result['gpu_gmu_registers']=dict(sysreset=hex(gpu_value('LMI_GPU_GMU_SYSRESET')),ao_counter_delta=delta,measured_hz=hz,firmware_started=False,hardware_acceleration_verified=False)
                        else:
                            result['gpu_gmu_registers']=dict(sysreset='0x1',ao_counter_measured=False,firmware_started=False,hardware_acceleration_verified=False)
                        if profile.get('lmi_gpu_tcm_load'):
                            assert 'LMI_GPU_TCM_END' in log, 'TCM probe did not finish'
                            assert gpu_value('LMI_GPU_TCM_BYTES')==18404
                            assert gpu_value('LMI_GPU_TCM_FIRMWARE_CRC')==0x5c66275c
                            assert gpu_value('LMI_GPU_TCM_MISMATCHES')==0, 'TCM firmware readback mismatch'
                            assert gpu_value('LMI_GPU_TCM_RESTORE_MISMATCHES')==0, 'Original TCM words not restored'
                            assert gpu_value('LMI_GPU_GMU_SYSRESET')==1, 'CM3 was not initially held in reset'
                            assert gpu_value('LMI_GPU_TCM_RESET_AFTER')==1, 'CM3 reset changed'
                            assert [int(v,16) for v in re.findall(r'LMI_GPU_TCM_BLOCK_OFFSET\n([0-9a-f]{16})\n',log)]==[0x3000,0x3200,0x3400,0x7000,0xafdc]
                            result['gpu_tcm']=dict(bytes=18404,readback_verified=True,original_words_restored_verified=True,cm3_held_in_reset=True,firmware_started=False,hardware_acceleration_verified=False)
                        if profile.get('lmi_gpu_smmu_readonly') and not profile.get('lmi_gpu_gmu_route_probe'):
                            assert 'LMI_GPU_SMMU_END\n' in log and 'LMI_GPU_SMMU_STREAMS_END\n' in log, 'SMMU inventory did not finish'
                            assert gpu_value('LMI_GPU_GMU_SYSRESET')==1 and 'LMI_GPU_TCM_BEGIN' not in log
                            bus=re.findall(r'LMI_GPU_SMMU_CLOCK_OFFSET\n([0-9a-f]{16})\nLMI_GPU_SMMU_CLOCK_STATUS\n([0-9a-f]{16})\n',log)
                            assert {int(k,16) for k,v in bus}=={0x7100c,0x71018}
                            assert all(not (int(v,16)&(1<<31)) or int(v,16)&0xf0000000==0x20000000 for k,v in bus)
                            restored=re.findall(r'LMI_GPU_SMMU_RESTORE_OFFSET\n([0-9a-f]{16})\nLMI_GPU_SMMU_RESTORE_EXPECTED\n([0-9a-f]{16})\nLMI_GPU_SMMU_RESTORE_ACTUAL\n([0-9a-f]{16})\nLMI_GPU_SMMU_RESTORE_STATUS\n([0-9a-f]{16})\n',log)
                            assert {int(k,16) for k,expected,actual,status in restored}=={0x7100c,0x71018}
                            assert all(expected==actual for k,expected,actual,status in restored), 'SMMU bus votes not restored'
                            assert all(int(status,16)&(1<<31) for k,expected,actual,status in restored if int(k,16)==0x71018 and int(expected,16)==0), 'SNOC halt not observed after relinquishing new vote'
                            regs={int(k,16):int(v,16) for k,v in re.findall(r'LMI_GPU_SMMU_READ_ADDRESS\n([0-9a-f]{16})\nLMI_GPU_SMMU_VALUE\n([0-9a-f]{16})\n',log)}
                            assert set(regs)=={0x3da0020,0x3da0024,0x3da0028,0x3da003c,0x3da0000,0x3da0048}
                            id0,id1=regs[0x3da0020],regs[0x3da0024]
                            nr=id0&255;page=65536 if id1&(1<<31) else 4096
                            global_size=page*(1<<(((id1>>28)&7)+1));cb=id1&255
                            assert id0 not in (0,0xffffffff) and id0&(1<<27) and 0<nr<=128
                            assert cb>0 and ((id1>>16)&255)<=cb and global_size+cb*page<=0x10000
                            streams=re.findall(r'LMI_GPU_SMMU_STREAM_INDEX\n([0-9a-f]{16})\nLMI_GPU_SMMU_SMR\n([0-9a-f]{16})\nLMI_GPU_SMMU_S2CR\n([0-9a-f]{16})\n',log)
                            assert [int(i,16) for i,smr,s2cr in streams]==list(range(nr)), 'Incomplete SMMU stream census'
                            result['gpu_smmu_inventory']=dict(registers={hex(k):hex(v) for k,v in regs.items()},page_bytes=page,global_bytes=global_size,context_banks=cb,
                                streams=[dict(index=int(i,16),smr=hex(int(smr,16)),s2cr=hex(int(s2cr,16))) for i,smr,s2cr in streams],
                                bus_votes_restored=True,smmu_written=bool(profile.get('lmi_gpu_cb0_format_probe') or profile.get('lmi_gpu_cb0_context_probe') or profile.get('lmi_gpu_wired_context')),contexts_accessed=bool(profile.get('lmi_gpu_cb0_readonly')),firmware_started=False,hardware_acceleration_verified=False)
        if label=='checkpoint-63' and profile.get('lmi_gpu_cb0_readonly'):
            assert 'LMI_GPU_CB0_END\n' in log and 'LMI_GPU_CB0_REFUSED' not in log
            values=re.findall(r'LMI_GPU_CB0_READ_ADDRESS\n([0-9a-f]{16})\nLMI_GPU_CB0_VALUE\n([0-9a-f]{16})\n',log)
            expected=[0x1000,0x1800,0x8000,0x8010,0x8020,0x8024,0x8028,0x802c,0x8030,0x8034,0x8038,0x803c,0x8058,0x8060,0x8064]
            assert [int(a,16) for a,v in values]==[0x3da0000+a for a in expected]*3
            snapshots=[{int(a,16):int(v,16) for a,v in values[n:n+15]} for n in (0,15,30)]
            changes=sum(snapshot[a]!=snapshots[0][a] for snapshot in snapshots[1:] for a in snapshot)
            reported=re.search(r'LMI_GPU_CB0_CHANGED_READS\n([0-9a-f]{16})\n',log)
            assert reported and int(reported[1],16)==changes
            regs=snapshots[0]
            result['gpu_cb0_snapshot']=dict(registers={hex(a):hex(v) for a,v in regs.items()},
                snapshots=[{hex(a):hex(v) for a,v in snapshot.items()} for snapshot in snapshots],
                changed_reads=changes,read_stability_verified=changes==0,
                translation_enabled=bool(regs[0x3da8000]&1),ownership_verified=False,smmu_written=bool(profile.get('lmi_gpu_cb0_format_probe') or profile.get('lmi_gpu_cb0_context_probe') or profile.get('lmi_gpu_wired_context')),hardware_acceleration_verified=False)
        if label=='checkpoint-63' and profile.get('lmi_gpu_cb0_format_probe'):
            def format_value(key):
                match=re.search(key+r'\n([0-9a-f]{16})\n',log)
                assert match,key
                return int(match[1],16)
            assert 'LMI_GPU_CB0_FORMAT_END\n' in log, 'CB0 format probe did not complete'
            before=format_value('LMI_GPU_CB0_FORMAT_BEFORE');written=format_value('LMI_GPU_CB0_FORMAT_WRITTEN');restored=format_value('LMI_GPU_CB0_FORMAT_RESTORED')
            assert before==0 and restored==before, 'CB0 format original not restored'
            assert format_value('LMI_GPU_CB0_FORMAT_SCTLR')==regs[0x3da8000], 'CB0 SCTLR changed during format probe'
            assert format_value('LMI_GPU_CB0_FORMAT_GFSR')==0, 'Nonzero global fault status after CB0 format restore'
            result['gpu_cb0_format']=dict(before=before,requested=1,readback=written,
                write_observed=written==1,restored=True,translation_enabled=False,hardware_acceleration_verified=False)
        if label=='checkpoint-63' and profile.get('lmi_gpu_cb0_context_probe'):
            assert 'LMI_GPU_CB0_CONTEXT_END'+chr(10) in log, 'Context probe did not complete'
            keys=['OFFSET','BEFORE','REQUESTED','ACTUAL','RESTORED']
            lists={key:[int(v,16) for v in re.findall('LMI_GPU_CB0_CONTEXT_'+key+chr(10)+'([0-9a-f]{16})'+chr(10),log)] for key in keys}
            expected=[0x1800,0x1000,0x8010,0x8030,0x8020,0x8024,0x8028,0x802c,0x8038,0x803c]
            assert lists['OFFSET']==expected and all(len(v)==10 for v in lists.values()), 'Incomplete context register evidence'
            result['gpu_cb0_context']=dict(registers=lists,configuration_observed=lists['ACTUAL']==lists['REQUESTED'],restored=lists['RESTORED']==lists['BEFORE'],translation_enabled=False,hardware_acceleration_verified=False)
            assert lists['BEFORE']==[regs[0x3da0000+a] for a in expected], 'Context original snapshot changed'
            requested=[1,0x1f300,0x38011,0x803519,0,0,0,0,0xf404ff44,0]
            if profile.get('lmi_gpu_cb0_table_probe'):
                m=re.search('LMI_GPU_CB0_TABLE_ROOT'+chr(10)+'([0-9a-f]{16})'+chr(10),log)
                assert m, 'No owned root evidence'
                root_pa=int(m[1],16);window=result['kernel_window']
                base=int(window['base'],16);size=int(window['size'],16)
                assert root_pa%4096==0 and root_pa>>36==0 and base<=root_pa<=base+size-4096
                requested[1]=regs[0x3da1000];requested[4]=root_pa&0xffffffff;requested[5]=root_pa>>32
                assert 'LMI_GPU_CB0_TABLE_FREED'+chr(10) in log and 'LMI_GPU_CB0_TABLE_RETAINED' not in log
                result['gpu_cb0_table']=dict(root_pa=hex(root_pa),zero_filled=True,freed_after_restore=True,cbar_written=False,translation_enabled=False,hardware_translation_verified=False)
            assert lists['REQUESTED']==requested
            assert lists['RESTORED']==lists['BEFORE'], 'Context registers not restored'
            for key,value in [('SCTLR',regs[0x3da8000]),('GFSR',0),('FSR',0)]:
                m=re.search('LMI_GPU_CB0_CONTEXT_'+key+chr(10)+'([0-9a-f]{16})'+chr(10),log)
                assert m and int(m[1],16)==value, 'Unexpected context post-status '+key
        if label=='checkpoint-63' and profile.get('lmi_gpu_rpmh_probe'):
            assert re.search(r'LMI_GPU_RPMH_RESULT\n0000000000000001\n',log), 'GPU RPMh result is not complete'
            if profile.get('lmi_gpu_rscc_sde_probe'):
                sde=re.search(r'LMI_GPU_RPMH_SDE_GATE_DISABLED\n([0-9a-f]{16})\n',log)
                assert sde and int(sde[1],16)&0x1000000 and 'LMI_GPU_RPMH_SDE_GATE_RESTORED\n' in log
            if profile.get('lmi_gpu_rpmh_interface_probe'):
                interface=re.search(r'LMI_GPU_RPMH_INTERFACE_ENABLED\n([0-9a-f]{16})\n',log)
                assert interface and int(interface[1],16)==0xf11 and 'LMI_GPU_RPMH_INTERFACE_RESTORED\n' in log
            for key in ['LMI_GPU_RPMH_GPU_VOTES_RETAINED_UNTIL_RESET','LMI_GPU_RPMH_MIN_VOTES_COMPLETE']:
                assert key+'\n' in log,key
            assert all(key not in log for key in ['LMI_GPU_RPMH_PENDING_UNTIL_RESET','LMI_GPU_RPMH_KEEP_CLOCKS_UNTIL_RESET','LMI_GPU_RPMH_NOT_COMPLETE'])
            requests=re.findall(r'LMI_GPU_RPMH_REQUEST_ADDRESS\n([0-9a-f]{16})\nLMI_GPU_RPMH_REQUEST_SELECTOR\n([0-9a-f]{16})\n',log)
            assert [(int(a,16),int(v,16)) for a,v in requests]==[(0x30010,2),(0x30000,2)]
            statuses=[int(v,16) for v in re.findall(r'LMI_GPU_RPMH_COMMAND_STATUS\n([0-9a-f]{16})\n',log)]
            assert len(statuses)==2 and all(v&0x10100==0x10100 for v in statuses)
            if profile.get('lmi_gpu_rpmh_bus_probe'):
                assert log.index('LMI_GPU_SMMU_CLOCK_OFFSET\n') < log.index('LMI_GPU_RPMH_REQUEST_ADDRESS\n'), 'Bus clocks were not prepared before requests'
                result['gpu_rpmh_bus_before_requests']=True
            if profile.get('lmi_gpu_rpmh_arc_slot_probe'):
                assert re.search(r'LMI_GPU_RPMH_TCS_SLOT\n0000000000000001\n',log), 'Missing firmware ARC slot1 evidence'
            result['gpu_rpmh_probe']=dict(drv='GPU DRV0',slot=1 if profile.get('lmi_gpu_rpmh_arc_slot_probe') else 0,requests=['MX selector2 level128','CX selector2 level64'],command_statuses=[hex(v) for v in statuses],tcs_storage_restored=True,votes_retained_until_reset=True,physical_voltage_measured=False,frequency_changed=False,hardware_acceleration_verified=False)
        if label=='checkpoint-63' and profile.get('lmi_gpu_rscc_readonly') and not profile.get('lmi_gpu_rpmh_probe') and not profile.get('lmi_gpu_rsc_init'):
            assert 'LMI_GPU_RSCC_READONLY_OK\n' in log and 'LMI_GPU_RSCC_LAYOUT_REFUSED' not in log, 'RSCC census refused or incomplete'
            chunks=log.split('LMI_GPU_RSCC_BEGIN\n')[1].split('LMI_GPU_RSCC_READONLY_OK\n')[0]
            pairs=[(int(a,16),int(v,16)) for a,v in re.findall(r'LMI_GPU_RSCC_READ_OFFSET\n([0-9a-f]{16})\nLMI_GPU_RSCC_VALUE\n([0-9a-f]{16})\n',chunks)]
            offsets=[0xc,0x10,0x2c,0x404,0xd00,0xd04]+[0xd00+slot*0x2a0+off for slot in range(10) for off in [0x10,0x14,0x18,0x1c,0x30,0x34,0x38,0x3c,0x40,0x44,0x48,0x4c,0x50,0x54]]
            assert [a for a,v in pairs]==offsets and all(v<=0xffffffff for a,v in pairs), 'RSCC census address/value mismatch'
            registers=dict(pairs)
            assert registers[0xc]==0x4000000a and registers[0xc]&63==10 and (registers[0xc]>>27)&31==8
            slots=[int(v,16) for v in re.findall(r'LMI_GPU_RSCC_SLOT\n([0-9a-f]{16})\n',chunks)]
            assert slots==list(range(10))
            result['gpu_rscc_readonly']=dict(physical='0x03de0000',registers={hex(a):hex(v) for a,v in pairs},rpmh_writes=False,voltage_verified=False)
        if label=='checkpoint-63' and profile.get('lmi_gpu_rsc_state'):
            import runpy
            result['gpu_rsc_state']=runpy.run_path(str(root/'tools/verify-lmi-gpu-rsc-state.py'))['verify'](log)
        if label=='checkpoint-63' and profile.get('lmi_gpu_rsc_init') and not profile.get('lmi_gpu_gmu_boot'):
            import runpy
            result['gpu_rsc_init']=runpy.run_path(str(provenance/'verify-lmi-gpu-rsc-init.py'))['verify'](log,sequence_only=bool(profile.get('lmi_gpu_rsc_sequence_probe')),pdc_enable=bool(profile.get('lmi_gpu_pdc_enable_probe')),vote_probe=bool(profile.get('lmi_gpu_rsc_pdc_vote_probe')),clock_probe=bool(profile.get('lmi_gpu_gmu_200mhz_probe')),route_probe=bool(profile.get('lmi_gpu_gmu_route_probe')))
        if label=='checkpoint-63' and profile.get('lmi_gpu_gmu_200mhz_probe') and not profile.get('lmi_gpu_gmu_boot'):
            import runpy
            result['gpu_gmu_200mhz']=runpy.run_path(str(provenance/'verify-lmi-gpu-clock.py'))['verify'](log)
        if label=='checkpoint-63' and profile.get('lmi_gpu_gmu_route_probe') and not profile.get('lmi_gpu_gmu_boot'):
            import runpy
            result['gpu_gmu_route']=runpy.run_path(str(provenance/'verify-lmi-gpu-route.py'))['verify'](log,(root/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes(),result['kernel_window'])
        if label=='checkpoint-63' and profile.get('lmi_gpu_gmu_boot'):
            import runpy
            result['gpu_gmu_boot']=runpy.run_path(str(provenance/('verify-lmi-gpu-desktop.py' if profile.get('lmi_gpu_desktop') else 'verify-lmi-gpu-tile.py' if profile.get('lmi_gpu_tile') else 'verify-lmi-gpu-unsecure.py' if profile.get('lmi_gpu_unsecure') else 'verify-lmi-gpu-zap-load.py' if profile.get('lmi_gpu_zap_load') else 'verify-lmi-gpu-zap-metadata.py' if profile.get('lmi_gpu_zap_metadata') else 'verify-lmi-gpu-scm.py' if profile.get('lmi_gpu_scm_query') else 'verify-lmi-gpu-cp-config-plan.py' if profile.get('lmi_gpu_cp_config_plan') else 'verify-lmi-gpu-core-access.py' if profile.get('lmi_gpu_core_access') else 'verify-lmi-gpu-cp.py' if profile.get('lmi_gpu_cp') else 'verify-lmi-gpu-core-memory.py' if profile.get('lmi_gpu_core_memory') else 'verify-lmi-gpu-cp-plan.py' if profile.get('lmi_gpu_cp_plan') else 'verify-lmi-gpu-gx.py' if profile.get('lmi_gpu_gx') else 'verify-lmi-gpu-hfi-core.py' if profile.get('lmi_gpu_hfi_core') else 'verify-lmi-gpu-hfi-perf.py' if profile.get('lmi_gpu_hfi_perf') else 'verify-lmi-gpu-table-plan.py' if profile.get('lmi_gpu_table_plan') else 'verify-lmi-gpu-hfi-io.py' if profile.get('lmi_gpu_hfi_io') else 'verify-lmi-gpu-boot.py')))['verify'](log,(root/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes(),result['kernel_window'])
        if label=='checkpoint-63' and profile.get('lmi_gpu_cp_config_ready'):
            assert result['gpu_gmu_boot']['mode']==(46 if profile.get('lmi_gpu_unsecure') else 45 if profile.get('lmi_gpu_zap_load') else 44 if profile.get('lmi_gpu_zap_metadata') else 43 if profile.get('lmi_gpu_scm_query') else 42), 'GPU mode requires its own exact config-ready and CP execution proof'
        if label=='checkpoint-63' and args.ios_boot_image:
            result['gpu_gl_probe']=dict(hardware_shader_readback_verified=False,
                records=[line for line in log.splitlines() if 'LMI_GL_' in line])
            result['gpu_gl_probe']=runpy.run_path(str(provenance/'verify-lmi-gpu-gl.py'))['verify'](log)
            if gl_manifest.get('gles_copy_regression'):
                result['gles_copy_regression']=runpy.run_path(str(provenance/'verify-lmi-gl-copy.py'))['verify'](log)
        if label=='checkpoint-63' and profile.get('lmi_touch_input'):
            result['touch_input']=dict(driver_ready='LMI_TOUCH_READY\n' in log,
                backboardd_touching_records=len(re.findall(r'contact \d+ presence: touching',log)),
                physical_interaction_verified=False)
            assert log.count('LMI_TOUCH_BEGIN\n')==log.count('LMI_TOUCH_READY\n')==1, 'FT3518 input did not become ready'
            assert 'LMI_TOUCH_SUPPLY_UNCONFIRMED' not in log, 'FT3518 supply was not confirmed'
        if label=='checkpoint-63' and profile.get('lmi_gpu_arc_inventory') and not profile.get('lmi_gpu_rpmh_probe'):
            assert 'LMI_GPU_ARC_INVENTORY_OK'+chr(10) in log and 'LMI_GPU_ARC_REFUSED' not in log, 'ARC DB not verified'
            arc_chunks=log.split('LMI_GPU_ARC_RESOURCE'+chr(10))[1:]
            assert len(arc_chunks)==2, 'Expected exactly CX and MX ARC resources'
            arc_resources=[]
            for index,chunk in enumerate(arc_chunks):
                def arc_value(key):
                    m=re.search('LMI_GPU_ARC_'+key+chr(10)+'([0-9a-f]{16})'+chr(10),chunk)
                    assert m,key
                    return int(m[1],16)
                assert int(chunk.splitlines()[0],16)==index
                address=arc_value('ADDRESS');selector=arc_value('MIN_SVS_SELECTOR')
                pairs=re.findall('LMI_GPU_ARC_SELECTOR'+chr(10)+'([0-9a-f]{16})'+chr(10)+'LMI_GPU_ARC_LEVEL'+chr(10)+'([0-9a-f]{16})'+chr(10),chunk)
                levels=[int(v,16) for i,v in pairs]
                assert 2<=len(pairs)<=16 and [int(i,16) for i,v in pairs]==list(range(len(pairs)))
                assert levels[0]==0 and all(a<b<=65535 for a,b in zip(levels,levels[1:]))
                assert selector==next(i for i,v in enumerate(levels) if v>=48)
                assert address and address%4==0 and (address>>16)&7==3
                arc_resources.append(dict(name=['cx.lvl','mx.lvl'][index],address=hex(address),levels=levels,min_svs_selector=selector))
            assert arc_resources[0]['address']!=arc_resources[1]['address']
            result['gpu_arc_inventory']=dict(resources=arc_resources,rpmh_writes=False,hardware_acceleration_verified=False)
        if label=='checkpoint-63' and profile.get('lmi_gpu_wired_context'):
            def wired_value(key):
                m=re.search('LMI_GPU_WIRED_CONTEXT_'+key+chr(10)+'([0-9a-f]{16})'+chr(10),log)
                assert m,key
                return int(m[1],16)
            rows={key:[int(v,16) for v in re.findall('LMI_GPU_WIRED_CONTEXT_'+key+chr(10)+'([0-9a-f]{16})'+chr(10),log)] for key in ['OFFSET','BEFORE','REQUESTED','ACTUAL','RESTORED']}
            offsets=[0x1800,0x8010,0x8030,0x8020,0x8024,0x8028,0x802c,0x8038,0x803c]
            assert rows['OFFSET']==offsets and all(len(v)==9 for v in rows.values())
            root_pa=wired_value('ROOT')
            requested=[1,0x38071,0x803519,root_pa&0xffffffff,root_pa>>32,0,0,0xf404ff44,0]
            stage1=bool(profile.get('lmi_gpu_stage1_init'))
            if stage1:requested[4]|=0x10000
            assert rows['REQUESTED']==requested and rows['ACTUAL']==requested, 'Wired configuration mismatch'
            assert rows['BEFORE']==[regs[0x3da0000+a] for a in offsets]
            assert rows['RESTORED']==rows['BEFORE'], 'Wired context restoration mismatch'
            during_values=[int(v,16) for v in re.findall('LMI_GPU_WIRED_CONTEXT_DURING_VALUE'+chr(10)+'([0-9a-f]{16})'+chr(10),log)]
            assert during_values==[regs[0x3da8000],0x1f300 if stage1 else regs[0x3da1000],0,0x400], 'Unexpected live control/FSR format or fault bits'
            if stage1:
                def stage1_value(key):
                    m=re.search('LMI_GPU_STAGE1_'+key+chr(10)+'([0-9a-f]{16})'+chr(10),log)
                    assert m,key
                    return int(m[1],16)
                assert regs[0x3da1000]==0 and stage1_value('CBAR_RETAINED')==0x1f300
                assert stage1_value('LOCAL_SYNC')==1, 'Local ASID1 TLB sync incomplete'
                result['gpu_stage1_init']=dict(cbar_before=0,cbar_initialized='0x1f300',cbar_restored=False,context_disabled=True,streams_published=False,local_asid1_sync=True,firmware_execution=False,hardware_acceleration_verified=False)
            assert wired_value('SAFE')==wired_value('DURING_SAFE')==wired_value('MATCHED')==1
            assert 'LMI_GPU_RAM_RETAINED' not in log
            assert log.index('LMI_GPU_RAM_SOFTWARE_WALK_OK')<log.index('LMI_GPU_WIRED_CONTEXT_ROOT')<log.index('LMI_GPU_WIRED_CONTEXT_SAFE')<log.index('LMI_GPU_RAM_CLEANUP_DONE')
            ram_root=re.search('LMI_GPU_RAM_ROOT_PA'+chr(10)+'([0-9a-f]{16})'+chr(10),log)
            assert ram_root and int(ram_root[1],16)==root_pa
            result['gpu_wired_context']=dict(root_pa=hex(root_pa),registers=rows,nine_registers_restored=True,cbar_restored=not stage1,backing_wired_until_restore=True,translation_enabled=False,firmware_execution=False,hardware_acceleration_verified=False)
        if label=='checkpoint-63' and profile.get('lmi_gpu_ram_plan') and not profile.get('lmi_gpu_gmu_route_probe'):
            def ram_value(key):
                match=re.search(key+r'\n([0-9a-f]{16})\n',log)
                assert match,key
                return int(match[1],16)
            assert 'LMI_GPU_RAM_SOFTWARE_WALK_OK\n' in log and 'LMI_GPU_RAM_CLEANUP_DONE\n' in log and 'LMI_GPU_RAM_END\n' in log
            assert ram_value('LMI_GPU_RAM_FAILED')==0
            assert 'LMI_GPU_TCM_BEGIN' not in log
            assert profile.get('lmi_gpu_wired_context') or ('LMI_GPU_READONLY_BEGIN' not in log and 'LMI_GPU_SMMU_BEGIN' not in log)
            base=ram_value('LMI_GPU_RAM_CLAIM_BASE');size=ram_value('LMI_GPU_RAM_CLAIM_SIZE');page=ram_value('LMI_GPU_RAM_XNU_PAGE')
            assert base==int(result['kernel_window']['base'],16) and size==int(result['kernel_window']['size'],16)
            payload_pages=42 if profile.get('lmi_gpu_ram_hfi') else 37
            total_pages=payload_pages+5
            assert page in (4096,16384) and ram_value('LMI_GPU_RAM_WIRED_BYTES')==((total_pages*4096+page-1)//page)*page
            assert ram_value('LMI_GPU_RAM_PAYLOAD_PAGES')==payload_pages and ram_value('LMI_GPU_RAM_TABLE_PAGES')==5
            pages=re.findall(r'LMI_GPU_RAM_PAGE_INDEX\n([0-9a-f]{16})\nLMI_GPU_RAM_PAGE_PA\n([0-9a-f]{16})\n',log)
            assert [int(i,16) for i,p in pages]==list(range(total_pages))
            pas=[int(p,16) for i,p in pages]
            assert len(set(pas))==total_pages and all(base<=p<=base+size-4096 and p%4096==0 and p>>36==0 for p in pas)
            assert ram_value('LMI_GPU_RAM_ROOT_PA')==pas[payload_pages]
            fw=(root/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
            assert hashlib.sha256(fw).hexdigest()==kernel_meta['lmi_gpu_ram_plan']['firmware_sha256']
            segments=[(0x4000,0x8000,14812,21968),(0x144000,0x13000,0,0),(0x157000,0x9000,36796,920),(0x60000000,0x1000,0,0)]
            expected={address:zlib.crc32(fw[offset:offset+length]+bytes(bytes_count-length)) for address,bytes_count,offset,length in segments}
            if profile.get('lmi_gpu_ram_hfi'):
                hfi=bytearray(20480)
                struct.pack_into('<6I',hfi,0,0,54,6,12,4,4)
                for i,priority in enumerate((10,10,40,20)):
                    ring_offset=256 if 'LMI_GPU_RAM_HFI_RING_OFFSET\n' in log else 224
                    struct.pack_into('<12I',hfi,24+i*48,int(i<3),0x60001000+ring_offset+i*4096,i|(priority<<8),1024,*([0]*8))
                expected[0x60001000]=zlib.crc32(hfi)
                assert ram_value('LMI_GPU_RAM_HFI_ADDRESS')==0x60001000 and ram_value('LMI_GPU_RAM_HFI_BYTES')==20480
            measured={int(a,16):int(c,16) for a,c in re.findall(r'LMI_GPU_RAM_SEGMENT_ADDRESS\n([0-9a-f]{16})\nLMI_GPU_RAM_SEGMENT_CRC\n([0-9a-f]{16})\n',log)}
            assert measured==expected, 'GMU prealloc payload/zero-fill mismatch'
            result['gpu_ram_plan']=dict(wired_bytes=ram_value('LMI_GPU_RAM_WIRED_BYTES'),xnu_page_bytes=page,payload_pages=payload_pages,table_pages=5,hfi_verified=bool(profile.get('lmi_gpu_ram_hfi')),
                page_pas=[hex(p) for p in pas],root_pa=hex(pas[payload_pages]),segment_crcs={hex(a):hex(c) for a,c in measured.items()},
                software_walk_verified=True,allocation_freed=True,gpu_mmio_access=bool(profile.get('lmi_gpu_wired_context')),hardware_translation_verified=False,hardware_acceleration_verified=False)
        if label in ('checkpoint-55','checkpoint-56'):
            created=re.search(r'LMI_BOOTSTRAP_THREAD_CREATED\n([0-9a-f]{16})\n',log)
            entered=re.search(r'LMI_BOOTSTRAP_THREAD_ENTERED\n([0-9a-f]{16})\n',log)
            stack=re.search(r'LMI_BOOTSTRAP_THREAD_STACK\n([0-9a-f]{16})\n',log)
            assert created and entered and stack, 'Missing native thread context evidence'
            assert created[1]==entered[1] and int(created[1],16) and int(stack[1],16), 'Current thread does not match the newly created bootstrap thread'
            result['bootstrap_thread']=dict(created=created[1],current=entered[1],stack=stack[1],verified=True)
        if label=='checkpoint-56':
            nub=re.search(r'LMI_IOKIT_ROOT_NUB\n([0-9a-f]{16})\n',log)
            pages=re.search(r'LMI_VM_FREE_PAGES\n([0-9a-f]{16})\n',log)
            assert nub and pages and int(nub[1],16) and int(pages[1],16), 'Missing live IOKit root nub or VM free pages'
            result['iokit_core']=dict(root_nub=nub[1],vm_free_pages=int(pages[1],16),verified=True)
        if label=='checkpoint-57':
            count=re.search(r'LMI_VTIMER_IRQ_SERVICED\n([0-9a-f]{16})\n',log)
            iar=re.search(r'LMI_ACTIVE_IRQ_IAR\n([0-9a-f]{16})\n',log)
            unknown=re.search(r'LMI_UNHANDLED_IRQS\n([0-9a-f]{16})\n',log)
            assert count and iar and unknown and int(count[1],16)>0 and int(iar[1],16)&0xffffff==27 and int(unknown[1],16)==0, 'No verified native timer IRQ service'
            assert 'lmi IRQ return: isolated=1 matches=1' in log and 'spi-mask-ok=1' in log, 'Resident IRQ isolation/restore was not verified'
            result['native_timer_irq']=dict(timer_count=int(count[1],16),iar=iar[1],unhandled=0,verified=True)
        if label=='checkpoint-58':
            assert 'LMI_BSD_INIT_BOUNDARY\n' in log
            def sample(marker):
                m=re.search(re.escape(marker)+r'\n([0-9a-f]{16})\n',log)
                assert m, f'Missing {marker}'
                return int(m[1],16)
            count=sample('LMI_NORMAL_IRQ_TIMER_COUNT')
            iar=sample('LMI_THREAD_CONTEXT_IAR');unknown=sample('LMI_THREAD_CONTEXT_UNHANDLED')
            platform=sample('LMI_PLATFORM_OBJECT');pv=sample('LMI_PLATFORM_VTABLE')
            cpu=sample('LMI_CPU_OBJECT');cv=sample('LMI_CPU_VTABLE');processors=sample('LMI_PROCESSOR_COUNT')
            assert count>0 and iar==0 and unknown==0, 'No verified normal timer IRQ return to thread context'
            assert platform and pv==int(kernel_meta['expected_platform_vtable'],16), 'GenericARMPE object not verified'
            assert cpu and cv==int(kernel_meta['expected_cpu_vtable'],16) and processors==1, 'GenericARMCPU/processor count not verified'
            assert 'lmi IRQ return: isolated=1 matches=1' in log and 'spi-mask-ok=1' in log
            result['driver_matching']=dict(platform=hex(platform),platform_vtable=hex(pv),cpu=hex(cpu),cpu_vtable=hex(cv),processors=processors,verified=True)
            result['normal_irq_return']=dict(timer_count=count,active_iar=iar,unhandled=unknown,verified=True)
            result['bsd_init_boundary']=True
        if label=='checkpoint-59':
            assert 'LMI_BSD_BEFORE_ROOT_SELECTION\n' in log
            assert all(marker+'\n' in log for marker in ('LMI_BSD_BUFFER_INIT_RETURNED','LMI_BSD_VFS_INIT_RETURNED','LMI_BSD_IOKIT_INIT_RETURNED','LMI_BSD_NETWORK_INIT_RETURNED'))
            def bsd_sample(marker):
                m=re.search(re.escape(marker)+r'\n([0-9a-f]{16})\n',log)
                assert m, f'Missing {marker}'
                return int(m[1],16)
            proc=bsd_sample('LMI_BSD_CURRENT_PROC');kernproc=bsd_sample('LMI_BSD_KERNPROC');pid=bsd_sample('LMI_BSD_PID')
            bsd_map=bsd_sample('LMI_BSD_PAGEABLE_MAP');vfs_ops=bsd_sample('LMI_BSD_VFS_OPS');loopback=bsd_sample('LMI_BSD_LOOPBACK')
            root_vnode=bsd_sample('LMI_BSD_ROOT_VNODE');first_mount=bsd_sample('LMI_BSD_FIRST_MOUNT')
            assert proc and proc==kernproc and pid==0 and bsd_map and vfs_ops>0 and loopback, 'BSD process/VFS/loopback state was not verified'
            assert root_vnode==0 and first_mount==0, 'Unexpected root vnode or mounted filesystem'
            assert 'lmi IRQ return: isolated=1 matches=1' in log and 'spi-mask-ok=1' in log
            result['bsd_setup']=dict(current_proc=hex(proc),kernproc=hex(kernproc),pid=pid,pageable_map=hex(bsd_map),vfs_ops=vfs_ops,loopback=hex(loopback),root_vnode=root_vnode,first_mount=first_mount,verified=True)
        if label=='checkpoint-60':
            def root_sample(marker):
                m=re.search(re.escape(marker)+r'\n([0-9a-f]{16})\n',log)
                assert m, f'Missing {marker}'
                return int(m[1],16)
            vnode=root_sample('LMI_ROOT_VNODE');mount=root_sample('LMI_ROOT_MOUNT');device=root_sample('LMI_ROOT_DEVICE')
            assert vnode and mount and 'LMI_ROOT_FS_NAME\napfs\n' in log, 'APFS root not verified'
            assert 'rd=md0' in log and 'lmi IRQ return: isolated=1 matches=1' in log
            ram=re.search(r'ramdisk at pa ([0-9a-f]+) size ([0-9a-f]+)',log)
            assert ram
            lo,sz=int(ram[1],16),int(ram[2],16)
            window=result['kernel_window'];start=int(window['base'],16);end=start+int(window['size'],16)
            assert start<=lo and lo+sz<=end and sz>=root_image_meta['bytes']
            result['ram_root']=dict(vnode=hex(vnode),mount=hex(mount),device=hex(device),filesystem='apfs',phys_base=hex(lo),size=sz,verified=True)
        if label=='checkpoint-61':
            def el0_sample(marker):
                m=re.search(re.escape(marker)+r'\n([0-9a-f]{16})\n',log)
                assert m, f'Missing {marker}'
                return int(m[1],16)
            pid=el0_sample('LMI_EL0_PID');flavor=el0_sample('LMI_EL0_STATE_FLAVOR');pc=el0_sample('LMI_EL0_PC')
            pstate=el0_sample('LMI_EL0_PSTATE');esr=el0_sample('LMI_EL0_ESR');x16=el0_sample('LMI_EL0_X16')
            assert pid==1 and flavor==21 and 0<pc<(1<<48) and pstate&15==0 and esr>>26==0x15 and esr&0xffff==0x80 and x16==1, 'PID1 saved EL0 SYS_exit state not verified'
            assert 'lmi IRQ return: isolated=1 matches=1' in log
            result['static_darwin_el0']=dict(pid=pid,flavor=flavor,pc=hex(pc),pstate=hex(pstate),esr=hex(esr),syscall=x16,verified=True,apple_ios_userspace=False)
        if label in ('checkpoint-62','checkpoint-63'):
            assert 'LMI_IOS_PID1_NAME\nlaunchd.ios\n' in log
            def ios_sample(marker):
                m=re.search(re.escape(marker)+r'\n([0-9a-f]{16})\n',log)
                assert m, f'Missing {marker}'
                return int(m[1],16)
            pid=ios_sample('LMI_IOS_PID');flavor=ios_sample('LMI_IOS_STATE_FLAVOR');pc=ios_sample('LMI_IOS_PC')
            pstate=ios_sample('LMI_IOS_PSTATE');esr=ios_sample('LMI_IOS_ESR');x16=ios_sample('LMI_IOS_X16')
            assert pid==1 and flavor==21 and 0<pc<(1<<48) and pstate&15==0 and esr>>26==0x15 and esr&0xffff==0x80 and x16==20
            assert result['resident_crc_verified'] and result['ios_payload_crc_verified'] and 'lmi IRQ return: isolated=1 matches=1' in log
            assert 'it is the root (md0), the payload ramdisk is md1' in log
            result['apple_ios_el0']=dict(name='launchd.ios',pid=pid,pc=hex(pc),pstate=hex(pstate),esr=hex(esr),syscall=x16,verified=True,apple_launchd_sha256=ios_meta['apple_launchd']['sha256'],desktop_verified=False)
            if label=='checkpoint-63':
                assert 'LMI_IOS_GETPID_CONTINUING\n' in log
                assert 'LMI_RAM_ONLY_TIMER_EXPIRED\n' in log, 'Dedicated RAM-only timer did not expire'
                assert '=== 36 checks, 0 failed ===' in log
                assert 'panic(cpu' not in log and 'Debugger message: panic' not in log, 'Kernel panic observed'
                frequency=ios_sample('LMI_TIMER_CNTFRQ');start_ticks=ios_sample('LMI_IOS_CONTINUE_CNTVCT');end_ticks=ios_sample('LMI_RAM_ONLY_TIMER_EXPIRED')
                assert frequency==19200000 and end_ticks>start_ticks
                result['bounded_ios_run']=dict(seconds=profile['ios_observe_seconds'],ram_only_timer_verified=True,native_getpid_resumed=True,post_getpid_counter_seconds=(end_ticks-start_ticks)/frequency,desktop_verified=False)
                if profile.get('smp_cpus',1)>1:
                    counts=[int(value,16) for value in re.findall(r'LMI_SMP_ONLINE_BEFORE_STOP\r?\n([0-9a-fA-F]{16})',log)]
                    assert counts and 'LMI_SMP_OTHER_CORES_OFF\n' in log and 'LMI_SMP_RETURN_HELD\n' not in log,'SMP return not verified'
                    result['smp_run']=dict(requested_cpus=profile['smp_cpus'],observed_online_counts=counts,all_other_cores_off_verified=True,all_requested_online_verified=max(counts)==profile['smp_cpus'])
        result['pending_checkpoint']=None
        (out/'hardware-test.json').write_text(json.dumps(result,indent=2)+'\n')
    if args.max_checkpoint>=20:
        run(target+['oem','screenshot'])
        run(target+['get_staged',str(out/f'framebuffer-checkpoint-{args.max_checkpoint}.raw')],timeout=20)
        before=(out/'framebuffer-before.raw').read_bytes()
        after=(out/f'framebuffer-checkpoint-{args.max_checkpoint}.raw').read_bytes()
        assert len(before)==len(after)==4320*2400
        result['framebuffer']=dict(before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(after).hexdigest(),changed=before!=after)
        if args.console_probe:
            assert before!=after, 'Console probe did not change the framebuffer'
            assert 'HackiOS lmi: XNU framebuffer console test' in (out/'checkpoint-20.log').read_text(), 'Returned XNU log lacks the console marker'
        if args.max_checkpoint==56:
            assert before!=after and 'Checkpoint 56 - RAM-only test' in (out/'checkpoint-56.log').read_text(), 'Missing bootstrap console evidence'
    result['result']='PASS: MMU return path and XNU checkpoints '+','.join(map(str,checkpoints_to_run))
except Exception as e:
    result['result']='INCOMPLETE'
    result['error']=str(e)
    result['error_type']=type(e).__name__
    result['error_traceback']=traceback.format_exc()
    print('Test stopped:',e,flush=True)
finally:
    (out/'hardware-test.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        p=subprocess.run(fb+['devices'],capture_output=True,text=True,timeout=4)
        if 'xnuloader' in p.stdout:run(target+['reboot'],timeout=6,check=False)
    except subprocess.TimeoutExpired:pass
    print('Waiting for Android to return...',flush=True)
    until=time.monotonic()+140
    while time.monotonic()<until:
        try:
            p=subprocess.run(adb+['shell','getprop','sys.boot_completed'],capture_output=True,text=True,timeout=4)
            if p.returncode==0 and p.stdout.strip()=='1':break
        except subprocess.TimeoutExpired:pass
        time.sleep(3)
    else:
        result['android_return']='not observed within timeout'
        (out/'hardware-test.json').write_text(json.dumps(result,indent=2)+'\n')
        raise RuntimeError('Android return not observed; inspect phone')
    digests=run(adb+['exec-out','su','-c','sha256sum /dev/block/by-name/boot /dev/block/by-name/dtbo'],timeout=25)
    original={'boot':'ab6a887047f7f169bf2fc3e95e23dca929ba87ab4749d725e9bd4ebc4a38f662','dtbo':'41d5aa69150b084504081e6e4234317d8c8d1179e31b66e532eff0276b6c21e1'}
    restore=dict(android_boot_completed=True,original_partition_hashes_match={k:v in digests for k,v in original.items()},digests=digests)
    (out/'android-return.json').write_text(json.dumps(restore,indent=2)+'\n')
    result['android_return']=restore
    (out/'hardware-test.json').write_text(json.dumps(result,indent=2)+'\n')
    assert all(restore['original_partition_hashes_match'].values())
print(result['result'],flush=True)
if not result['result'].startswith('PASS:'):raise SystemExit(1)
