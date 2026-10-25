/* Mode32: source-defined A650 off-only BW table then CORE_FW_START.
 * No GX OOB request, DCVS frequency request, START, CP or secure writes.
 * The CNOC on/off encoding matches Linux A650; addresses come from this DB.
 * All dependencies stay held on both success and failure. */
#include "lmi-gpu-hfi-transfer.h"
#include "lmi-gpu-table-plan.h"
typedef unsigned int u32;
typedef unsigned long long u64;
#define CORE __attribute__((noinline,section(".gpu_hfi_core")))
extern u64 io_map_memory(u64,u64);
extern u32 lmi_gpu_bcm_address(const void *,u32,const char *);
struct lmi_gpu_bw_table {u32 hdr,levels,cnoc_count,ddr_count,cnoc_wait,ddr_wait,cnoc[6],cnoc_data[2][6],ddr[8],ddr_data[16][8];};
_Static_assert(sizeof(struct lmi_gpu_bw_table)==640,"vendor HFI bandwidth table ABI");
int CORE lmi_gpu_prepare_bw(const void *db,u32 bytes,struct lmi_gpu_bw_table *bw) {
    struct lmi_gpu_bw_table t={0};t.levels=1;t.cnoc_count=1;t.ddr_count=3;t.cnoc_wait=t.ddr_wait=1;
    t.ddr[0]=lmi_gpu_bcm_address(db,bytes,"MC0\0\0\0\0");
    t.ddr[1]=lmi_gpu_bcm_address(db,bytes,"SH0\0\0\0\0");
    t.ddr[2]=lmi_gpu_bcm_address(db,bytes,"ACV\0\0\0\0");
    t.cnoc[0]=lmi_gpu_bcm_address(db,bytes,"CN0\0\0\0\0");
    if(!bw || !t.cnoc[0])return 0;
    for(u32 n=0;n<3;n++) {
        if(!t.ddr[n] || t.ddr[n]==t.cnoc[0])return 0;
        for(u32 k=0;k<n;k++)if(t.ddr[n]==t.ddr[k])return 0;
        t.ddr_data[0][n]=0x40000000;
    }
    t.cnoc_data[0][0]=0x40000000;t.cnoc_data[1][0]=0x60000001;
    *bw=t;return 1;
}
int CORE lmi_gpu_hfi_core(u64 pool,u32 bytes,volatile u32 *g) {
    struct lmi_gpu_bw_table bw;
    if(!lmi_gpu_prepare_bw((void *)io_map_memory(0x80860000,0x20000),0x20000,&bw))return 0;
    bw.hdr=0x0030a003;
    const struct lmi_hfi_trace trace={"LMI_GPU_HFI_BW_REQUEST\n","LMI_GPU_HFI_BW_REPLY\n","LMI_GPU_HFI_BW_ACK_VERIFIED\n"};
    if(!lmi_gpu_hfi_exchange(pool,bytes,g,(u32 *)&bw,160,64,8,&trace))return 0;
    const u32 request[]={0x0040020e,0};
    const struct lmi_hfi_trace start={"LMI_GPU_HFI_CORE_REQUEST\n","LMI_GPU_HFI_CORE_REPLY\n","LMI_GPU_HFI_CORE_ACK_VERIFIED\n"};
    return lmi_gpu_hfi_exchange(pool,bytes,g,request,2,224,12,&start);
}
