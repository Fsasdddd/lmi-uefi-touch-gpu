#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "lmi-gpu-hfi.c"
int main(void) {
    unsigned char *p=aligned_alloc(4096,24576);assert(p);
    memset(p,0,24576);memset(p+20480,0xa5,4096);
    assert(lmi_hfi_prepare(p,20480,0x60000000));
    struct lmi_hfi_table *t=(void *)p;
    assert(t->version==0 && t->size==54 && t->qhdr0_offset==6);
    assert(t->qhdr_size==12 && t->num_q==4 && t->num_active_q==4);
    unsigned pri[]={10,10,40,20};
    for(unsigned n=0;n<4;n++) {
        struct lmi_hfi_queue *q=&t->queue[n];
        assert(q->start_addr==0x60000100+n*4096);
        assert(q->status==(n<3) && q->type==(n|(pri[n]<<8)));
        assert(q->queue_size==1024 && !q->msg_size && !q->read_index && !q->write_index);
        for(unsigned k=0;k<5;k++)assert(!q->unused[k]);
    }
    for(unsigned i=216;i<20480;i++)assert(!p[i]);
    for(unsigned i=20480;i<24576;i++)assert(p[i]==0xa5);
    unsigned char copy[20480];memcpy(copy,p,20480);
    assert(!lmi_hfi_prepare(p,20480,0x60000000));assert(!memcmp(copy,p,20480));
    memset(p,0,20480);
    assert(!lmi_hfi_prepare(0,20480,0x60000000));
    assert(!lmi_hfi_prepare(p+1,20480,0x60000000));
    assert(!lmi_hfi_prepare(p,20479,0x60000000));
    assert(!lmi_hfi_prepare(p,20480,0x60000001));
    assert(!lmi_hfi_prepare(p,20480,0xffffc000));
    p[20479]=1;assert(!lmi_hfi_prepare(p,20480,0x60000000));assert(!p[0]);
    p[20479]=0;assert(lmi_hfi_prepare(p,20480,0xffffb000));
    free(p);puts("PASS: vendor HFI ABI, bounds, zeroing/refusals; no DMA proof");
}
