#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#define LMI_GPU_POLL_HOST
#include "lmi-gpu-desktop.c"
struct desktop_space desktop_space;
u64 desktop_slot[3],desktop_free[1024][2],g_phys_base=0x80000000,g_phys_size=0x10000000;
u32 desktop_free_count;
static unsigned char pool[81920] __attribute__((aligned(4096))),dma[81920];
static u32 gpu[0x10000],s[0x4000],g[0xc000],test,services,queued,decoded,cache_calls,maps,tlbis,syncs;
static struct desk_state storage;
static jmp_buf held;
static int expect_hold,tile_calls;
static u64 counter,counter_frequency=19200000;
static u32 sleeping,pending_end,complete_at;
u64 lmi_gpu_counter(void) {counter+=192;return counter;}
u64 lmi_gpu_counter_frequency(void) {return counter_frequency;}
void log_line(const char *p) {(void)p;}
void log_hex(u64 v) {(void)v;}
u64 absolute_time(void) {return 42;}
u64 pa_of(u64 p) {assert(p>=(u64)pool && p<(u64)pool+sizeof(pool));return 0x80000000+p-(u64)pool;}
u64 io_map(u64 p,u64 n) {
    if(p==0x3d00000) {assert(n==sizeof(gpu));return test==1?0:(u64)gpu;}
    assert(p==0x3da0000 && n==sizeof(s));return (u64)s;
}
void *alloc_data(u64 n) {assert(n==sizeof(storage));return test==2?0:&storage;}
int lmi_gpu_cp_complete(volatile u32 *a,volatile u32 *b,volatile u32 *c,u32 at) {
    assert(a==gpu && b==s && c==g);return gpu[0x806]==at && !gpu[0x821] && !gpu[0x823];
}
int boot_arg(const char *key,void *out,int n) {
    assert(n==4);assert(!strcmp(key,"lmi_gpu_tile") || !strcmp(key,"lmi_gpu_desktop"));
    *(u32 *)out=test==30?2:1;return test!=29 && (test!=31 || strcmp(key,"lmi_gpu_desktop"));
}
int lmi_gpu_tile(u64 p,u32 n,volatile u32 *c) {assert(p==(u64)pool && n==sizeof(pool) && c==g);tile_calls++;return test!=32;}
void desktop_service_start(void) {assert(lmi_desktop_ready() && gpu[0x806]==72 && desktop_free_count==1);services++;}
int legacy_space_map(struct desktop_space *p,u64 addr,u64 phys,u64 attr) {
    assert(p==&desktop_space && addr>=0x20000000 && !(addr&4095));
    assert((!phys && !attr) || (phys>=g_phys_base && (attr==0xe40 || attr==0xec0)));
    maps++;p->tables[0].changed=1;return test!=25;
}
int cache_sync(u64 p,u32 n,int publish) {
    cache_calls++;
    if(test==3 || (test==19 && publish && n==32768) || (test==20 && !publish && queued>1))return 0;
    if(p>=(u64)pool && p+n<=(u64)pool+sizeof(pool)) {
        unsigned at=p-(u64)pool;
        if(publish)memcpy(dma+at,pool+at,n);else memcpy(pool+at,dma+at,n);
    } else assert(p==(u64)&storage && n==sizeof(storage));
    return 1;
}
u32 rsc_read(volatile u32 *p) {
    if(test==4 && p==gpu+0xb604)return *p^1;
    if(test==33 && p==gpu+0x806 && pending_end && counter>=complete_at) {
        gpu[0x806]=pending_end;pending_end=0;
    }
    return *p;
}
/* Decode the DMA-visible ring independently, including both type7 parity bits.
 * GPU completion changes DMA scratch only; the CPU sees it after invalidation. */
static void execute(u32 end) {
    u32 *ring=(void *)dma,*scratch=(void *)(dma+65536),pos=gpu[0x806],events=0,ibs=0,waits=0;
    while(pos!=end) {
        u32 h=ring[pos],cnt=h&0x3fff,op=(h>>16)&127;pos=(pos+1)&8191;
        assert(h>>28==7 && ((h>>15)&1)==(1^__builtin_parity(cnt)) && ((h>>23)&1)==(1^__builtin_parity(op)));
        u32 arg[4]={0};assert(cnt<=4);
        for(u32 i=0;i<cnt;i++) {assert(pos!=end);arg[i]=ring[pos];pos=(pos+1)&8191;}
        if(op==0x3d) {assert(queued==1 && cnt==3 && arg[0]==0x1010044 && !arg[1] && arg[2]==0x650c0de4);scratch[17]=arg[2];}
        else if(op==0x46 && cnt==1) {assert(events<2 && arg[0]==0x18+events);events++;}
        else if(op==0x3f) {assert(events==2 && cnt==3 && arg[0]>=0x20000000 && !arg[1] && arg[2]);ibs++;}
        else if(op==0x26) {assert(cnt==0 && ibs && !waits++);}
        else {assert(op==0x46 && cnt==4 && events==2 && ibs && waits==1 && arg[0]==4 && arg[1]==0x1010040 && !arg[2]);if(test!=21)scratch[16]=arg[3];}
        decoded++;
    }
    gpu[0x806]=end;
}
void rsc_write(volatile u32 *p,u32 v) {
    if(p==gpu+0x807) {
        assert(!memcmp(pool,dma,32768));queued++;*p=v;
        if(test==22)gpu[0x821]=1;else if(test!=23) {
            u32 previous=gpu[0x806];execute(v);
            if(test==33) {pending_end=v;gpu[0x806]=previous;}
        }
        return;
    }
    if(p==s+0x9610/4) {assert(v==2 && maps && !desktop_space.tables[0].changed);tlbis++;}
    else if(p==s+0x97f0/4) {assert(!v && tlbis);syncs++;}
    else {int found=0;for(u32 i=0;i<sizeof(nc)/sizeof(nc[0]);i++)if(p==gpu+nc[i][0] && v==nc[i][1])found=1;assert(found);}
    *p=v;
}
void delay(u32 n,u32 unit) {
    assert(unit==1000 && (n==1 || n==100));
    sleeping++;
    counter+=(u64)n*192/10;
    if(expect_hold && storage.failed)longjmp(held,1);
}
static void seed(u32 t) {
    memset(pool,0,sizeof(pool));memset(dma,0,sizeof(dma));memset(gpu,0,sizeof(gpu));memset(s,0,sizeof(s));memset(g,0,sizeof(g));
    memset(&desktop_space,0,sizeof(desktop_space));memset(desktop_slot,0,sizeof(desktop_slot));memset(&storage,0,sizeof(storage));
    desktop_space.control=256;desktop_free_count=0;test=t;services=queued=decoded=cache_calls=maps=tlbis=syncs=0;expect_hold=tile_calls=0;
    counter=sleeping=pending_end=complete_at=0;counter_frequency=19200000;
    gpu[0x806]=gpu[0x807]=68;gpu[0x808]=1;gpu[0x210]=1;s[0x9058/4]=0x400;
    s[0x9020/4]=pa_of((u64)pool+17*4096);s[0x9024/4]=0x20000;s[0x9000/4]=0xc000e7;s[0x9010/4]=0x38071;s[0x9030/4]=0x803519;
    ((u64 *)(pool+17*4096))[0]=pa_of((u64)pool+18*4096)|3;
    ((u64 *)(pool+18*4096))[8]=pa_of((u64)pool+19*4096)|3;
    for(u32 i=0;i<17;i++)((u64 *)(pool+19*4096))[i]=pa_of((u64)pool+i*4096)|(i>=8 && i<16?0xec3:0xe43);
    memcpy(dma,pool,sizeof(pool));
}
static int start(void) {return lmi_gpu_desktop((u64)pool,sizeof(pool),g);}
int main(void) {
    for(u32 t=0;t<=15;t++) {
        seed(t);
        if(t==5)desktop_space.table_count=1;if(t==6)s[0x9024/4]^=0x10000;
        if(t==7)((u64 *)(pool+19*4096))[16]^=128;if(t==8)((u64 *)(pool+18*4096))[9]=3;
        if(t==9)((u32 *)(dma+65536))[16]=1;if(t==10)gpu[0x806]=67;
        if(t==11)desktop_slot[1]=1;if(t==12)desktop_space.tables[1023].changed=1;
        if(t==13)((u32 *)pool)[68]=1;if(t==14)desktop_free_count=1;if(t==15)desktop_space.control=0;
        assert(start()==(t==0));assert(services==(t==0));
    }
    seed(0);assert(start());u64 addr[128];u32 sizes[128];for(u32 i=0;i<128;i++){addr[i]=0x20000000+4096*i;sizes[i]=256;}
    for(u32 i=1;i<=40;i++){assert(lmi_desktop_submit(addr,sizes,128)==i);assert(lmi_desktop_done(i) && !lmi_desktop_done(i+1));}
    assert(storage.at==(72+40*(4+512+1+5))%8192 && queued==41 && decoded==1+40*132); /* binding + events/IBs/wait/fence */
    u64 v;assert(lmi_desktop_parameter(2,&v) && v==1179648);assert(lmi_desktop_parameter(3,&v) && v==0x6050002);
    assert(lmi_desktop_parameter(16,&v) && v==16 && !lmi_desktop_parameter(999,&v));
    assert(lmi_desktop_map(addr[0],g_phys_base,0));lmi_desktop_mapped();assert(!desktop_space.tables[0].changed);
    lmi_desktop_unmap(addr[0],4096);assert(tlbis==1 && syncs==1);
    assert(!lmi_desktop_map(addr[0]+1,g_phys_base,0) && !lmi_desktop_map(addr[0],g_phys_base-4096,0));
    lmi_desktop_to_memory(&storage,sizeof(storage));
    for(u32 t=19;t<=23;t++) {
        seed(0);assert(start());test=t;u32 f=lmi_desktop_submit(addr,sizes,1);
        assert(f==(t==19?0:1) && storage.failed && lmi_desktop_ready());
        assert(!lmi_desktop_done(1) && !lmi_desktop_submit(addr,sizes,1));
    }
    for(u32 t=24;t<=28;t++) {
        seed(0);assert(start());test=t;expect_hold=1;
        if(!setjmp(held)) {
            if(t==24)gpu[0x821]=1;if(t==26)s[0x97f4/4]=1;
            if(t==27)desktop_space.tables[0].changed=1,test=3;
            if(t==28)lmi_desktop_to_memory(0,1);else if(t==27)lmi_desktop_mapped();else lmi_desktop_unmap(addr[0],4096);
            assert(!"uncertain release returned");
        }
        assert(storage.failed && lmi_desktop_ready());
    }
    for(u32 t=29;t<=32;t++){seed(t);assert(!lmi_gpu_tile_opt((u64)pool,sizeof(pool),g) && !services);}
    /* Real delayed completion, long-wait fallback, counter wrap, rate refusal. */
    seed(0);assert(start());test=33;complete_at=19200;
    assert(lmi_desktop_submit(addr,sizes,1)==1 && lmi_desktop_done(1) && !sleeping);
    seed(0);assert(start());test=33;complete_at=76800;
    assert(lmi_desktop_submit(addr,sizes,1)==1 && lmi_desktop_done(1) && sleeping);
    seed(0);counter=~(u64)0-1000;test=23;
    assert(!start() && storage.failed && sleeping==980);
    seed(0);counter_frequency=24000000;assert(!start() && !services && !queued);
    seed(0);assert(start());assert(!lmi_desktop_submit(addr,sizes,0));sizes[0]=0;assert(!lmi_desktop_submit(addr,sizes,1));
    lmi_desktop_stop();assert(lmi_desktop_ready() && storage.failed && !lmi_desktop_recover());
    puts("PASS: adoption guards, independent DMA type7/parity decoding, 40x128 IBs with ring wrap, cache ordering, CB1/ASID2 invalidation, queued fault fences, held releases, opt-in publication");
}
