/* lmi gpucc-kona.c: GMU 200 MHz = active GPLL0 /2 /1.5.
 * Called only AFTER confirmed GPU DRV0 MX/CX selector2 completion, RESET1,
 * RSC/PDC initialization and parent/bus clocks held. No PLL or rail writes.
 * Restore XO and complete UPDATE before releasing the GPU-only divided gate.
 * Any pending UPDATE or uncertain restoration retains ALL parents to reboot.
 * Readback proves configuration, not measured frequency or GPU execution. */
typedef unsigned int u32;
typedef unsigned long long u64;
extern u64 io_map(u64,u64);
extern u32 rsc_read(volatile u32 *);
extern void rsc_write(volatile u32 *,u32);
extern void delay(u32,u32);
extern void log_line(const char *);
extern void log_hex(u64);
#define CFG_MASK 0x10371fu
#define DIV_GATE 0x10000u
static void pair(u32 address,u32 value) {log_hex(((u64)address<<32)|value);}
static int __attribute__((section(".gpu_helpers"))) update(volatile u32 *cc) {
    rsc_write(cc+0x1120/4,rsc_read(cc+0x1120/4)|1u);
    for(u32 n=0;n<500;n++) {
        if(!(rsc_read(cc+0x1120/4)&1))return 1;
        delay(1,1000);
    }
    return 0;
}
int __attribute__((section(".gpu_helpers"))) lmi_gpu_gmu_200mhz_probe(void) {
    volatile u32 *gcc=(volatile u32 *)io_map(0x100000,0x80000);
    volatile u32 *cc=(volatile u32 *)io_map(0x3d90000,0x9000);
    volatile u32 *g=(volatile u32 *)io_map(0x3d6a000,0x30000);
    if(!gcc || !cc || !g)return 0;
    const u32 offsets[]={0,4,0x40,0xc,0x38,0x52000};
    u32 source[6];
    log_line("LMI_GPU_GMU_200MHZ_SOURCE\n");
    for(u32 i=0;i<6;i++) {source[i]=rsc_read(gcc+offsets[i]/4);pair(0x100000+offsets[i],source[i]);}
    u32 cfg=rsc_read(cc+0x1124/4),cmd=rsc_read(cc+0x1120/4);
    pair(0x3d91124,cfg);pair(0x3d91120,cmd);pair(0x3d7e000,rsc_read(g+0x14000/4));
    u64 hz=19200000ull*source[1]+((19200000ull*source[2])>>16);
    log_line("LMI_GPU_GMU_200MHZ_PARENT_HZ\n");log_hex(hz);
    /* alpha_pll_lucid_enable: FSM_ENA uses ACTIVE_FLAG, not OPMODE.RUN.
     * lmi inherited MODE=d810003d, OPMODE=0 is this active FSM path. */
    u32 running=(source[0]&0x100000u)?(source[0]&0x40000000u):(source[4]&1);
    if((source[0]&0x80000001u)!=0x80000001u || !running ||
       source[2]>0xffff || ((source[3]>>8)&15)!=1 ||
       hz<599999000 || hz>600001000 || (cfg&CFG_MASK)!=1 || (cmd&1) ||
       rsc_read(g+0x14000/4)!=1 || rsc_read(g+0x14070/4) ||
       (rsc_read(cc+0x1098/4)&0x80000001u)!=1 ||
       (rsc_read(cc+0x109c/4)&0x80000001u)!=1)return 0;
    u32 gate=source[5]&DIV_GATE,good=1;
    rsc_write(gcc+0x52000/4,rsc_read(gcc+0x52000/4)|DIV_GATE);
    delay(10,1000); /* gcc-kona BRANCH_HALT_DELAY */
    if(!(rsc_read(gcc+0x52000/4)&DIV_GATE)) {
        rsc_write(gcc+0x52000/4,(rsc_read(gcc+0x52000/4)&~DIV_GATE)|gate);
        return (rsc_read(gcc+0x52000/4)&DIV_GATE)==gate?0:2;
    }
    u32 requested=(cfg&~CFG_MASK)|0x100602u;
    rsc_write(cc+0x1124/4,requested);
    if(!update(cc))return 2;
    log_line("LMI_GPU_GMU_200MHZ_ACTUAL\n");
    u32 actual=rsc_read(cc+0x1124/4);
    pair(0x3d91124,actual);pair(0x3d91120,rsc_read(cc+0x1120/4));pair(0x152000,rsc_read(gcc+0x52000/4));
    if(actual!=requested)good=0;
#ifdef LMI_GPU_GMU_ROUTE
    if(rsc_read(g+0x14000/4)!=1 || rsc_read(g+0x14070/4))return 2;
    if(good) {
        extern int lmi_gpu_gmu_route_probe(void);
        int routed=lmi_gpu_gmu_route_probe();
        log_line("LMI_GPU_GMU_ROUTE_RESULT\n");log_hex(routed);
#ifdef LMI_GPU_GMU_BOOT
        if(routed==3)return 3;
#endif
        if(routed==2)return 2;
        if(routed!=1)good=0;
    }
#endif
    if(rsc_read(g+0x14000/4)!=1 || rsc_read(g+0x14070/4))return 2;
    rsc_write(cc+0x1124/4,(rsc_read(cc+0x1124/4)&~CFG_MASK)|(cfg&CFG_MASK));
    if(!update(cc) || rsc_read(cc+0x1124/4)!=cfg)return 2;
    rsc_write(gcc+0x52000/4,(rsc_read(gcc+0x52000/4)&~DIV_GATE)|gate);
    if((rsc_read(gcc+0x52000/4)&DIV_GATE)!=gate)return 2;
    log_line("LMI_GPU_GMU_200MHZ_RESTORED\n");
    pair(0x3d91124,rsc_read(cc+0x1124/4));pair(0x3d91120,rsc_read(cc+0x1120/4));pair(0x152000,rsc_read(gcc+0x52000/4));
    log_line("LMI_GPU_GMU_200MHZ_RESTORE_OK\n");
    return good?1:0;
}
