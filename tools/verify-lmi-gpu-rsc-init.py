"""Verify actual mode22 programming AND restoration, not GPU execution."""
import re
OFFSETS=[0x10,0x2c,0x38,0x34,0x40,0x3c,0x48,0x44,0x400,0x20,0x24,0x28,
         0x600,0x604,0x608,0x60c,0x610,0x4520,0x4500]
EXPECTED=[0,1,0,0x82204514,0,0x82204510,0,0x82204520,0,0x4520,0x4510,0x4514,
          0,0,0,0,0,0,0x100]
REQUESTED=[0x1000000,1,0,0,0,0,0x80000000,0,0,0x4520,0x4510,0x4514,
           0xeaaae5a0,0xe1a1ebab,0xa2e0a581,0xecac82e2,0x20edad,0,0x80000001]

def decode(log,sequence_only=False,pdc_enable=False,vote_probe=False,clock_probe=False,route_probe=False,active=False):
    assert not pdc_enable or sequence_only, 'PDC probe requires sequence profile'
    assert not vote_probe or pdc_enable, 'Held vote probe requires PDC profile'
    assert not clock_probe or vote_probe, 'Clock probe requires confirmed vote profile'
    assert not route_probe or clock_probe, 'Route probe requires 200MHz profile'
    assert not active or route_probe
    if route_probe and not active:
        assert re.search(r'LMI_GPU_GMU_ROUTE_RESULT\n0000000000000001\n',log)
        assert 'LMI_GPU_GMU_ROUTE_DETACH_OK\n' in log and 'LMI_GPU_RAM_CLEANUP_DONE\n' in log
    if vote_probe:
        assert log.count('LMI_GPU_RSC_PDC_READY\n')==1
        assert log.index('LMI_GPU_RSC_INIT_ACTUAL\n')<log.index('LMI_GPU_RSC_PDC_READY\n')<log.index('LMI_GPU_RPMH_REQUEST_ADDRESS\n')
        assert re.search(r'LMI_GPU_RPMH_RESULT\n0000000000000001\n',log), 'Held RPMh votes incomplete'
        requests=re.findall(r'LMI_GPU_RPMH_REQUEST_ADDRESS\n([0-9a-f]{16})\nLMI_GPU_RPMH_REQUEST_SELECTOR\n([0-9a-f]{16})\n',log)
        assert [(int(a,16),int(v,16)) for a,v in requests]==[(0x30010,2),(0x30000,2)]
        statuses=[int(v,16) for v in re.findall(r'LMI_GPU_RPMH_COMMAND_STATUS\n([0-9a-f]{16})\n',log)]
        assert len(statuses)==2 and all(v&0x10100==0x10100 for v in statuses)
        assert re.search(r'LMI_GPU_RPMH_TCS_SLOT\n0000000000000001\n',log)
        assert 'LMI_GPU_RPMH_KEEP_CLOCKS_UNTIL_RESET\n' not in log
    if clock_probe and not active:
        assert re.search(r'LMI_GPU_GMU_200MHZ_RESULT\n0000000000000001\n',log)
        assert log.count('LMI_GPU_GMU_200MHZ_RESTORE_OK\n')==1
        assert log.rindex('LMI_GPU_RPMH_COMMAND_STATUS\n')<log.index('LMI_GPU_GMU_200MHZ_SOURCE\n')<log.index('LMI_GPU_RSC_INIT_RESTORED\n')
    result=re.search(r'LMI_GPU_RSC_INIT_RESULT\n([0-9a-f]{16})\n',log)
    assert result, 'Missing RSC/PDC result'
    assert log.count('LMI_GPU_RSC_INIT_BEGIN\n')==1
    assert log.count('LMI_GPU_RSC_INIT_RESTORE_OK\n')==(0 if active else 1)
    if active:assert 'LMI_GPU_RSC_INIT_RESTORED' not in log
    rows={}
    addresses=[(0x3de0000 if i<17 else 0xb290000)+off for i,off in enumerate(OFFSETS)]
    for marker in (['BEFORE','ACTUAL'] if active else ['BEFORE','ACTUAL','RESTORED']):
        match=re.search('LMI_GPU_RSC_INIT_'+marker+r'\n((?:[0-9a-f]{16}\n){19})',log)
        assert match, 'Incomplete RSC/PDC '+marker
        pairs=[int(v,16) for v in match[1].splitlines()]
        assert [v>>32 for v in pairs]==addresses
        rows[marker]=[v&0xffffffff for v in pairs]
    targets=EXPECTED.copy() if sequence_only else REQUESTED.copy()
    if sequence_only:
        for i in [0,12,13,14,15,16]:targets[i]=REQUESTED[i]
    if pdc_enable:
        for i in [17,18]:targets[i]=REQUESTED[i]
    different=[i for i,(actual,target) in enumerate(zip(rows['ACTUAL'],targets)) if actual!=target]
    return dict(mode=28 if active else 27 if route_probe else 26 if clock_probe else 25 if vote_probe else 24 if pdc_enable else 23 if sequence_only else 22,result=int(result[1],16),addresses=[hex(a) for a in addresses],registers=rows,
                original_matches_cold_census=rows['BEFORE']==EXPECTED,
                first_unmatched_target_address=hex(addresses[different[0]]) if different else None,
                vendor_program_readback_verified=rows['ACTUAL']==targets,
                exact_restore_verified=not active and rows['RESTORED']==rows['BEFORE'],dependencies_retained_active=active,
                rpmh_requests=vote_probe,firmware_execution=active,hardware_acceleration_verified=False)

def verify(log,sequence_only=False,pdc_enable=False,vote_probe=False,clock_probe=False,route_probe=False,active=False):
    result=decode(log,sequence_only=sequence_only,pdc_enable=pdc_enable,vote_probe=vote_probe,clock_probe=clock_probe,route_probe=route_probe,active=active)
    assert result['result']==(3 if active else 1) and result['vendor_program_readback_verified'], 'RSC/PDC programming/restoration not successful'
    assert result['original_matches_cold_census']
    assert active or result['exact_restore_verified'], 'RSC/PDC original state not restored'
    return result
