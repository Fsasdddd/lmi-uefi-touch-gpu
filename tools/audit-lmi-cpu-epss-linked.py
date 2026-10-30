"""Independent recompilation/link and boundary review of the v77 RAM kernel."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,struct
from importlib.machinery import SourceFileLoader
ROOT=Path(__file__).resolve().parents[1]
elf=SourceFileLoader('v73_elf_reader',str(ROOT/'tools/build-lmi-display-timing-v73.py')).load_module().elf
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='a');args=parser.parse_args();assert re.fullmatch('[a-z]',args.attempt)
folder=ROOT/'out/lmi-cpu-epss-v77e';out=ROOT/('out/lmi-cpu-epss/link-'+args.attempt)
assert not out.exists();out.mkdir()
audit=json.loads((folder/'build-audit.json').read_text())
for name,digest in audit['inputs'].items():assert sha(ROOT/name)==digest,name
for name in ['lmi-cpu-epss','lmi-cpu-epss-native']:
    subprocess.run(['clang',*audit['compile_flags'],'-c',str(ROOT/'tools'/(name+'.c')),'-o',str(out/(name+'.o'))],check=True)
    assert (out/(name+'.o')).read_bytes()==(folder/(name+'.o')).read_bytes()
(out/'epss.ld').write_bytes((folder/'epss.ld').read_bytes())
subprocess.run(['ld.lld','-T','epss.ld','--entry=lmi_epss_native_init','lmi-cpu-epss.o','lmi-cpu-epss-native.o',
    *[f'--defsym={n}={v}' for n,v in audit['bindings'].items()],'-o','epss.elf'],cwd=out,check=True)
assert (out/'epss.elf').read_bytes()==(folder/'epss.elf').read_bytes()
assert not subprocess.check_output(['llvm-nm','-u',str(out/'epss.elf')],text=True).strip()
raw=(folder/'mach.development.bcm2837').read_bytes()
original=(ROOT/'out/lmi-display-timing-v73/mach.development.bcm2837').read_bytes();base=0xfffffff007004000
restored=bytearray(raw)
for a,z in audit['allowed_file_ranges']:restored[a:z]=original[a:z]
assert restored==original and len(raw)==len(original)
for name,(h,data) in elf(out/'epss.elf').items():
    assert h[1]==1 and not h[2]&1
    assert raw[h[3]-base:h[3]-base+len(data)]==data
native=json.loads((ROOT/'out/lmi-cpu-epss/native-e/result.json').read_text())
assert native['result']=='PASS' and native['scenarios']==13 and native['kernel_sha256']==audit['sha256']
inventory_path=ROOT/'out/lmi-cpu-epss/space-a/reference-inventory.json'
inventory=json.loads(inventory_path.read_text())
assert len(inventory['external_direct_calls'])==2 and not inventory['external_exact_address_references'] and not inventory['loaded_pointers'] and not inventory['neighboring_code_page_references']
# Every reference to this BSS page outside the replaced unit was decoded and
# inventoried. The adjacent Apple80211 data ends below 0x840 and GPU starts at
# 0x950. No external ADRP consumer addresses the 0x850 eight-byte CPU slot.
for row in inventory['state_page_references']:
    assert not any('#0x850' in line for line in row['context'])
pos=32;state_symbol_literals=[]
for _ in range(struct.unpack_from('<I',original,16)[0]):
    cmd,size=struct.unpack_from('<II',original,pos)
    if cmd==25:
        name=original[pos+8:pos+24].rstrip(b'\0').decode();va,vs,fo,fs=struct.unpack_from('<QQQQ',original,pos+24)
        found=struct.pack('<Q',0xfffffff007e98850) in original[fo:fo+fs]
        if found:
            assert name in ['__LINKEDIT','__LINKINFO'],name
            state_symbol_literals.append(name)
    pos+=size
# Current checkpoint63 bypasses native loader_return cleanup. Verify the live
# chain to the *wrapped* display cleanup, instead of relying on dead native BL.
word=lambda pc:struct.unpack_from('<I',raw,pc-base)[0]
def branch(pc,opcode,target):
    w=word(pc);v=w&0x3ffffff
    assert w&0xfc000000==opcode and pc+4*(v-(1<<26) if v&(1<<25) else v)==target
branch(0xfffffff007472364,0x14000000,0xfffffff00745a800)
branch(0xfffffff007460cd0,0x94000000,0xfffffff0074d2494)
branch(0xfffffff0074d24a0,0x94000000,int(next(r for r in audit['hooks'] if r['symbol']=='lmi_epss_native_cleanup')['target'],16))
for start,end in [(0xfffffff00745a818,0xfffffff00745a964),(0xfffffff0079e59e4,0xfffffff0079e5b00)]:
    assert raw[start-base:end-base]==original[start-base:end-base]
paths=[Path(__file__),folder/'build-audit.json',folder/'mach.development.bcm2837',folder/'epss.elf',
       ROOT/'out/lmi-cpu-epss/native-e/result.json',ROOT/'out/lmi-cpu-epss/host-c/result.json',inventory_path,
       ROOT/'tools/lmi-smp-return.S',ROOT/'tools/lmi-display-timing-v73.c',ROOT/'tools/lmi-display-native-v56.c']
report=dict(result='PASS',kernel_sha256=audit['sha256'],objects_reproduced=True,link_reproduced=True,
    no_unresolved_symbols=True,no_new_writable_globals=True,placed_bytes_verified=True,
    outside_cpu_and_one_cleanup_call_exact=True,live_checkpoint63_cleanup_verified=True,
    unchanged_smp_off_guard=True,original_native_gpu_wait_200us_exact=True,
    state_pointer_exclusive_after_replacement=True,state_symbol_literals_only=state_symbol_literals,
    original_display_cleanup_required_before_cpu_restore=True,
    hardware_tested=False,performance_verified=False,measured_cpu_frequency=None,
    limitations='Host instruction/reference review; no real firmware, hardware fault or thermal behavior proven. CPU requests are not CPU frequency measurements.',
    inputs={p.relative_to(ROOT).as_posix():sha(p) for p in paths})
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: independent objects/link/placement and actual checkpoint63 return chain; original 200us wait retained')
