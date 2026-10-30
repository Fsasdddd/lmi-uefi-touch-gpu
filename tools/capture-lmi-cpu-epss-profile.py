"""Read-only board evidence for an EPSS implementation; never writes sysfs/MMIO."""
from pathlib import Path
import argparse, datetime, hashlib, json, re, struct, subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fdt(raw):
    magic, total, a, b, _, _, _, _, n, size = struct.unpack_from('>10I', raw)
    assert magic == 0xd00dfeed and total <= len(raw)
    names = raw[b:b+n]; nodes = {}; stack = []; pos = a
    while pos < a+size:
        token, = struct.unpack_from('>I', raw, pos); pos += 4
        if token == 1:
            end = raw.index(0, pos); stack.append(raw[pos:end].decode())
            pos = (end+4)&~3; nodes['/'+'/'.join(stack[1:])] = {}
        elif token == 2: stack.pop()
        elif token == 3:
            length, offset = struct.unpack_from('>II', raw, pos); pos += 8
            name = names[offset:names.index(0, offset)].decode()
            nodes['/'+'/'.join(stack[1:])][name] = raw[pos:pos+length]
            pos = (pos+length+3)&~3
        elif token == 4: continue
        elif token == 9: break
        else: raise AssertionError(token)
    return nodes


def capture(attempt):
    assert re.fullmatch('[a-z]', attempt)
    out = ROOT/('out/lmi-cpu-epss/board-profile-'+attempt)
    assert not out.exists(); out.mkdir(parents=True)
    script = '''getprop sys.boot_completed
for p in /sys/devices/system/cpu/cpufreq/policy*; do
 echo POLICY=$p
 for n in related_cpus cpuinfo_min_freq cpuinfo_max_freq scaling_available_frequencies scaling_min_freq scaling_max_freq scaling_cur_freq cpuinfo_cur_freq; do
  if [ -r $p/$n ]; then echo NAME=$n; cat $p/$n; fi
 done
done
exit 0
'''
    cmd = ['D:/Gaoji/adb.exe', '-s', 'YOUR_ADB_SERIAL', 'shell', script]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=18)
    (out/'android-cpufreq.txt').write_text(result.stdout)
    (out/'android-cpufreq-stderr.txt').write_text(result.stderr)
    assert result.returncode == 0 and result.stdout.splitlines()[0].strip() == '1'
    policies = {}; current = None; name = None
    for line in result.stdout.splitlines()[1:]:
        if line.startswith('POLICY='):
            current = {}; policies[line[7:]] = current
        elif line.startswith('NAME='): name = line[5:]
        elif line.strip() and current is not None:
            current[name] = [int(n) for n in line.split()]
    assert [p['related_cpus'] for p in policies.values()] == [[0,1,2,3],[4,5,6],[7]]
    dtb = ROOT/'device-info/live.dtb'; nodes = fdt(dtb.read_bytes())
    cells = lambda v: list(struct.unpack('>'+str(len(v)//4)+'I', v))
    ctrl = nodes['/soc/qcom,cpufreq-hw']
    cpus = {path: dict(reg=cells(p['reg']), frequency_domain=cells(p['qcom,freq-domain']))
            for path,p in nodes.items() if re.fullmatch('/cpus/cpu@[0-9a-f]+',path)}
    assert len(cpus) == 8
    assert [p['frequency_domain'] for p in cpus.values()] == [[4,i,4] for i in [0,0,0,0,1,1,1,2]]
    assert cells(ctrl['reg']) == [0x18591000,0x1000,0x18592000,0x1000,0x18593000,0x1000]
    assert cells(ctrl['qcom,lut-row-size']) == [4] and 'qcom,skip-enable-check' in ctrl
    phandles = {cells(p['phandle'])[0]: dict(path=path,properties={k:v.hex() for k,v in p.items()})
                for path,p in nodes.items() if 'phandle' in p}
    report = dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        read_only=True, android_boot_completed=True, cpu_policies=policies, cpus=cpus,
        epss_properties={k:v.hex() for k,v in ctrl.items()},
        clock_controllers={str(i):phandles[i] for i in [0x15,0x16]},
        xo_board={k:v.hex() for k,v in nodes['/soc/clocks/xo-board'].items()},
        note='Android policy requests are not a measurement of XNU CPU frequency. DT max_cores is 4 for all three domains.',
        inputs={dtb.relative_to(ROOT).as_posix():sha(dtb),Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__))})
    (out/'profile.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Captured board profile, 8 CPUs / 3 domains; read-only.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--attempt',default='a')
    capture(parser.parse_args().attempt)
