"""Reconstruct the bounded BLIT from pinned Mesa24.3 primary definitions."""
from pathlib import Path
import hashlib,json,re,runpy,xml.etree.ElementTree as ET

r=Path(__file__).resolve().parents[1]
d=r/'out/lmi-gpu-research/rsc-register-source'
hashes={
    'fd6_blitter.cc':'9aab3aebed3026e962d5bde32962bab4eabb16a4f44acb56d5b9cefc59e4e667',
    'a6xx.xml':'543f6843c0b90f61d367b2cd96863569b01d524e1238c82357bd206ec612603b',
    'fd6_emit.cc':'ef458f912d8c6770840655b8a9460f8af5d3c0b2a736aa69fd45da7ebbc9d2eb',
    'freedreno_devices.py':'53921eeab755eff5f197ad5685895c294f94ea90af7baebf50469bcd1022a89d',
    'adreno_pm4.xml':'3d96f39a6beef90e74325c827e41e0e165ee3eaf9737f94fcbdb75a2e4011f1c',
    'fd6_emit.h':'53ec058d596bfda8d5d9be679ed79914f36feb591c699a6b8a2f7b7e0d1a7af2',
    'fd6_screen.cc':'1e7d742a3288593d8e75763dc775874a93d987c8c0293230080f0143d21ffe28',
    'freedreno_gpu_event.h':'71c7761089ae66bed28264720ae3716379d60d7d236f987d37eb9f8c6d27b1ad',
    'fd6_format_table.c':'e024ef301b646757e45205fc00440d6ba871284f7fa6da03f35c95413276b702',
    'adreno_common.xml':'c733db8294d0bedc6191044b7a6acfc81495ba1f294c3108746999c596cf5e58',
}
sources={}
for name,sha in hashes.items():
    p=d/('mesa-24.3.0-'+name);assert hashlib.sha256(p.read_bytes()).hexdigest()==sha,name
    sources[name]=p.read_text()
def xml(name):
    tree=ET.fromstring(sources[name])
    for node in tree.iter():node.tag=node.tag.split('}')[-1]
    return tree
x=xml('a6xx.xml');pm=xml('adreno_pm4.xml');common=xml('adreno_common.xml')
def named(tree,tag,name):
    return next(e for e in tree.iter(tag) if e.get('name')==name)
def value(tree,name):return int(named(tree,'value',name).get('value'),0)
def reg(name):return int(named(x,'reg32',name).get('offset'),0)
def field(container,name,v):
    f=named(container,'bitfield',name);lo=int(f.get('pos',f.get('low','0')));hi=int(f.get('pos',f.get('high',str(lo))))
    shift=int(f.get('shr','0'));assert v%(1<<shift)==0 and v>>shift < 1<<(hi-lo+1)
    return (v>>shift)<<lo
fmt=value(x,'FMT6_8_8_8_8_UNORM');swap=value(common,'WXYZ');ifmt=value(x,'R2D_UNORM8')
assert (fmt,swap,ifmt)==(0x30,1,0x10)
assert re.search(r'VTC\(B8G8R8A8_UNORM,\s+8_8_8_8_UNORM,\s+WXYZ\)',sources['fd6_format_table.c'])
blit=named(x,'bitset','a6xx_2d_blit_cntl')
control=field(blit,'SOLID_COLOR',1)|field(blit,'COLOR_FORMAT',fmt)|field(blit,'MASK',15)|field(blit,'IFMT',ifmt)
setup=sources['fd6_blitter.cc'].split('uint32_t blit_cntl =',1)[1].split('OUT_PKT4',1)[0]
assert 'NORM' not in setup and 'IFMT(ifmt)' in setup and 'SOLID_COLOR' in setup
assert 'float_to_ubyte(color->f[0])' in sources['fd6_blitter.cc']
dev=sources['freedreno_devices.py'];a650=dev.split('GPUId(650)',1)[1].split('add_gpus(',1)[0]
assert 'num_ccu = 3' in a650 and 'RB_DBG_ECO_CNTL_blit = 0x04100000' in a650
assert 'sysmem_per_ccu_depth_cache_size = 64 * 1024' in dev
assert 'sysmem->color_ccu_offset = sysmem->depth_ccu_offset + depth_cache_size;' in sources['fd6_screen.cc']
ccu=field(named(x,'reg32','RB_CCU_CNTL'),'COLOR_OFFSET',3*64*1024)
assert ccu==0x18000000
events=sources['freedreno_gpu_event.h'].split('fd_gpu_events<A6XX>',1)[1].split('template <>',1)[0]
assert '{CACHE_FLUSH_TS, true}' in events and '{PC_CCU_FLUSH_COLOR_TS, true}' in events
assert 'COND(info.needs_seqno, CP_EVENT_WRITE_0_TIMESTAMP)' in sources['fd6_emit.h']
event=named(pm,'domain','CP_EVENT_WRITE');seq=field(event,'TIMESTAMP',1)
assert seq==1<<30 and field(event,'IRQ',1)==1<<31
# Mesa's bit30 requests a timestamp (confirmed by the first real tile test).
# The Linux submit fence uses the payload sequence with bit30 clear. IRQ is
# independently optional; leave it clear for this polling-only transaction.
linux=r/'out/lmi-gpu-research/rsc-register-source/linux-v6.12-a6xx_gpu.c'
assert hashlib.sha256(linux.read_bytes()).hexdigest()=='c33479377574ed193e82c272b3708e19a2b2153088f246e2639d8a43fef943a2'
linux_fence=linux.read_text().split('OUT_PKT7(ring, CP_EVENT_WRITE, 4);',1)[1].split('trace_msm_gpu_submit_flush',1)[0]
assert 'CP_EVENT_WRITE_0_IRQ' in linux_fence and 'TIMESTAMP' not in linux_fence and 'submit->seqno' in linux_fence
assert 'when set, write back timestamp instead of value from packet' in sources['adreno_pm4.xml']
seq=0
def parity(v):return 1^(v.bit_count()&1)
def p4(address,*values):return [(4<<28)|(parity(address)<<27)|(address<<8)|(parity(len(values))<<7)|len(values),*values]
def p7(op,*values):return [(7<<28)|(parity(op)<<23)|(op<<16)|(parity(len(values))<<15)|len(values),*values]
def pkt(name,*v):return p7(value(pm,name),*v)
assert value(pm,'RM6_BLIT2DSCALE')==12
expected=[*pkt('CP_SET_MARKER',12),*pkt('CP_WAIT_FOR_IDLE'),*p4(reg('RB_CCU_CNTL'),ccu),
    *p4(reg('GRAS_2D_DST_TL'),0,15|(15<<16)),*p4(reg('RB_2D_SRC_SOLID_C0'),0x33,0x66,0xcc,0xff),
    *p4(reg('RB_2D_BLIT_CNTL'),control),*p4(reg('GRAS_2D_BLIT_CNTL'),control),
    *p4(reg('SP_2D_DST_FORMAT'),(15<<12)|(fmt<<3)),*p4(reg('RB_2D_UNKNOWN_8C01'),0),
    *p4(reg('RB_2D_DST_INFO'),fmt|(swap<<10),0x1010100,0,1),
    *pkt('CP_WAIT_FOR_IDLE'),*p4(reg('RB_DBG_ECO_CNTL'),0x04100000),*pkt('CP_BLIT',value(pm,'BLIT_OP_SCALE')),
    *pkt('CP_WAIT_FOR_IDLE'),*p4(reg('RB_DBG_ECO_CNTL'),0),
    *pkt('CP_EVENT_WRITE',seq|value(pm,'PC_CCU_FLUSH_COLOR_TS'),0x1010008,0,0x650c0101),
    *pkt('CP_EVENT_WRITE',seq|value(pm,'CACHE_FLUSH_TS'),0x101000c,0,0x650c0102),
    *pkt('CP_WAIT_FOR_IDLE'),*pkt('CP_MEM_WRITE',0x1010010,0,0x650c0de3)]
src=(r/'tools/lmi-gpu-tile.c').read_text()
actual=[int(v.strip(),0) for v in re.search(r'commands\[\].*?=\{(.*?)\};',src,re.S)[1].split(',')]
assert actual==expected==runpy.run_path(str(r/'tools/verify-lmi-gpu-tile.py'))['COMMANDS'] and len(expected)==49
assert len(re.findall(r'rsc_write\(',src))==2 # prototype plus only WPTR submission
report=dict(result='PASS',mesa_version='24.3.0',primary_sha256=hashes,packet=[f'{v:08x}' for v in expected],
    gpu_tile_source_sha256=hashlib.sha256((r/'tools/lmi-gpu-tile.c').read_bytes()).hexdigest(),
    verifier_sha256=hashlib.sha256((r/'tools/verify-lmi-gpu-tile.py').read_bytes()).hexdigest(),
    event_policy='Linux payload sequence fence: bit30 timestamp clear, payload4; no IRQ bit31; exact writeback must be observed',
    linux_fence_source_sha256=hashlib.sha256(linux.read_bytes()).hexdigest(),
    normal_field='No NORM field in this version; use explicit UNORM8 IFMT, matching Mesa setup',
    tile_iova='0x1010100',tile_bytes=1024,existing_owned_mapping_only=True,hardware_verified=False)
(r/'out/lmi-gpu-research/mode46-tile-source-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: pinned Mesa A650 CCU, BGRA swap, IFMT, events and all49 packet words')
