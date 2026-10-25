"""Summarize bounded input traces without changing hardware verdicts.

This reports delivery observations, not proof that physical interaction works.
User feedback belongs in a separate user-interaction.json record.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import re
import statistics

parser = argparse.ArgumentParser()
parser.add_argument('evidence', type=Path)
args = parser.parse_args()
raw = (args.evidence / 'checkpoint-63.log').read_bytes()
log = raw.decode(errors='replace')
lines = log.splitlines()

def records(marker):
    return [dict(re.findall(r'(\w+)=([^ ]+)', line))
            for line in lines if line.startswith(marker + ' ')]

def distribution(values):
    if not values:
        return dict(count=0)
    values = sorted(values)
    return dict(count=len(values), min=values[0], median=statistics.median(values),
                p95=values[min(len(values)-1, int(len(values)*0.95))], max=values[-1])

samples = records('LMI_INPUT_SAMPLE')
observed = records('LMI_HID_OBSERVED')
posted = {int(x['posted_us']) for x in samples}
matched = [x for x in observed if int(x['posted_us']) in posted]
windows = list(dict.fromkeys(re.findall(
    r'MiniIOMobileFramebuffer: (\d+) frames in (\d+) ms \((\d+) a second\), '
    r'(\d+) us each in the driver, after (\d+) us waiting for the GPU', log)))
hardware = json.loads((args.evidence / 'hardware-test.json').read_text())
result = dict(
    log_sha256=hashlib.sha256(raw).hexdigest(),
    sample_count=len(samples),
    routes=dict(collections.Counter(x['route'] for x in samples)),
    accepted=dict(collections.Counter(x['accepted'] for x in samples)),
    phases=dict(collections.Counter(x['type'] for x in samples)),
    post_to_read_us=distribution([int(x['read_us'])-int(x['posted_us']) for x in samples]),
    post_to_sent_us=distribution([int(x['sent_us'])-int(x['posted_us']) for x in samples]),
    hid_observer_records=len(observed),
    matched_original_timestamps=len(matched),
    post_to_hid_monitor_us=distribution([int(x['observed_us'])-int(x['posted_us']) for x in matched]),
    uikit_hooks=[x for x in lines if x.startswith('LMI_UIKIT_INPUT_HOOK ')],
    uikit_input_records=sum(x.startswith('LMI_UIKIT_INPUT stage=') for x in lines),
    backboard_hooks=[x for x in lines if x.startswith('LMI_BK_HOOK ')],
    backboard_process_records=records('LMI_BK_PROCESS'),
    backboard_service_records=records('LMI_BK_SERVICE'),
    backboard_service_info_records=[x for x in lines if x.startswith('LMI_BK_SERVICE_INFO ')],
    hid_usage_recheck_records=[x for x in lines if x.startswith('LMI_HID_USAGE_RECHECK ')],
    backboard_state_records=[x for x in lines if x.startswith('LMI_BK_STATE ')],
    backboard_touching_records=sum(x.startswith('LMI_BK_STATE ') and
                                  ('presence: touching' in x or '; touching;' in x) for x in lines),
    ignored_touch_records=[x for x in lines if 'ignoring touch event' in x],
    digitizer_state_records=[x for x in lines if 'UISensor mode changing' in x],
    display_windows=[dict(frames=int(f),window_ms=int(ms),window_fps=int(hz),
                          driver_us=int(d),gpu_wait_us=int(g)) for f,ms,hz,d,g in windows],
    raw_hardware_result=hardware.get('result'),
    android_return=hardware.get('android_return'),
    scope='Monitor delivery and API acceptance do not prove UI interaction. '
          'Five-second display windows include idle periods and are not continuous-animation FPS. '
          'A missing UIKit hook log does not establish where delivery stopped.',
)
target = args.evidence / 'touch-log-analysis.json'
target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
print(json.dumps({key: result[key] for key in [
    'sample_count', 'accepted', 'matched_original_timestamps', 'post_to_hid_monitor_us',
    'uikit_hooks', 'uikit_input_records', 'backboard_hooks',
    'backboard_touching_records', 'raw_hardware_result']}, indent=2))
print(target)
