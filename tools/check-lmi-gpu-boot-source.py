"""Compare boot addresses with pinned primary driver header and live DT fields."""
from pathlib import Path
import hashlib,re,struct,json
root=Path(__file__).resolve().parents[1]
def check():
    source=root/'out/lmi-gpu-hardware/a6xx_reg.h';raw=source.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='0a1976e256033c1daaf23b7f1a9e3bdaa5c4c1ccc2e8e739496935d0e2fd025a'
    registers={k:int(v,16) for k,v in re.findall(r'^#define A6XX_(\w+)\s+(0x[0-9a-fA-F]+)\s*$',raw.decode(),re.M)}
    header=(root/'tools/lmi-gpu-boot-regs.h').read_text()
    offsets={k:int(v,16) for k,v in re.findall(r'^#define BOOT_(\w+)\s+(0x[0-9a-f]+)u$',header,re.M)}
    assert len(offsets)==29
    dt=(root/'device-info/live.dts').read_text()
    def prop(node,name):
        part=dt.split(node+' {',1)[1]
        text=re.search(re.escape(name)+r' = \[([0-9a-f ]+)\];',part)[1]
        return bytes.fromhex(text)
    gpu=struct.unpack('>I',prop('qcom,kgsl-3d0@3d00000','reg')[:4])[0]
    gmu=struct.unpack('>I',prop('qcom,gmu@3d6a000','reg')[:4])[0]
    assert (gpu,gmu)==(0x3d00000,0x3d6a000)
    assert all(offset==4*registers[name]+gpu-gmu for name,offset in offsets.items()), 'Word-offset address mismatch'
    chip=struct.unpack('>I',prop('qcom,kgsl-3d0@3d00000','qcom,chipid'))[0]
    compressed=(chip&0xffff0000)|(((chip>>8)&255)<<12)|((chip&255)<<8)
    assert chip==0x06050002 and compressed==int(re.search(r'#define LMI_GMU_CHIPID (0x[0-9a-f]+)u',header)[1],16)==0x06050200
    fw=(root/'out/lmi-gpu-hardware/a650_gmu.bin').read_bytes()
    assert hashlib.sha256(fw).hexdigest()=='df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c'
    assert struct.unpack_from('<I',fw,41528)[0]==0x20010008>0x20010004
    driver=(root/'out/lmi-gpu-hardware/adreno_a6xx_gmu.c').read_text()
    assert 'u32 val = 0x00000100;' in driver and 'u32 mask = 0x000001FF;' in driver
    enum=(root/'out/lmi-gpu-research/lmi-vendor/drivers/gpu/msm/kgsl_gmu.h').read_text()
    assert re.search(r'enum gmu_load_mode\s*{\s*CACHED_LOAD_BOOT,\s*CACHED_BOOT,\s*TCM_BOOT,',enum), 'Boot enum differs'
    # Pin both wire ABI and A650-supported version to the same primary sources.
    vendor=root/'out/lmi-gpu-research/lmi-vendor/drivers/gpu/msm'
    for name,digest in [('kgsl_hfi.c','6262de44ecd7647b7eea7ca57e451d15b53c4646812fd20318a5fc0d09ebfde8'),
                        ('kgsl_hfi.h','5aa0338222c0d144d40424f79d6eef207a61148ad7e3e7ac1d7f6b6f9864a6d3'),
                        ('adreno-gpulist.h','29fb16f730c8ebea138b1f66f05096b6e56e74cdb81f17995e13fa0dda647797')]:
        assert hashlib.sha256((vendor/name).read_bytes()).hexdigest()==digest,name
    opp=dt.split('gpu-opp-table_v2 {',1)[1].split('regulator-dbb1 {',1)[0]
    pairs=re.findall(r'opp-hz = \[([0-9a-f ]+)\];\s*opp-microvolt = \[([0-9a-f ]+)\];',opp)
    values=[(int.from_bytes(bytes.fromhex(a),'big')//1000,int.from_bytes(bytes.fromhex(b),'big')) for a,b in pairs]
    assert values==[(670000,320),(587000,256),(525000,224),(490000,192),(441600,144),(400000,128),(305000,64)]
    gpu_node=dt.split('qcom,kgsl-3d0@3d00000 {',1)[1].split('qcom,kgsl-iommu@',1)[0]
    assert 'operating-points-v2 = [00 00 03 3a]' in gpu_node and 'phandle = [00 00 03 3a]' in opp
    bin0=gpu_node.split('qcom,gpu-pwrlevels-0 {',1)[1].split('qcom,gpu-pwrlevels-1 {',1)[0]
    assert 'qcom,speed-bin = [00 00 00 00]' in bin0
    bins=re.findall(r'qcom,gpu-freq = \[([0-9a-f ]+)\];',bin0)
    freqs=[int.from_bytes(bytes.fromhex(v),'big')//1000 for v in bins]
    assert freqs==[v[0] for v in values]+[0]
    qfprom=dt.split('qfprom@780000 {',1)[1].split('refgen-regulator@',1)[0]
    assert 'reg = [00 78 40 00 00 00 30 00]' in qfprom
    assert 'reg = [00 00 01 9b 00 00 00 01]' in qfprom and 'bits = [00 00 00 05 00 00 00 03]' in qfprom
    linux=root/'out/lmi-gpu-research/rsc-register-source/linux-v6.12-a6xx_hfi.c'
    assert hashlib.sha256(linux.read_bytes()).hexdigest()=='f62c802d25475b86ac05cc58df012e088230ed64a0e9319456eb20ebb40c9faa'
    bw=linux.read_text().split('static void a650_build_bw_table',1)[1].split('static void a690_build_bw_table',1)[0]
    for name,value in [('bw_level_num','1'),('ddr_cmds_num','3'),('ddr_wait_bitmask','0x01'),('cnoc_cmds_num','1'),('cnoc_wait_bitmask','0x01')]:
        assert re.search(r'msg->'+name+r'\s*=\s*'+value+r';',bw)
    assert bw.count('0x40000000')==4 and bw.count('0x60000001')==1
    # Nonlegacy A650 OOB protocol and HFI wire shapes, pinned above.
    hfi=(vendor/'kgsl_hfi.h').read_text()
    assert re.search(r'#define H2F_MSG_START\s+10\b',hfi)
    assert re.search(r'#define H2F_MSG_GX_BW_PERF_VOTE\s+30\b',hfi)
    assert re.search(r'struct hfi_start_cmd\s*{\s*uint32_t hdr;\s*};',hfi)
    assert re.search(r'struct hfi_gx_bw_perf_vote_cmd\s*{\s*uint32_t hdr;\s*uint32_t ack_type;\s*uint32_t freq;\s*uint32_t bw;\s*};',hfi)
    assert 'set = BIT(30 - req * 2);' in driver and 'check = BIT(31 - req);' in driver
    core=(vendor/'kgsl_gmu_core.h').read_text()
    assert 'oob_gpu = 0,' in core and '#define INVALID_DCVS_IDX\t0xFF' in core
    user=dt.split('gfx3d_user {',1)[1].split('gfx3d_secure {',1)[0]
    assert 'iommus = [00 00 01 82 00 00 00 00 00 00 04 01]' in user
    sqe=(root/'out/lmi-gpu-hardware/a650_sqe.fw').read_bytes()
    assert len(sqe)==31632 and hashlib.sha256(sqe).hexdigest()=='b4c27420fd6a5c6b511b254cc0fad8cdd40eea38ceb3418f895a1084f4460487'
    cp=(root/'out/lmi-gpu-research/rsc-register-source/linux-v6.12-a6xx_gpu.c').read_bytes()
    assert hashlib.sha256(cp).hexdigest()=='c33479377574ed193e82c272b3708e19a2b2153088f246e2639d8a43fef943a2'
    clock_driver=(root/'out/lmi-gpu-hardware/adreno_a6xx.c').read_bytes()
    assert hashlib.sha256(clock_driver).hexdigest()=='d91a7ed9b511a2143c7cec12a82194d8ef87c9f1a88aa94e55019e8654e3e2ff'
    assert 'A6XX_GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL, 0, 1);' in clock_driver.decode()
    assert 'if (value == 0 && !on)\n\t\treturn;' in clock_driver.decode()
    assert 'if ((!state && !val) || (state && (val == clock_cntl_on)))\n\t\treturn;' in cp.decode()
    assert registers['GPU_GMU_GX_SPTPRAC_CLOCK_CONTROL']==0x1a880
    normal=(root/'tools/lmi-gpu-unsecure.c').read_text()
    normal_words=[int(v,16) for v in re.search(r'diag_words\[\].*?=\{(.*?)\};',normal,re.S)[1].split(',')]
    normal_names=['CP_ADDR_MODE_CNTL','VSC_ADDR_MODE_CNTL','GRAS_ADDR_MODE_CNTL','RB_ADDR_MODE_CNTL',
        'PC_ADDR_MODE_CNTL','HLSQ_ADDR_MODE_CNTL','VFD_ADDR_MODE_CNTL','VPC_ADDR_MODE_CNTL',
        'UCHE_ADDR_MODE_CNTL','SP_ADDR_MODE_CNTL','TPL1_ADDR_MODE_CNTL','RBBM_CLOCK_CNTL',
        'RBBM_CLOCK_CNTL_SP0','RBBM_CLOCK_MODE_HLSQ','RBBM_CLOCK_CNTL_UCHE','RBBM_CLOCK_CNTL_GMU_GX']
    assert normal_words==[registers[name] for name in normal_names]
    address_init=clock_driver.decode().split('static void a6xx_enable_64bit(',1)[1].split('\n}',1)[0]
    for name in normal_names[:11]:
        assert f'kgsl_regwrite(device, A6XX_{name}, 0x1);' in address_init
    assert registers['GPU_GMU_CX_GMU_CX_FAL_INTF']==0x1f8f0
    assert 'A6XX_GPU_GMU_CX_GMU_CX_FAL_INTF, 0x1);' in driver
    cores=(vendor/'adreno-gpulist.h').read_text()
    for name in ['adreno_gpu_core_a650 =','adreno_gpu_core_a650v2 =']:
        assert '.veto_fal10 = true,' in cores.split(name,1)[1].split('\n};',1)[0]
    cc=(root/'out/lmi-gpu-hardware/gpucc-kona.c').read_bytes()
    assert hashlib.sha256(cc).hexdigest()=='a9653a258c24397e366c04bb89c737d392f9cd198a2ba97c26c47a3250673c8a'
    assert '.offset = 0x100,' in cc.decode()
    for value in [0x1008,0x1064,0x1068,0x106c,0x1078,0x1088,0x1098,0x109c,0x10a0,0x111c,0x1120,0x5000]:
        assert hex(value) in cc.decode() or ('03 d9 '+f'{value>>8:02x} {value&255:02x}') in dt,hex(value)
    assert gpu+4*registers['GPU_CC_GX_GDSCR']==0x3d9100c
    assert gpu+4*registers['GPU_CC_GX_DOMAIN_MISC']==0x3d91508
    snapshot=(root/'out/lmi-gpu-research/android-register-access/adreno_a6xx_snapshot.c').read_bytes()
    assert hashlib.sha256(snapshot).hexdigest()=='4d696730c7b80dcd898cf9247319e247b49559dbef31cf62d5862a2b6b8e1467'
    assert 'kgsl_regread(device, A6XX_CP_ROQ_THRESHOLDS_2, &roq_size);' in snapshot.decode()
    pll=(vendor.parents[1]/'clk/qcom/clk-alpha-pll.c').read_bytes()
    assert hashlib.sha256(pll).hexdigest()=='b19e6d1f3a4fffdac8dae3efa470baeb7c080aa61eddbc07f018909e5668b706'
    init=cp.decode().split('static int a6xx_cp_init(',1)[1].split('static int a7xx_cp_init(',1)[0]
    assert 'OUT_PKT7(ring, CP_ME_INIT, 8);' in init and '0x0000002f' in init and '0x20000000' in init
    for name,word in [('CP_ADDR_MODE_CNTL',0x842),('CP_ROQ_THRESHOLDS_2',0x8c2),('CP_ROQ_THRESHOLDS_1',0x8c1),
                      ('CP_MEM_POOL_SIZE',0x8c3),('CP_AHB_CNTL',0x98d),('CP_SQE_INSTR_BASE_LO',0x830),('CP_RB_BASE',0x800)]:
        assert registers[name]==word
    report=dict(result='PASS',register_source_sha256=hashlib.sha256(raw).hexdigest(),offsets={k:hex(v) for k,v in offsets.items()},gpu_base=hex(gpu),gmu_base=hex(gmu),word_origin=hex((gmu-gpu)//4),chipid=hex(compressed),core_version='0x20010008',hardware_verified=False)
    return report
if __name__=='__main__':
    result=check();(root/'out/lmi-gpu-research/gmu-boot-offset-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
