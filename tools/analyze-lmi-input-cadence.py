"""Read saved input timestamps; cadence is separate from touch-to-photon latency."""
from pathlib import Path
import argparse, collections, hashlib, json, math, re, statistics


def distribution(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    return dict(count=len(values), min=values[0], median=statistics.median(values),
                p95=values[math.ceil(len(values)*.95)-1], max=values[-1])


def analyze(raw):
    rows = []
    seen = set()
    for line in raw.decode(errors='replace').splitlines():
        if not line.startswith('LMI_INPUT_SAMPLE '):
            continue
        fields = dict(re.findall(r'(\w+)=([^ ]+)', line))
        if not {'n', 'type', 'finger', 'posted_us', 'read_us', 'sent_us'} <= fields.keys():
            continue
        row = {k: int(fields[k]) for k in ('n', 'type', 'finger', 'posted_us', 'read_us', 'sent_us')}
        key = tuple(row.values())
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    last = {}
    intervals = []
    for row in rows:
        finger = row['finger']
        before = last.get(finger)
        if row['type'] in (2, 3) and before and before['type'] in (1, 2):
            delta = row['posted_us']-before['posted_us']
            if delta > 0:
                intervals.append(delta)
        if row['type'] in (1, 2):
            last[finger] = row
        else:
            last.pop(finger, None)
    cadence = distribution(intervals)
    return dict(log_sha256=hashlib.sha256(raw).hexdigest(), samples=len(rows),
        phases=dict(collections.Counter(r['type'] for r in rows)),
        same_contact_intervals_us=cadence,
        reciprocal_median_samples_per_second=1e6/cadence['median'] if intervals else None,
        post_to_read_us=distribution([r['read_us']-r['posted_us'] for r in rows]),
        post_to_sent_us=distribution([r['sent_us']-r['posted_us'] for r in rows]),
        touch_to_photon_ms=None,
        limitation='Bounded first input records, with exact duplicates removed. Intervals pair consecutive samples of one active contact; they are input cadence, not panel FPS or physical touch-to-photon delay. The physical contact time and panel visibility time are not present.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    output = args.evidence/'input-cadence-analysis.json'
    assert not output.exists(), 'Preserve previous analysis'
    report = analyze((args.evidence/'checkpoint-63.log').read_bytes())
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
