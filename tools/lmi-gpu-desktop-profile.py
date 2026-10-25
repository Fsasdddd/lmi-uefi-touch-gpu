"""Pinned legacy ABI bindings and guarded RAM-kernel patches for lmi desktop."""
import hashlib,struct

BINDINGS={
    'desktop_space':('_core_space',0xfffffff007b03910),
    'desktop_slot':('_core_target',0xfffffff007e98f60),
    'desktop_free':('_gpu_free',0xfffffff007e94970),
    'desktop_free_count':('_gpu_free_count',0xfffffff007e94968),
    'legacy_space_map':('_space_map',0xfffffff0074d2ea4),
    'desktop_service_start':('_RedwoodGPUStart',0xfffffff0079e5d74),
    'absolute_time':('_mach_absolute_time',0xfffffff00746959c),
}
# Each original exported entry is replaced by one direct B, preserving the ABI.
ABI={
    '_redwood_adreno_quiesce':(0xfffffff0074d1e74,0xf0004e08,'stop'),
    '_redwood_gpu_stop':(0xfffffff0074d209c,0xd10103ff,'stop'),
    '_redwood_gpu_done':(0xfffffff0074d21d0,0xd0004e28,'done'),
    '_redwood_adreno_stop':(0xfffffff0074d29a4,0xd10083ff,'stop'),
    '_redwood_gpu_ready':(0xfffffff0074d29f4,0xd0004e08,'ready'),
    '_redwood_gpu_parameter':(0xfffffff0074d2a00,0x52800008,'parameter'),
    '_redwood_gpu_map':(0xfffffff0074d2e7c,0xaa0103e8,'map'),
    '_redwood_gpu_mapped':(0xfffffff0074d30ac,0x90003188,'mapped'),
    '_redwood_gpu_unmap':(0xfffffff0074d3120,0xa9bb67fa,'unmap'),
    '_redwood_gpu_to_memory':(0xfffffff0074d3270,0x927ae408,'to_memory'),
    '_redwood_gpu_last':(0xfffffff0074d3298,0xb0004e08,'last'),
    '_redwood_gpu_worked':(0xfffffff0074d32a4,0xa9bd57f6,'worked'),
    '_redwood_gpu_submit':(0xfffffff0074d34f8,0xa9ba6ffc,'submit'),
    '_redwood_gpu_report':(0xfffffff0074d3964,0xd10303ff,'report'),
    '_redwood_gpu_recover':(0xfffffff0074d3c50,0xb0004e08,'recover'),
}

def bindings(symbols):
    for name,va in BINDINGS.values():assert symbols[name]==va,name
    return {key:va for key,(name,va) in BINDINGS.items()}

def patch(raw,offset,audit,code,linked,symbols):
    entry,start,end=[int(audit[key],16) for key in ['entry','start','end']]
    assert audit['result']=='PASS' and start==entry+8 and 0<len(code)<=end-start
    at=offset(entry);assert list(struct.unpack_from('<2I',raw,at))==[int(v,16) for v in audit['original_entry_words']]
    struct.pack_into('<2I',raw,at,0x52800000,0xd65f03c0)
    at=offset(start,len(code));old=bytes(raw[at:at+len(code)]);raw[at:at+len(code)]=code
    patches=[dict(va=hex(entry),new=['0x52800000','0xd65f03c0'],purpose='Disable obsolete board init entries'),
        dict(va=hex(start),bytes=len(code),limit=hex(end),original_region_sha256=hashlib.sha256(old).hexdigest(),purpose='Opt-in lmi desktop backend in audited obsolete init bodies')]
    for slot,old_value in zip(audit['table_slots'],audit['original_entries'].values()):
        at=int(slot,16);assert struct.unpack_from('<Q',raw,at)[0]==int(old_value,16)
        struct.pack_into('<Q',raw,at,entry)
        patches.append(dict(file_offset=slot,old=old_value,new=hex(entry),purpose='Redirect obsolete init table slot to false-return stub'))
    for name,(pc,old,target) in ABI.items():
        assert symbols[name]==pc and struct.unpack_from('<I',raw,offset(pc))[0]==old,name
        to=linked['lmi_desktop_'+target];assert start<=to<start+len(code) and (to-pc)%4==0 and -(1<<27)<=to-pc<(1<<27)
        new=0x14000000|(((to-pc)//4)&0x3ffffff);struct.pack_into('<I',raw,offset(pc),new)
        patches.append(dict(va=hex(pc),old=hex(old),new=hex(new),target=hex(to),purpose='lmi desktop ABI '+name))
    return patches
