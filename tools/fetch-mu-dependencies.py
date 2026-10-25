"""Fetch pinned Mu Git objects using Windows Git, for local WSL import."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import configparser
import subprocess

root = Path(__file__).resolve().parents[1]
source = root / 'Mu-Silicium-base'
cache = root / 'dependency-cache'
cache.mkdir(exist_ok=True)
entries = [
    ('Common/Mu', 'https://github.com/microsoft/mu_plus.git'),
    ('Common/Mu_OEM_Sample', 'https://github.com/microsoft/mu_oem_sample.git'),
    ('Mu_Basecore', 'https://github.com/microsoft/mu_basecore.git'),
    ('Silicium-ACPI', 'https://github.com/Project-Silicium/Silicium-ACPI.git'),
    ('Silicon/Silicium/OpensslPkg/Library/OpensslLib/openssl', 'https://github.com/openssl/openssl.git'),
]

def fetch(entry):
    path, url = entry
    line = subprocess.check_output(['git', '-C', str(source), 'ls-tree', 'HEAD', path], text=True)
    commit = line.split()[2]
    dest = cache / path.replace('/', '__')
    with (cache / (dest.name + '.log')).open('w') as log:
        if not dest.exists():
            subprocess.run(['git', 'init', '--bare', str(dest)], stdout=log, stderr=log, check=True)
        cmd = ['git', '-C', str(dest), '-c', 'http.version=HTTP/1.1',
               '-c', 'http.lowSpeedLimit=1000', '-c', 'http.lowSpeedTime=30',
               'fetch', '--depth=1', url, commit]
        subprocess.run(cmd, stdout=log, stderr=log, check=True)
        subprocess.run(['git', '-C', str(dest), 'update-ref', 'refs/heads/pinned', commit], check=True)
        subprocess.run(['git', '-C', str(dest), 'symbolic-ref', 'HEAD', 'refs/heads/pinned'], check=True)
    print(f'Fetched {path} {commit}', flush=True)
    return dict(path=path, url=url, commit=commit, cache=dest.name)

def fetch_nested(item):
    parent = cache / item['parent_cache']
    line = subprocess.check_output(['git', '-C', str(parent), 'ls-tree', 'HEAD', item['relative']], text=True)
    commit = line.split()[2]
    dest = cache / item['path'].replace('/', '__')
    with (cache / (dest.name + '.log')).open('w') as log:
        if not dest.exists():
            subprocess.run(['git', 'init', '--bare', str(dest)], stdout=log, stderr=log, check=True)
        subprocess.run(['git', '-C', str(dest), '-c', 'http.version=HTTP/1.1',
                        '-c', 'http.lowSpeedLimit=1000', '-c', 'http.lowSpeedTime=30',
                        'fetch', '--depth=1', item['url'], commit], stdout=log, stderr=log, check=True)
        subprocess.run(['git', '-C', str(dest), 'update-ref', 'refs/heads/pinned', commit], check=True)
        subprocess.run(['git', '-C', str(dest), 'symbolic-ref', 'HEAD', 'refs/heads/pinned'], check=True)
    print(f"Fetched nested {item['path']} {commit}", flush=True)
    return dict(item, commit=commit, cache=dest.name)

manifest = cache / 'manifest.json'
if manifest.exists():
    results = [r for r in json.loads(manifest.read_text()) if 'relative' not in r]
else:
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, entries))
# Basecore's vendored library source is required by its package graph. OpenSSL
# test/interop submodules are not part of the firmware build and are excluded.
base = next(r for r in results if r['path'] == 'Mu_Basecore')
modules = subprocess.check_output(['git', '-C', str(cache/base['cache']), 'show', 'HEAD:.gitmodules'], text=True)
config = configparser.ConfigParser()
config.read_string(modules)
nested = [dict(path='Mu_Basecore/'+config[s]['path'], relative=config[s]['path'],
               parent_cache=base['cache'], parent_path='Mu_Basecore',
               url=config[s]['url']) for s in config.sections()]
with ThreadPoolExecutor(max_workers=4) as pool:
    results.extend(pool.map(fetch_nested, nested))
(cache / 'manifest.json').write_text(json.dumps(results, indent=2))
