"""Create a guarded, offline patch set for the captured lmi XBL modules.

Every input SHA-256 and instruction/data preimage is checked. Original captures
are never modified. These patches have not been tested on hardware.
"""
from pathlib import Path
import hashlib
import json
import struct

root = Path(__file__).resolve().parents[1]
source = root / 'firmware-extracted/xbl_4/BOOT.XF.3.2-00304-SM8250-2'
out = root / 'out/lmi-firmware-patched'
out.mkdir(parents=True, exist_ok=True)
expected = {
    'ButtonsDxe/ButtonsDxe': '1828c96f5940e2a3ae578517137b1db8569565a1d77094bb85b61acde88550ba',
    'DALSYSDxe/DALSYSDxe': '78090e3da5d3e2f7d17e22912d79263f2f0cc232b19e03e0ab16642a96358d65',
    'TzDxe/TzDxeLA': '24dc99af29ad12fae95fc215840af1044178ab67b0b801621ef4cd112385ef74',
    'UsbConfigDxe/UsbConfigDxe': 'bf0640561b2eca6bccfc5d4d3f17ee2b9c21c2fc1a77530789562c54863ca876',
    'UsbMsdDxe/UsbMsdDxe': 'a6e1e9bd291cd2ed12dd716076f02e36dfbdf57b672917e407ad81f8da8472b5',
}
def sha(data):
    return hashlib.sha256(data).hexdigest()

report = dict(source=str(source), hardware_tested=False, patches=[])
pending_outputs = []
for module, digest in expected.items():
    relative = 'QcomPkg/Drivers/' + module + '.efi'
    raw = (source / relative).read_bytes()
    assert sha(raw) == digest, f'Unsupported input firmware: {module}'
    data = bytearray(raw)
    changes = []
    def edit(offset, before, after, reason):
        before, after = bytes.fromhex(before), bytes.fromhex(after)
        assert len(before) == len(after) and data[offset:offset+len(before)] == before, (module, hex(offset))
        data[offset:offset+len(before)] = after
        changes.append(dict(offset=hex(offset), before=before.hex(), after=after.hex(), reason=reason))
    if module.startswith('ButtonsDxe/'):
        assert data[0x36d4:0x36dc] == bytes.fromhex('101c001230030034')
        # Historical lmi patch: replace ScanCode=0x102 with UnicodeChar=Enter.
        edit(0x36dc, '51208052f1330079', 'b1018052f1370079',
             'Power key: mov w17,#0x102 / scan code -> mov w17,#13 / UnicodeChar')
    elif module.startswith('DALSYSDxe/'):
        # Locate and walk the actual IORT; do not infer the field from a nearby
        # string alone. Layout: MdePkg/Include/IndustryStandard/IoRemappingTable.h.
        tables = []
        pos = 0
        while True:
            pos = data.find(b'IORT', pos)
            if pos < 0:
                break
            length = struct.unpack_from('<I', data, pos+4)[0]
            if 48 <= length <= len(data)-pos:
                count, node_offset = struct.unpack_from('<II', data, pos+36)
                if node_offset == 48 and 1 <= count <= 128:
                    tables.append((pos, length, count, node_offset))
            pos += 4
        assert len(tables) == 1
        base, length, count, node_offset = tables[0]
        pos, matches = base+node_offset, []
        for _ in range(count):
            kind, size, rev = struct.unpack_from('<BHB', data, pos)
            assert size >= 16 and pos+size <= base+length
            if kind == 1:
                assert size >= 30
                name_end = data.index(0, pos+29, pos+size)
                name = bytes(data[pos+29:name_end]).decode('ascii')
                if name == '\\_SB_.UFS0':
                    mappings, mapping_offset = struct.unpack_from('<II', data, pos+8)
                    assert mapping_offset >= 29 and mapping_offset+20*mappings <= size
                    assert data[pos+28] == 36
                    matches.append(pos+20)  # CacheCoherent UINT32, named component.
            pos += size
        assert pos == base+length and matches == [0x2c654]
        edit(matches[0], '00000000', '01000000', 'UFS IORT named component: CacheCoherent BIT0')
        # Original vendor table already has a zero checksum placeholder and an
        # invalid ACPI checksum. Preserve the template convention, as upstream
        # does; this does not certify it as an installable ACPI table.
        changes[-1]['vendor_template_checksum_before'] = sum(raw[base:base+length]) & 255
        changes[-1]['vendor_template_checksum_after'] = sum(data[base:base+length]) & 255
    elif module.startswith('TzDxe/'):
        # Two distinct call paths read/write this same app-initialized flag.
        assert data[0x2e28:0x2e2c] == bytes.fromhex('e9a65139')
        branch = struct.unpack_from('<I', data, 0x2e30)[0]
        assert branch & 0xff00001f == 0x34000009
        assert 0x2e30 + ((branch >> 5) & 0x7ffff)*4 == 0x2e80
        assert data[0x32d8:0x32dc] == bytes.fromhex('c9a65139')
        edit(0xd469, '00', '01', 'Set the TZ app-initialized flag used by both initialization paths')
    elif module.startswith('UsbConfigDxe/'):
        # Both branches retain their original destination (+0x44), bypassing
        # controller teardown paths. No host-mode or default-role override.
        for offset in (0x5684, 0x56e0):
            assert data[offset-4:offset] in (bytes.fromhex('e82b00f9'), bytes.fromhex('e81f00f9'))
            edit(offset, '2a020034', '11000014', 'USB device-mode preservation: cbz w10,+0x44 -> b +0x44')
    elif module.startswith('UsbMsdDxe/'):
        assert data[0x3aa8:0x3aac] == bytes.fromhex('8c060039')
        edit(0x3a98, 'ec031932', '0c008052', 'SCSI INQUIRY RMB byte: clear removable-media bit before strb [x20,#1]')
    assert len(data) == len(raw) and changes
    # Edits must be exactly those described, without any incidental changes.
    allowed = {i for c in changes for i in range(int(c['offset'],16), int(c['offset'],16)+len(bytes.fromhex(c['before'])))}
    assert all(i in allowed for i,(a,b) in enumerate(zip(raw,data)) if a != b)
    target = out / relative
    pending_outputs.append((target, bytes(data)))
    report['patches'].append(dict(path=relative, original_sha256=digest,
        patched_sha256=sha(data), changed_bytes=sum(a != b for a,b in zip(raw,data)), edits=changes))
for target, data in pending_outputs:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
(out / 'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
for p in report['patches']:
    print(p['path'], p['changed_bytes'], 'bytes changed')
