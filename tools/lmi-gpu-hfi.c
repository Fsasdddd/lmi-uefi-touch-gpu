/* A650 vendor kgsl_hfi.c header ABI; ring starts align to128 bytes so CPU
 * cache writeback cannot overwrite a different producer's queue header.
 * Firmware receives each ring address explicitly. Caller owns zeroed backing.
 * This helper never publishes memory, accesses MMIO or starts firmware. */
typedef unsigned int hfi_u32;
struct lmi_hfi_queue {
    hfi_u32 status,start_addr,type,queue_size,msg_size;
    hfi_u32 unused[5],read_index,write_index;
};
struct lmi_hfi_table {
    hfi_u32 version,size,qhdr0_offset,qhdr_size,num_q,num_active_q;
    struct lmi_hfi_queue queue[4];
};
_Static_assert(sizeof(struct lmi_hfi_queue)==48,"vendor HFI queue ABI");
_Static_assert(sizeof(struct lmi_hfi_table)==216,"vendor HFI table ABI");
int lmi_hfi_prepare(void *memory,hfi_u32 bytes,hfi_u32 iova) {
    if(!memory || ((unsigned long long)memory&15) || bytes<20480 ||
       (iova&4095) || iova>0xffffffffu-20479u)return 0;
    unsigned char *p=memory;
    for(hfi_u32 n=0;n<20480;n++)if(p[n])return 0;
    struct lmi_hfi_table *table=memory;
    table->version=0;table->size=54;table->qhdr0_offset=6;
    table->qhdr_size=12;table->num_q=4;table->num_active_q=4;
    const hfi_u32 priorities[]={10,10,40,20};
    for(hfi_u32 n=0;n<4;n++) {
        struct lmi_hfi_queue *q=&table->queue[n];
        q->status=n<3;q->start_addr=iova+256+n*4096;
        q->type=n|(priorities[n]<<8);q->queue_size=1024;
    }
    return 1;
}
