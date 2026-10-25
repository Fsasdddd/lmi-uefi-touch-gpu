/* Actual boot transaction with host MMIO events; does not execute firmware. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lmi-gpu-boot.c"
static u32 g[0xc000],s[0x4000],writes,released,fw_timeout,hfi_timeout,tcm_fault,setting_fault,missing,bad_crc,verbose,delays,fw_reads,hfi_reads;
static unsigned char fw[41548],pool[196608] __attribute__((aligned(4096)));
static const u64 root=0x123450000ull;
#ifdef LMI_GPU_FAL_VETO
static u32 fal_attempts,fal_fault;
#endif
#ifdef LMI_GPU_GX
static u32 gx_failed,gx_called;
int lmi_gpu_gx(u64 address,u32 bytes,volatile u32 *gmu) {
    assert(address==(u64)pool && bytes==sizeof(pool) && gmu==g);
    assert(released && g[BOOT_GMU_CM3_FW_INIT_RESULT/4]==0x100 && g[BOOT_GMU_HFI_CTRL_STATUS/4]==1);
    gx_called++;return !gx_failed;
}
#endif
#ifdef LMI_GPU_HFI_IO
static u32 io_failed,io_called;
int lmi_gpu_hfi_version(u64 address,u32 bytes,volatile u32 *gmu) {
    assert(address==(u64)pool && bytes==sizeof(pool) && gmu==g);
    assert(released && g[BOOT_GMU_CM3_FW_INIT_RESULT/4]==0x100 && g[BOOT_GMU_HFI_CTRL_STATUS/4]==1);
    io_called++;return !io_failed;
}
#endif
u64 io_map(u64 address,u64 bytes) {
    if(address==0x3d6a000) {assert(bytes==sizeof(g));return missing==1?0:(u64)g;}
    assert(address==0x3da0000 && bytes==sizeof(s));return missing==2?0:(u64)s;
}
void log_line(const char *message) {if(verbose)fputs(message,stdout);}
void log_hex(u64 value) {if(verbose)printf("%016llx\n",value);}
void delay(u32 amount,u32 unit) {assert(amount==100 && unit==1000 && ++delays<=2000);}
const unsigned char *image_file(const char *dir,const char *name,u64 *size,int *disk) {
    assert(!strcmp(dir,"fw") && !strcmp(name,"a650_gmu.bin"));*size=sizeof(fw);*disk=1;return fw;
}
u32 lmi_gpu_firmware_crc(const unsigned char *memory,u32 bytes) {
    assert(memory==fw && bytes==sizeof(fw));return bad_crc?0:0x5c66275c;
}
u32 rsc_read(volatile u32 *word) {
    if(word==g+BOOT_GMU_CM3_FW_INIT_RESULT/4 && released && !fw_timeout && ++fw_reads>=2)*word=0x100;
    if(word==g+BOOT_GMU_HFI_CTRL_STATUS/4 && g[BOOT_GMU_HFI_CTRL_INIT/4] && !hfi_timeout && ++hfi_reads>=2)*word=1;
    return *word;
}
void rsc_write(volatile u32 *word,u32 value) {
    assert(word>=g && word<g+0xc000);u32 off=(u32)(word-g)*4,allowed=0;
#ifdef LMI_GPU_FAL_VETO
    if(off==BOOT_GPU_GMU_CX_GMU_CX_FAL_INTF) {
        assert(!writes && !released && !fal_attempts && value==1 && g[BOOT_GMU_CM3_SYSRESET/4]==1);
        fal_attempts++;if(fal_fault)return;allowed=1;
    }
#endif
    for(u32 n=0;n<5;n++)if(off>=blocks[n].off && off<blocks[n].off+blocks[n].size) {
        assert(!released && g[BOOT_GMU_CM3_SYSRESET/4]==1);allowed=1;
        if(tcm_fault && off==0x3400)return;
    }
    for(u32 n=0;n<14;n++)if(off==settings[n].off) {
        allowed=1;assert(!released && value==settings[n].value);
        if(setting_fault==n+1)return;
    }
    if(off==BOOT_GMU_CM3_SYSRESET) {
#ifdef LMI_GPU_FAL_VETO
        assert(fal_attempts==1 && g[BOOT_GPU_GMU_CX_GMU_CX_FAL_INTF/4]==1);
#endif
        allowed=1;assert(value==0 && !released);
        for(u32 n=0;n<5;n++)assert(!memcmp((unsigned char *)g+blocks[n].off,fw+blocks[n].file,blocks[n].size));
        for(u32 n=0;n<14;n++)assert(g[settings[n].off/4]==settings[n].value);
        assert(g[BOOT_GMU_CM3_BOOT_CONFIG/4]==2 && g[BOOT_GMU_HFI_SFR_ADDR/4]==0x06050200);
        released=1;
    }
    if(off==BOOT_GMU_HFI_CTRL_INIT) {allowed=1;assert(released && value==1 && g[BOOT_GMU_CM3_FW_INIT_RESULT/4]==0x100);}
    assert(allowed);*word=value;writes++;
}
static void seed(void) {
#ifdef LMI_GPU_FAL_VETO
    fal_attempts=fal_fault=0;
#endif
#ifdef LMI_GPU_GX
    gx_failed=gx_called=0;
#endif
    memset(g,0,sizeof(g));memset(s,0,sizeof(s));g[BOOT_GMU_CM3_SYSRESET/4]=1;
    s[0x8000/4]=0xc000e7;s[0x800/4]=0x84000005;s[0xc00/4]=0x300;s[0x8058/4]=0x400;
    s[0x8020/4]=(u32)root;s[0x8024/4]=(u32)(root>>32)|0x10000;
    writes=released=fw_timeout=hfi_timeout=tcm_fault=setting_fault=missing=bad_crc=delays=fw_reads=hfi_reads=0;
#ifdef LMI_GPU_HFI_IO
    io_failed=io_called=0;
#endif
}
int main(int argc,char **argv) {
    assert(argc==2);FILE *file=fopen(argv[1],"rb");assert(file && fread(fw,1,sizeof(fw),file)==sizeof(fw));fclose(file);
    assert(lmi_gpu_exec_canary(0x1badb002)==0x7ea61d23);
    seed();verbose=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==3 && released && fw_reads>=2 && hfi_reads>=2);verbose=0;
    for(u32 n=1;n<=2;n++) {seed();missing=n;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==2 && !writes);}
    seed();bad_crc=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==2 && !writes);
    seed();s[0x800/4]=0;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==2 && !writes);
    seed();s[0x8020/4]^=4096;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==2 && !writes);
    seed();g[BOOT_GMU_HFI_CTRL_STATUS/4]=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==2 && !writes);
    seed();tcm_fault=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==0 && !released);
    for(u32 n=0;n<14;n++)if(settings[n].value) {
        seed();setting_fault=n+1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==0 && !released);
    }
    seed();fw_timeout=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==0 && released && !g[BOOT_GMU_HFI_CTRL_INIT/4] && delays==1000);
    seed();hfi_timeout=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==0 && released && g[BOOT_GMU_HFI_CTRL_INIT/4]==1 && delays>=1000);
#ifdef LMI_GPU_HFI_IO
    assert(!io_called);
    seed();io_failed=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==0 && released && io_called==1);
    seed();assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==3 && io_called==1);
#endif
#ifdef LMI_GPU_GX
    seed();gx_failed=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==0 && released && gx_called==1);
    seed();assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==3 && gx_called==1);
    seed();hfi_timeout=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==0 && !gx_called);
#endif
    puts("PASS: source-defined TCM/config/release ordering, fresh FW/HFI replies, every config mismatch, timeout holds and strict write whitelist");
#ifdef LMI_GPU_FAL_VETO
    seed();fal_fault=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==0 && fal_attempts==1 && !writes && !released);
    seed();g[BOOT_GPU_GMU_CX_GMU_CX_FAL_INTF/4]=1;assert(lmi_gpu_gmu_boot(root,(u64)pool,sizeof(pool))==3 && fal_attempts==1 && released);
#endif
}
