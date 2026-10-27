"""Summarize saved hardware logs, without treating mixed windows as animation FPS."""
from pathlib import Path
import argparse,json,re
p=argparse.ArgumentParser();p.add_argument('evidence',type=Path);args=p.parse_args()
folder=args.evidence;log=(folder/'checkpoint-63.log').read_text()
observation=json.loads((folder/'dpu-observation.json').read_text())
# The loader can retain the same timestamped kernel ring slice more than
# once. Count each exact timestamped report once; retain raw logs unchanged.
timing_lines=list(dict.fromkeys(line for line in log.splitlines() if
    re.search(r'^\[\s*\d+\.\d+\]: MiniIOMobileFramebuffer:',line)))
timing_log='\n'.join(timing_lines)
windows=[dict(frames=int(a),ms=int(b),reported_per_second=int(c),driver_us=int(d),gpu_wait_us=int(e))
    for a,b,c,d,e in re.findall(r'MiniIOMobileFramebuffer: (\d+) frames in (\d+) ms \((\d+) a second\), (\d+) us each in the driver, after (\d+) us waiting for the GPU',timing_log)]
intervals=[dict(under_10ms=int(a),under_18ms=int(b),under_26ms=int(c),under_35ms=int(d),longer=int(e),
    longest_ms=int(f),median_below_ms=int(g),p95_below_ms=int(h),pauses=int(i))
    for a,b,c,d,e,f,g,h,i in re.findall(r'from one frame to the next: (\d+) times under 10 ms, (\d+) under 18, (\d+) under 26, (\d+) under 35, (\d+) longer \(the longest (\d+) ms\); half under (\d+) ms, 95 in 100 under (\d+) ms; (\d+) pauses',timing_log)]
hardware=json.loads((folder/'hardware-test.json').read_text())
report=dict(desktop_pipeline_enabled=observation['desktop_pipeline_enabled'],desktop_stats=observation['desktop_stats'],
    cache_submit_us_per_frame=observation.get('cache_submit_us_per_frame'),gpu_frequency=observation.get('gpu_frequency'),
    async_gpu=observation.get('async_gpu'),fast_path=observation.get('fast_path'),
    qualification_metadata=observation.get('qualification_metadata'),framebuffer_windows=windows,
    frame_interval_summaries=intervals,android_return=hardware.get('android_return'),
    whole_test_result=hardware.get('result'),whole_test_error_type=hardware.get('error_type'),
    measured_animation_fps=None,performance_verified=False,exact_timestamped_reports_deduplicated=True,
    limitation='Windows and whole-run counts include static periods and uncontrolled user input. Driver timing omits preservation copy and the outer DPU wait. Intervals are native show timestamps, not measured panel timestamps; pauses >=90ms are excluded by the native histogram. Do not infer controlled animation FPS or cross-version speedup.')
(folder/'display-timing-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['desktop_pipeline_enabled','desktop_stats','cache_submit_us_per_frame','gpu_frequency','async_gpu','fast_path','android_return','whole_test_result']},indent=2))
