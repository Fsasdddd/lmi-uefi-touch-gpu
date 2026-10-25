"""Decode the finite mode21 census; values are observations, not readiness proof."""
import re

BANKS = [
    (0x3d90000, [0x1000,0x1004,0x1068,0x1078,0x1088,0x108c,0x1090,
                 0x1098,0x109c,0x111c,0x1120,0x1124,0x1540]),
    (0x3d6a000, [0x14000,0x14070,0x143a0,0x143b0,0x24c1c,0x24c20]),
    (0x3de0000, [0xc,0x10,0x20,0x24,0x28,0x2c,0x34,0x38,0x3c,0x40,
                 0x44,0x48,0x400,0x404,0x600,0x604,0x608,0x60c,0x610]),
    (0xb290000, [0x4500,0x4520]),
    (0xc300000, list(range(0,64,4))),
]

def verify(log):
    assert log.count('LMI_GPU_RSC_STATE_BEGIN\n') == 1
    assert log.count('LMI_GPU_RSC_STATE_OK\n') == 1
    assert 'LMI_GPU_RSC_STATE_RESET_REFUSED' not in log
    assert 'LMI_GPU_RSC_STATE_MAP_FAILED' not in log
    chunk = log.split('LMI_GPU_RSC_STATE_BEGIN\n')[1].split('LMI_GPU_RSC_STATE_OK\n')[0]
    pairs = [(int(a,16),int(v,16)) for a,v in re.findall(
        r'LMI_GPU_RSC_STATE_ADDRESS\n([0-9a-f]{16})\nLMI_GPU_RSC_STATE_VALUE\n([0-9a-f]{16})\n',chunk)]
    assert [a for a,v in pairs] == [base+off for base,offs in BANKS for off in offs], 'RSC state census missing/reordered addresses'
    assert all(v <= 0xffffffff for a,v in pairs), 'Invalid 32-bit MMIO result'
    banks = [int(v,16) for v in re.findall(r'LMI_GPU_RSC_STATE_BANK\n([0-9a-f]{16})\n',chunk)]
    assert banks == [base for base,offs in BANKS], 'RSC bank map evidence missing'
    regs = dict(pairs)
    assert regs[0x3d7e000] == 1 and regs[0x3d7e070] == 0, 'Firmware not held in pre-init reset'
    assert regs[0x3de000c] == 0x4000000a, 'Unexpected RSC layout'
    sequence = [regs[0x3de0600+4*i] for i in range(5)]
    expected = [0xeaaae5a0,0xe1a1ebab,0xa2e0a581,0xecac82e2,0x20edad]
    qmp = [regs[0xc300000+4*i] for i in range(16)]
    channels = {}
    for name,start in [('ucore',3),('mcore',9)]:
        channel = dict(zip(['link_state','link_state_ack','ch_state','ch_state_ack',
                            'mailbox_size','mailbox_offset'],qmp[start:start+6]))
        size,offset = channel['mailbox_size'],channel['mailbox_offset']
        channel['mailbox_within_dt_resource'] = 64 <= offset <= 4096 and 0 < size <= 4096-offset
        channel['link_and_channel_up'] = all(channel[k] == 0xffff for k in
            ['link_state','link_state_ack','ch_state','ch_state_ack'])
        channels[name] = channel
    return dict(mode=21,registers={hex(a):hex(v) for a,v in pairs},
        rsc_sequence_matches_vendor=sequence==expected,
        rsc_sequence=[hex(v) for v in sequence],
        pdc_enable=hex(regs[0xb294500]),pdc_seq_start=hex(regs[0xb294520]),
        qmp=dict(magic=hex(qmp[0]),version=qmp[1],features=hex(qmp[2]),
                 valid_magic_version=qmp[:2]==[0x4d41494c,1],channels=channels),
        census_writes=False,rpmh_requests=False,qmp_messages=False,
        firmware_execution=False,hardware_acceleration_verified=False)
