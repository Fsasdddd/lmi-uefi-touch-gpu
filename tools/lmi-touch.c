/* lmi FT3518 bring-up. No firmware or storage writes.
 * GPIO offsets: Xiaomi lmi-q-oss pinctrl-kona.c SOUTH bank and live DT.
 * mode1 inherited-state probe; mode2 inherited-state samples.
 * mode3 board GPIO power/reset probe; mode4 board GPIO power/reset samples.
 * mode5 additionally votes liveDT ldoc1=1.8V, probe only; mode6 posts samples.
 * Changed pins return to their original state. Exact chip ID gates samples.
 */
typedef unsigned int u32;
typedef unsigned long long u64;
typedef unsigned char u8;
#include "lmi-touch-timing.h"
extern u64 io_map(u64, u64);
extern u64 io_map_memory(u64, u64);
extern void delay(u32, u32);
extern void log_line(const char *);
extern void log_hex(u64);
extern int boot_arg(const char *, void *, int);
extern void *current_thread(void);
extern int terminate(void *);
extern void touch_post(u32, u32, u32, u32);
extern void *user_regs(void *);
extern int thread_info(void *,int,int *,u32 *);
#ifdef LMI_TOUCH_SMP
extern void smp_touch_poll(const u8 *,u32);
#endif
struct bus { volatile u32 *pin[5]; u32 cfg[5], io[5]; };
static void pause_us(u32 n) { delay(n, 1000); }
#ifdef LMI_TOUCH_COMPACT_LOG
/* Runtime GPU builds retain all touch operations and guards; omit only the
 * old per-register diagnostic labels to stay inside the audited RX region. */
#define field(label,value) ((void)(value))
#else
static void field(const char *s, u64 n) { log_line(s); log_hex(n); }
#endif
/* Called only by the two bounded ustacks snapshots, on the selected process.
 * Saved user state is diagnostic, not a live CPU sample. No user dereferences.
 */
void *lmi_ustacks_regs(void *thread) {
    u64 *s=user_regs(thread);
    if(s && *(u32 *)s==21) {
        int info[10];u32 count=10;
        field("LMI_USTATE_THREAD\n",(u64)thread);
        if(thread_info(thread,3,info,&count)==0 && count==10) {
            field("LMI_USTATE_RUN_STATE\n",info[6]);
            field("LMI_USTATE_USER_US\n",(u64)(u32)info[0]*1000000+(u32)info[1]);
            field("LMI_USTATE_SYSTEM_US\n",(u64)(u32)info[2]*1000000+(u32)info[3]);
        }
        field("LMI_USTATE_PC\n",s[0x108/8]);
        field("LMI_USTATE_FAR\n",s[0x118/8]);
        field("LMI_USTATE_ESR\n",*(u32 *)((u8 *)s+0x120));
        field("LMI_USTATE_X8\n",s[(8+8*8)/8]);
        field("LMI_USTATE_X19\n",s[(8+19*8)/8]);
        field("LMI_USTATE_X20\n",s[(8+20*8)/8]);
    }
    return s;
}
static void fence(void) { __asm__ volatile("dsb sy" ::: "memory"); }
/* GPIO36 = SE13 IO0/SDA, GPIO37 = SE13 IO1/SCL.
 * Drive only low; release high by clearing OE, retaining pull/drive fields.
 */
static void line(struct bus *b, int i, int high) {
    /* Board DT active pins have external pull-ups; add weak internal pull-up
     * for cold-boot diagnosis, while retaining open-drain output behavior.
     */
    u32 cfg = (b->cfg[i] & ~((15u << 2) | (1u << 9) | 3u)) | 3u;
    b->pin[i][1] = b->io[i] & ~2u;
    b->pin[i][0] = cfg | (high ? 0 : 1u << 9);
    fence(); lmi_touch_edge_delay();
}
static int level(struct bus *b, int i) { return b->pin[i][1] & 1; }
static int clock_high(struct bus *b) {
    line(b, 1, 1);
    for (int n=0;n<100;n++) { if(level(b,1)) return 1; lmi_touch_edge_delay(); }
    return 0;
}
static void stop(struct bus *b) {
    line(b,1,0); line(b,0,0); clock_high(b); line(b,0,1);
}
static int start(struct bus *b) {
    line(b,0,1);
    if(!clock_high(b) || !level(b,0)) return 0;
    line(b,0,0); line(b,1,0); return 1;
}
static int send(struct bus *b,u8 v) {
    for(int n=7;n>=0;n--) {
        line(b,0,(v>>n)&1); if(!clock_high(b))return 0; line(b,1,0);
    }
    line(b,0,1); if(!clock_high(b))return 0;
    int ack=!level(b,0); line(b,1,0); return ack;
}
static int receive(struct bus *b,u8 *out,int last) {
    u8 v=0; line(b,0,1);
    for(int n=0;n<8;n++) {
        if(!clock_high(b))return 0;
        v=(v<<1)|level(b,0); line(b,1,0);
    }
    line(b,0,last); if(!clock_high(b))return 0;
    line(b,1,0); line(b,0,1); *out=v; return 1;
}
static int read_reg(struct bus *b,u8 reg,u8 *data,int count) {
    int ok=start(b) && send(b,0x70) && send(b,reg) && start(b) && send(b,0x71);
    for(int i=0;ok && i<count;i++)ok=receive(b,&data[i],i==count-1);
    stop(b); return ok;
}
static u32 scale(u32 n,u32 max) { return (n>max?max:n)*65535u/max; }
static void output(struct bus *b,int i,int high) {
    /* Only board-DT reset38 / enable72. Keep inherited pull/drive settings. */
    b->pin[i][1]=high?2u:0u;
    b->pin[i][0]=(b->cfg[i]&~(15u<<2))|(1u<<9);
    fence();
}
/* Live DT: cmd-db80860000/20000, apps RSC DRV2=18220000, TCS offsetd00.
 * Request only DT resource ldoc1 at its declared1800mV. Active TCS group
 * starts at0 in the liveDT (type2,count2), matching vendor rpmh-rsc.c.
 */
static int supply(void) {
    u8 *db=(u8 *)io_map_memory(0x80860000,0x20000);
    if(!db)return 0;
    field("LMI_TOUCH_CMD_DB_MAGIC\n",*(u32 *)(db+4));
    if(*(u32 *)(db+4)!=0x0c0330db)return 0;
    u32 addr=0;
    for(int s=0;s<8;s++) {
        unsigned short *v=(unsigned short *)(db+8+s*16);
        u32 off=144u+v[1],count=v[3];
        if(!v[0] || count>512 || off>0x20000 || count*24u>0x20000-off)continue;
        for(u32 j=0;j<count;j++) {
            u8 *p=db+off+24*j;
            if(p[0]=='l'&&p[1]=='d'&&p[2]=='o'&&p[3]=='c'&&p[4]=='1'&&p[5]==0&&p[6]==0&&p[7]==0)
                addr=*(u32 *)(p+16);
        }
    }
    field("LMI_TOUCH_LDOC1_ADDRESS\n",addr);
    if(!addr || ((addr>>16)&15)!=4)return 0;
    volatile u32 *r=(volatile u32 *)io_map(0x18220000,0x10000);
    if(!r)return 0;
    volatile u32 *t=r+0xd00/4;
    field("LMI_TOUCH_TCS_STATUS\n",t[0x18/4]);
    field("LMI_TOUCH_TCS_CONTROL\n",t[0x14/4]);
    field("LMI_TOUCH_TCS_COMMAND_ENABLE\n",t[0x1c/4]);
    field("LMI_TOUCH_TCS_IRQ_STATUS\n",t[1]);
    /* STATUS=1 is idle. Completed firmware requests retain TRIGGER/ENABLE;
     * clear them in vendor order before reusing the idle active TCS.
     */
    if(t[0x18/4]!=1)return 0;
    u32 old_irq=t[0],old_control=t[0x14/4];
    u32 old_wait=t[0x10/4],old_enable=t[0x1c/4];
    u32 old[9];
    for(int i=0;i<3;i++)for(int k=0;k<3;k++)old[i*3+k]=t[(0x30+20*i+4*k)/4];
    t[0x14/4]=old_control&~(1u<<24);fence();
    t[0x14/4]=old_control&~((1u<<24)|(1u<<16));fence();
    if(t[0x18/4]!=1)return 0;
    t[0x1c/4]=0;fence();
    t[0x08/4]=1;
    const u32 data[3]={1800,1,7};
    for(int i=0;i<3;i++) {
        t[(0x30+20*i)/4]=0x10108;
        t[(0x34+20*i)/4]=addr+4*i;
        t[(0x38+20*i)/4]=data[i];
    }
    t[0x10/4]=7;t[0x1c/4]=7;t[0]=old_irq|1;fence();
    t[0x14/4]=1u<<16;fence();t[0x14/4]=(1u<<16)|(1u<<24);fence();
    int done=0;
    for(int n=0;n<2000;n++) { if(t[1]&1){done=1;break;} pause_us(100); }
    field("LMI_TOUCH_LDOC1_VOTE_DONE\n",done);
    if(!done)return 0; /* Do not rewrite commands while transaction is pending. */
    int complete=1;
    for(int i=0;i<3;i++) {
        u32 status=t[(0x3c+20*i)/4];
        field("LMI_TOUCH_SUPPLY_COMMAND_STATUS\n",status);
        if((status&0x10100)!=0x10100)complete=0;
    }
    t[0x14/4]=1u<<16;fence();t[0x14/4]=0;fence();
    t[0x1c/4]=0;t[0x10/4]=0;t[2]=1;
    for(int i=0;i<3;i++)for(int k=0;k<3;k++)t[(0x30+20*i+4*k)/4]=old[i*3+k];
    t[0x10/4]=old_wait;t[0x1c/4]=old_enable;t[0]=old_irq;
    /* Never restore a set TRIGGER: that would replay firmware commands. */
    t[0x14/4]=old_control&~((1u<<24)|(1u<<16));fence();
    pause_us(20000);return complete;
}
__attribute__((section(".text.entry")))
void lmi_touch_thread(void *unused,int result) {
    (void)unused; (void)result;
    struct bus b;
    const u32 pins[5]={36,37,38,39,72};
    u32 mode=0;
    boot_arg("lmi_touch",&mode,4);
    if(mode<1 || mode>6)goto done;
    if(!lmi_touch_timing_ready())goto done;
    log_line("LMI_TOUCH_BEGIN\n");
    for(int i=0;i<5;i++) {
        b.pin[i]=(volatile u32 *)io_map(0xf500000ull+0x1000ull*pins[i],0x1000);
        if(!b.pin[i])goto done;
        b.cfg[i]=b.pin[i][0]; b.io[i]=b.pin[i][1];
        field("LMI_TOUCH_PIN\n",pins[i]); field("CFG\n",b.cfg[i]); field("IO\n",b.io[i]);
    }
    if(mode>=3) {
        /* Xiaomi fts_power_source_ctrl + fts_reset_proc: GPIO72 enable,
         * reset38 low5ms/high. Leave PM8150A L1 at its inherited voltage.
         */
        log_line("LMI_TOUCH_GPIO_POWER_RESET\n");
        output(&b,2,0); output(&b,4,1); pause_us(20000);
        if(mode>=5 && !supply()) {
            log_line("LMI_TOUCH_SUPPLY_UNCONFIRMED\n");
            if(mode==6)mode=5; /* Unconfirmed power can never post events. */
        }
        pause_us(5000); output(&b,2,1); pause_us(200000);
    }
    line(&b,0,1); line(&b,1,1);
    for(int i=0;i<5;i++) {
        field("LMI_TOUCH_ACTIVE_PIN\n",pins[i]);
        field("CFG\n",b.pin[i][0]); field("IO\n",b.pin[i][1]);
    }
    field("LMI_TOUCH_IDLE\n",level(&b,0)|(level(&b,1)<<1));
    u8 id=0,id2=0;
    int a=read_reg(&b,0xa3,&id,1),c=read_reg(&b,0x9f,&id2,1);
    field("LMI_TOUCH_ACK\n",a|(c<<1)); field("LMI_TOUCH_ID\n",((u32)id<<8)|id2);
#ifndef LMI_TOUCH_COMPACT_LOG
    if(a && c && id==0x54 && id2==0x52) {
        const u8 regs[]={0,1,2,3,4,5,6,0xa5,0xa6,0xa8,0x8f,0x91};
        for(u32 n=0;n<sizeof(regs);n++) {
            u8 value=0;
            int ok=read_reg(&b,regs[n],&value,1);
            field("LMI_TOUCH_SINGLE_REGISTER\n",((u32)regs[n]<<16)|((u32)ok<<8)|value);
        }
    }
#endif
    if(a && c && id==0x54 && id2==0x52 && (mode==2 || mode==4 || mode==6)) {
        log_line("LMI_TOUCH_READY\n");
        u32 active=0,x[10]={0},y[10]={0},bad=0,reports=0;
        /* Bounded iteration count; native RAM return timer bounds boot runtime.
         * Polling errors stop the driver after 8 consecutive failures.
         */
        for(int tick=0;tick<4000;tick++) {
            u8 data[63]; u32 next=0;
            /* Read the 3-byte header first. Avoid a 63-byte bit-banged
             * transfer when no valid frame exists, preserving startup CPU.
             */
            if(!read_reg(&b,0,data,active?63:3)) {
                if(!bad)log_line("LMI_TOUCH_REPORT_READ_FAILED\n");
                if(++bad>=64)break; pause_us(20000); continue;
            }
#ifdef LMI_TOUCH_SMP
            smp_touch_poll(data,(u32)tick);
#endif
#ifndef LMI_TOUCH_COMPACT_LOG
            if(tick%100==0) {
                field("LMI_TOUCH_POLL\n",tick);
                field("LMI_TOUCH_IRQ_HEADER\n",((u32)level(&b,3)<<24)|((u32)data[0]<<16)|((u32)data[1]<<8)|data[2]);
                const u8 status_regs[]={0xa5,0xa6,0xb4,0xd0};
                for(int n=0;n<4;n++) {
                    u8 value=0;int ok=read_reg(&b,status_regs[n],&value,1);
                    field("LMI_TOUCH_RUNTIME_STATUS\n",((u32)status_regs[n]<<16)|((u32)ok<<8)|value);
                }
            }
#endif
            /* While active, read the whole report in one transfer. FT3518
             * release records have count zero but retain the final position.
             * Only an idle count-zero header can skip reading the slots.
             */
            if(!(data[2]&15) && !active) {
                bad=0;pause_us(50000);continue;
            }
            /* Cold-boot report area reads FF with correct runtime ID/FW/vendor.
             * Vendor reads only on IRQ; FF may persist until the first touch.
             * Polling must wait, not exit before the desktop.
             */
            if((data[2]&15)>10) { bad=0;pause_us(200000);continue; }
            if((!active && !read_reg(&b,0,data,63)) || (data[2]&15)>10) {
                pause_us(50000);continue;
            }
            int valid=1;
            for(int k=0;k<10;k++) {
                int o=3+6*k, finger=data[o+2]>>4,ev=data[o]>>6;
                if(finger>=10)break;
                if((data[2]&15) && (ev==0 || ev==2)) {
                    if(!(data[2]&15) || (next&(1u<<finger))) { valid=0; break; }
                    next|=1u<<finger;
                }
            }
            if(!valid) { if(++bad>=8)break; pause_us(20000); continue; }
            bad=0;
            for(int k=0;k<10;k++) {
                int o=3+6*k,f=data[o+2]>>4,ev=data[o]>>6;
                if(f>=10)break;
                if(((data[2]&15) && (ev==0 || ev==2)) || (ev==1 && (active&(1u<<f)))) {
                    x[f]=scale(((data[o]&15)<<8)|data[o+1],1079);
                    y[f]=scale(((data[o+2]&15)<<8)|data[o+3],2399);
                    if(ev!=1)touch_post(active&(1u<<f)?2:1,f,x[f],y[f]);
                    if(reports++<12) { field("LMI_TOUCH_SAMPLE\n",f); field("X\n",x[f]);field("Y\n",y[f]); }
                }
            }
            for(int f=0;f<10;f++)if((active&~next)&(1u<<f))touch_post(3,f,x[f],y[f]);
            active=next; pause_us(20000);
        }
        for(int f=0;f<10;f++)if(active&(1u<<f))touch_post(3,f,x[f],y[f]);
        field("LMI_TOUCH_REPORTS\n",reports);
    }
    for(int i=0;i<5;i++) {
        if(i==3 || (i>=2 && mode<3))continue;
        b.pin[i][1]=b.io[i]&2; b.pin[i][0]=b.cfg[i]; fence();
    }
    log_line("LMI_TOUCH_END\n");
done:
    terminate(current_thread());
}
