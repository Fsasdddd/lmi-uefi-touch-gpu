"""Analyze a finished v80 run, preserving original logs and legacy failures."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,traceback
import lmi_display_v80_policy as policy

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('evidence',type=Path);p.add_argument('--console',type=Path)
args=p.parse_args();folder=args.evidence.resolve()
hardware_path=folder/'hardware-test.json';hardware=json.loads(hardware_path.read_text(encoding='utf-8'))
assert hardware.get('android_return') is not None,'First collect the existing test through Android return'
report=dict(result=hardware['result'],primary_error=hardware.get('error'),error_type=hardware.get('error_type'),
    kernel_sha256=hardware['kernel_sha256'],android_return=hardware['android_return'],
    raw_log_changed=False,legacy_verifier_changed=False,performance_verified=False,
    measured_animation_fps=None,wifi_integrated=False,
    ios_payload_crc_verified=hardware.get('ios_payload_crc_verified') is True,
    run63_command_acknowledged=any(row.get('command',[])[-3:]==['oem','run','63'] and row.get('returncode')==0
        for row in hardware.get('records',[])))
paths=[hardware_path,Path(__file__),ROOT/'tools/lmi_display_v80_policy.py']
logpath=folder/'checkpoint-63.log'
if logpath.exists():
    log=logpath.read_text(encoding='utf-8',errors='replace')
    observation=policy.observe(log);validation=policy.validate_run(observation)
    saved=folder/'dpu-observation.json'
    assert json.loads(saved.read_text(encoding='utf-8'))==observation
    keys=['async_dpu','cpu_epss','display_timing','gpu_frame','fast_path','desktop_stats','preclean','target_cache',
          'gpu_copy_overlap','deferred_cpu_cache','producer_retirement','gpu_queue','gpu_map_batch','copy_probe']
    report.update(validation=validation,**{k:observation[k] for k in keys})
    verifier=folder/'tools/verify-lmi-gpu-desktop.py'
    try:
        detail=runpy.run_path(str(verifier))['verify'](log,
            (ROOT/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes(),hardware['kernel_window'])
        report['independent_legacy']=dict(passed=True,detail=detail)
    except Exception as error:
        report['independent_legacy']=dict(passed=False,error_type=type(error).__name__,
            error=str(error),traceback=traceback.format_exc())
    report['panic_found']=bool(re.search(r'panic\(cpu|Kernel Extensions in backtrace|Debugger message: panic',log))
    report['ram_timer_expired']=log.count('LMI_RAM_ONLY_TIMER_EXPIRED\n')==1
    report['other_cores_stopped']=log.count('LMI_SMP_OTHER_CORES_OFF\n')==1
    report['timing_mean_us']={key:metric['mean_us'] for key,metric in observation['display_timing']['metrics'].items()}
    report['cpu_request_interpretation']='Requested LUT index readback is not measured CPU frequency or animation FPS.'
    report['timing_interpretation']='SOURCE and COPY overlap FRAME. GAP/CADENCE include idle/scheduling; these means and frame totals do not measure animation FPS. Different user actions prevent a controlled speedup claim.'
    paths.extend([logpath,saved,verifier])
else:
    report['runtime_log_recovered']=False
    report['new_gpu_dpu_admission_passed']=None
    report['scope']='No recovered checkpoint63 log; transfer and launch acknowledgement do not prove GPU/DPU execution or safe retirement.'
for name in ['android-return.json','user-feedback.json']:
    path=folder/name
    if path.exists():report[name.removesuffix('.json').replace('-','_')]=json.loads(path.read_text(encoding='utf-8'));paths.append(path)
if args.console:paths.append(args.console.resolve())
report['sources']={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
target=folder/'result-analysis-v80.json';assert not target.exists(),'Preserve previous analysis'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({key:report[key] for key in ['result','primary_error','validation','timing_mean_us','android_return'] if key in report},ensure_ascii=False,indent=2))
