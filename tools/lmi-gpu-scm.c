/* GPU PAS service discovery only, after verified CP writeback. No buffer,
 * PIL state change, firmware upload, SCM IO or APSS/rail command is sent.
 * lmi-q-oss qcom_scm-64.c convention probe + is_call_available ABI.
 * Interrupted returns carry A6 as required by ARM_SMCCC_QUIRK_QCOM_A6. */
typedef unsigned long long u64;
typedef unsigned int u32;
#define SCM __attribute__((noinline,section(".gpu_scm")))
extern void log_line(const char *);
extern void log_hex(u64);
#ifdef LMI_GPU_SCM_HOST
extern void scm_step(u64,u64,u64,u64 *);
#else
static void SCM scm_step(u64 fnid,u64 query,u64 session,u64 *out) {
    register u64 x0 __asm__("x0")=fnid,x1 __asm__("x1")=1,x2 __asm__("x2")=query;
    register u64 x3 __asm__("x3")=0,x4 __asm__("x4")=0,x5 __asm__("x5")=0;
    register u64 x6 __asm__("x6")=session,x7 __asm__("x7")=0;
    __asm__ volatile("smc #0":"+r"(x0),"+r"(x1),"+r"(x2),"+r"(x3),"+r"(x4),"+r"(x5),"+r"(x6),"+r"(x7)
        ::"x8","x9","x10","x11","x12","x13","x14","x15","x16","x17","memory");
    out[0]=x0;out[1]=x1;out[2]=x6;
}
#endif
int SCM lmi_gpu_scm_available(void) {
    const u32 queries[]={0x42000601,0x02000201,0x02000202,0x02000205,0x02000206};
    for(u32 i=0;i<5;i++) {
        u64 function=i?0x42000601:0xc2000601,out[3]={1,0,0};u32 n;
        for(n=0;n<64;n++) {
            scm_step(n?1:function,queries[i],out[2],out);
            if(out[0]!=1)break;
        }
        log_line("LMI_GPU_SCM_QUERY\n");
        log_hex(function);log_hex(queries[i]);log_hex(out[0]);log_hex(out[1]);log_hex(n==64?64:n+1);
        if(out[0] || out[1]!=1)return 0;
    }
    log_line("LMI_GPU_SCM_PAS_AVAILABLE\n");return 1;
}
