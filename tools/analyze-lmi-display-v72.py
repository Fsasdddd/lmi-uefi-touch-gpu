"""Analyze one saved run; preserve legacy failures and raw evidence."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,traceback
import lmi_display_v72_policy as policy
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence',type=Path,nargs='?',default=root/'out/lmi-checkpoint-63-ios-probe-test-display-v72-desktop-180')
parser.add_argument('--console',type=Path,help='Saved host console for launch-dispatch evidence only')
args=parser.parse_args();folder=args.evidence.resolve()
hardware=json.loads((folder/'hardware-test.json').read_text(encoding='utf-8'))
assert hardware.get('android_return') is not None,'Wait for return collection'
if not (folder/'checkpoint-63.log').exists():
    transferred=hardware.get('ios_payload_crc_verified') is True
    console=args.console.read_text(encoding='utf-8',errors='replace') if args.console else ''
    dispatched=transferred and console.count('Host-only control: waiting185s without USB queries before reading result')==1
    report=dict(result=hardware['result'],primary_error=hardware.get('error'),error_type=hardware.get('error_type'),
        kernel_sha256=hardware['kernel_sha256'],kernel_transfer_complete=transferred,
        launch_command_returned=dispatched if args.console else None,
        desktop_started=None if transferred else False,runtime_gpu_frame_verified=False,
        android_return=hardware['android_return'],performance_verified=False,measured_animation_fps=None,
        scope=('Kernel transmitted and verified, but checkpoint63 log was not collected; desktop/GPU behavior is unknown'
               if transferred else 'Runtime payload staging did not complete before checkpoint63; no v72 desktop/GPU behavior was exercised'),
        sources={'hardware-test.json':hashlib.sha256((folder/'hardware-test.json').read_bytes()).hexdigest()})
    feedback=folder/'user-feedback.json'
    if feedback.exists():
        report['user_feedback']=json.loads(feedback.read_text(encoding='utf-8'))
        report['sources'][feedback.name]=hashlib.sha256(feedback.read_bytes()).hexdigest()
        if report['user_feedback'].get('desktop_observed') is False:
            report['desktop_started']=False
            report['desktop_status_basis']='User observation; no XNU runtime log recovered'
            report['startup_regression_observed']=True
            report['scope']='User observed a persistent Apple logo and no desktop; kernel execution stage and GPU-copy outcome remain unknown'
    recovery=folder/'android-recovery-after-runtime-timeout.json'
    if recovery.exists():
        report['later_android_recovery']=json.loads(recovery.read_text(encoding='utf-8'))
        report['sources'][recovery.name]=hashlib.sha256(recovery.read_bytes()).hexdigest()
    if args.console:report['host_console']=dict(path=str(args.console.resolve()),sha256=hashlib.sha256(args.console.read_bytes()).hexdigest())
    report['analysis_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (folder/'result-analysis-v72.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(0)
log=(folder/'checkpoint-63.log').read_text(encoding='utf-8',errors='replace')
observation=policy.observe(log);validation=policy.validate_run(observation)
saved=json.loads((folder/'dpu-observation.json').read_text(encoding='utf-8'))
assert saved==observation,'Current parser must match frozen run parser'
try:
    detail=runpy.run_path(str(folder/'tools/verify-lmi-gpu-desktop.py'))['verify'](
        log,(root/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes(),hardware['kernel_window'])
    legacy=dict(passed=True,detail=detail)
except Exception as error:
    legacy=dict(passed=False,error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
c=observation['gpu_frame']['counts'];fast=observation['fast_path'];total=(observation['desktop_stats'] or [{}])[0].get('frames')
report=dict(result=hardware['result'],primary_error=hardware.get('error'),kernel_sha256=hardware['kernel_sha256'],
    validation=validation,original_validation=hardware.get('display_v72_validation'),
    gpu_frame=observation['gpu_frame'],fast_path=fast,desktop_stats=observation['desktop_stats'],
    preclean=observation['preclean'],target_cache=observation['target_cache'],gpu_copy_overlap=observation['gpu_copy_overlap'],deferred_cpu_cache=observation['deferred_cpu_cache'],producer_retirement=observation['producer_retirement'],
    gpu_queue=observation['gpu_queue'],gpu_map_batch=observation['gpu_map_batch'],
    copy_probe=observation['copy_probe'],independent_legacy=legacy,raw_log_changed=False,verifier_changed=False,
    android_return=hardware['android_return'],
    copy_submit_to_join_us_per_frame=c['copy_ticks']/19.2/c['draws'] if c.get('draws') else None,
    target_prepare_us_per_gpu_frame=(observation['target_cache']['counts'][4]/19.2/c['draws']) if observation['target_cache']['counts'] and c.get('draws') else None,
    scope='Submit-to-join includes native show tail, lock acquisition, GPU fence wait and status-page invalidate; CPU target ownership transfers are separate; it is not pure GPU time or panel FPS. Later queued counts submissions, not measured execution overlap. CPU partial composition remains.',
    gpu_frame_share=c['frames']/total if c.get('frames') is not None and total else None,
    stop_boundary=dict(
        source_begun=observation['producer_retirement']['counts'][0] if observation['producer_retirement']['counts'] else None,
        source_retired=observation['producer_retirement']['counts'][1] if observation['producer_retirement']['counts'] else None,
        outstanding_source_retirements=(observation['producer_retirement']['counts'][0]-observation['producer_retirement']['counts'][1]) if observation['producer_retirement']['counts'] else None,
        expected_submissions_including_probe=40+total if total is not None else None,
        observed_submissions=observation['desktop_stats'][0]['submitted'] if len(observation['desktop_stats'])==1 else None,
        note='Preserve strict rejection: a composed frame is not proof of DPU submission or source retirement; no counter is rewritten.'),
    extra_source_retains_at_return=c['retained']-c['released'] if c.get('retained') is not None else None,
    allocations_retained_until_ram_return=True,wifi_integrated=False,performance_verified=False,measured_animation_fps=None,
    panic_found=bool(re.search(r'panic\(cpu|Kernel Extensions in backtrace|Debugger message: panic',log)),
    ram_timer_expired=log.count('LMI_RAM_ONLY_TIMER_EXPIRED\n')==1,
    other_cores_stopped=log.count('LMI_SMP_OTHER_CORES_OFF\n')==1)
feedback=folder/'user-feedback.json'
if feedback.exists():report['user_feedback']=json.loads(feedback.read_text(encoding='utf-8'))
names=['hardware-test.json','checkpoint-63.log','dpu-observation.json','android-return.json']
if feedback.exists():names.append(feedback.name)
report['sources']={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in names}
report['analysis_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(folder/'result-analysis-v72.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['result','validation','gpu_frame','fast_path','copy_submit_to_join_us_per_frame',
    'gpu_frame_share','android_return']},ensure_ascii=False,indent=2))
