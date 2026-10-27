/* Appended to the frozen pixel fixture, using the real v64 backend and
 * original compositor/pipeline. Device memory is separate from CPU memory. */
#define LMI_GPU_POLL_HOST
#include "lmi-gpu-desktop-v64.c"
#include "lmi-gpu-deferred-cache-v71.h"
#include <setjmp.h>
struct desktop_space desktop_space;
u64 desktop_slot[3],desktop_free[1024][2],g_phys_base=0x80000000,g_phys_size=0x70000000;
u32 desktop_free_count;
static struct desk_state backend;
static unsigned char pool[81920] __attribute__((aligned(4096))),pool_dma[81920];
static u32 gpu[0x10000],smmu[0x4000],gmu[0xc000];
static uint64_t page[1<<20],next_va,clock_ticks;
static unsigned char rights[1<<20];
static unsigned locked,map_calls,unmaps,refs,unrefs,clean_calls,bells,fault,scenarios;
static unsigned pending,execute_reads,decodes,frame_emit_count,one_fence,inject_tail,tail_calls;
static unsigned char other_command[4096] __attribute__((aligned(4096)));
static jmp_buf escape;
static struct {
    uintptr_t cpu;unsigned char *dma,*expected,*clean;size_t size;uint64_t pa;
} memory[64];
static unsigned memory_count;
static void register_memory(void *p,size_t bytes)
{
    assert(memory_count<64 && !((uintptr_t)p&4095) && !(bytes&4095));
    unsigned i=memory_count++;memory[i].cpu=(uintptr_t)p;memory[i].size=bytes;
    memory[i].dma=malloc(bytes);assert(memory[i].dma);memcpy(memory[i].dma,p,bytes);
    memory[i].expected=malloc(bytes);assert(memory[i].expected);memcpy(memory[i].expected,p,bytes);
    memory[i].clean=malloc(bytes);assert(memory[i].clean);memcpy(memory[i].clean,p,bytes);
    memory[i].pa=i?memory[i-1].pa+memory[i-1].size:0x80000000;
}
static unsigned region(uintptr_t p,size_t n)
{for(unsigned i=0;i<memory_count;i++)if(p>=memory[i].cpu && p-memory[i].cpu<=memory[i].size && n<=memory[i].size-(p-memory[i].cpu))return i;assert(!"unowned memory");return 0;}
static unsigned char *physical(uint64_t pa,size_t n)
{for(unsigned i=0;i<memory_count;i++)if(pa>=memory[i].pa && pa-memory[i].pa<=memory[i].size && n<=memory[i].size-(pa-memory[i].pa))return memory[i].dma+pa-memory[i].pa;assert(!"invalid physical page");return 0;}
static void transfer(uint64_t dst,uint64_t src,size_t n)
{
    while(n) {
        assert(dst<0x100000000ull && src<0x100000000ull && page[dst>>12] && page[src>>12] && !rights[dst>>12]);
        size_t take=4096-(src&4095);if(take>4096-(dst&4095))take=4096-(dst&4095);if(take>n)take=n;
        memcpy(physical(page[dst>>12]+(dst&4095),take),physical(page[src>>12]+(src&4095),take),take);
        src+=take;dst+=take;n-=take;
    }
}
/* Evict dirty CPU cachelines AFTER the 2D write, as may happen on real
 * noncoherent hardware. Clean cached reads must not overwrite GPU memory. */
static void evict_dirty(uint64_t dst)
{
    uint64_t pa=page[dst>>12]+(dst&4095);
    for(unsigned i=0;i<memory_count;i++)if(pa==memory[i].pa) {
        assert(memory[i].size>=BYTES);
        for(size_t at=0;at<BYTES;at+=64) {
            if(memcmp((void *)(memory[i].cpu+at),memory[i].clean+at,64)) {
                memcpy(memory[i].dma+at,(void *)(memory[i].cpu+at),64);
                memcpy(memory[i].clean+at,(void *)(memory[i].cpu+at),64);
            }
        }
        return;
    }
    assert(!"target physical allocation missing");
}
static uint32_t fetch(uint64_t addr)
{assert(!(addr&3) && addr<0x100000000ull && page[addr>>12]);uint32_t v;memcpy(&v,physical(page[addr>>12]+(addr&4095),4),4);return v;}
/* Decode independent PM4 fields (Mesa XML), never call the builder to
 * determine expected packets or pixels. Model CCU writes as pending until
 * FLUSH_COLOR_TS, distinct CPU/DMA bytes, and register state preservation. */
static void gpu_store(uint64_t address,uint32_t value)
{
    assert(address<0x100000000ull && !(address&3) && page[address>>12] && !rights[address>>12]);
    memcpy(physical(page[address>>12]+(address&4095),4),&value,4);
}
static void execute_ib(uint64_t addr,uint32_t words)
{
    if(words==1) {assert(fetch(addr)==0x70268000);return;} /* unrelated producer IB */
    uint32_t reg[65536],original[65536];
    for(unsigned i=0;i<65536;i++)reg[i]=original[i]=(i*0x45d9f3bu)^0xa5a55a5a;
    unsigned at=0,saved=0,restored=0,readback=0,blits=0,flushed=0,cache=0,idle=0,writes=0,events=0;
    uint64_t state=0;unsigned state_offset=0;
    while(at<words) {
        uint32_t h=fetch(addr+4*at++),count;
        if(h>>28==4) {
            count=h&127;unsigned r=(h>>8)&0x7ffff;
            assert(count && r+count<=65536 && ((h>>7)&1)==(1^__builtin_parity(count)) &&
                   ((h>>27)&1)==(1^__builtin_parity(r)) && at+count<=words && !restored);
            for(unsigned i=0;i<count;i++)reg[r+i]=fetch(addr+4*(at+i));
        } else {
            assert(h>>28==7);count=h&0x3fff;unsigned op=(h>>16)&127;
            assert(((h>>15)&1)==(1^__builtin_parity(count)) && ((h>>23)&1)==(1^__builtin_parity(op)) && at+count<=words);
            if(op==0x3e || op==0x42) {
                assert(count==3);uint32_t v=fetch(addr+4*at),r=v&0x3ffff;
                unsigned nr=(v>>(op==0x3e?18:19))& (op==0x3e?0xfff:0x7ff);
                uint64_t dest=fetch(addr+4*(at+1))|((uint64_t)fetch(addr+4*(at+2))<<32);
                assert(nr && r+nr<=65536);
                if(op==0x3e) {
                    if(restored) {
                        assert(restored==7 && dest==state+256+4*readback);
                        for(unsigned i=0;i<nr;i++)gpu_store(dest+4*i,reg[r+i]);readback+=nr;
                    } else {
                        assert(!blits);if(!saved)state=dest;
                        assert(dest==state+state_offset);state_offset+=nr*4;
                        for(unsigned i=0;i<nr;i++)gpu_store(dest+4*i,reg[r+i]);saved++;
                    }
                } else {
                    assert(blits==1 && flushed && events==4 && writes>=2);
                    for(unsigned i=0;i<nr;i++)reg[r+i]=fetch(dest+4*i);restored++;
                }
            } else if(op==0x26) {assert(!count);idle++;}
            else if(op==0x12) {assert(!count);writes++;}
            else if(op==0x46) {
                uint32_t kind=fetch(addr+4*at);
                if(count==1) {assert(kind==0x18 || kind==0x19 || kind==0x31);if(kind==0x31)cache=idle;}
                else {
                    assert(count==4 && saved==7 && writes);
                    uint64_t dest=fetch(addr+4*(at+1))|((uint64_t)fetch(addr+4*(at+2))<<32);
                    uint32_t value=fetch(addr+4*(at+3));
                    assert(dest==state+128+4*events && value==0x680c0101u+events && events<4);
                    assert(kind==(events==0 || events==2?0x1d:events==1?0x1c:4));
                    if(events==2) {
                        assert(blits==1 && !flushed);
                        uint64_t src=reg[0xb4c2]|((uint64_t)reg[0xb4c3]<<32),dst=reg[0x8c18]|((uint64_t)reg[0x8c19]<<32);
                        unsigned pitch=(reg[0xb4c4]>>9)*64;
                        for(unsigned y=0;y<(reg[0xb4c1]>>15);y++)transfer(dst+y*4544,src+(uint64_t)y*pitch,4544);
                        evict_dirty(dst);flushed=1;
                    }
                    if(fault!=11)gpu_store(dest,value);events++;
                }
            } else {
                assert(op==0x2c && count==1 && fetch(addr+4*at)==3 && saved==7 && !restored && !blits++);
                assert(writes && cache && idle>cache && events==2 && reg[0x8e07]==0x18000000 && reg[0x8e04]==0x04100000);
                assert(reg[0x8400]==0x10f03000 && reg[0x8c00]==0x10f03000 && !reg[0x8c01] && reg[0xacc0]==0xf180);
                assert(!reg[0x8401] && reg[0x8402]==1135u<<8 && !reg[0x8403] && reg[0x8404]==2435u<<8 &&
                       !reg[0x8405] && reg[0x8406]==(1135u|(2435u<<16)));
                assert(reg[0xb4c0]==0x500030 && reg[0xb4c1]==(1136u|(2436u<<15)) && !(reg[0xb4c4]&511));
                assert((reg[0xb4c4]>>9)==71 || (reg[0xb4c4]>>9)==72);
                assert(reg[0x8c17]==0x30 && reg[0x8c1a]==71);
            }
        }
        at+=count;decodes++;
    }
    assert(blits==1 && flushed && saved==7 && restored==7 && readback==21 && events==4 && !memcmp(reg,original,sizeof(reg)));
}
static void execute_ring(void)
{
    uint32_t at=gpu[0x806],end=gpu[0x807],events=0,ibs=0,idle=0;
    const uint32_t *ring=(void *)pool_dma;
    while(at!=end) {
        uint32_t h=ring[at],count=h&0x3fff,op=(h>>16)&127,arg[4]={0};at=(at+1)&8191;
        assert(h>>28==7 && ((h>>15)&1)==(1^__builtin_parity(count)) && ((h>>23)&1)==(1^__builtin_parity(op)) && count<=4);
        for(unsigned i=0;i<count;i++) {assert(at!=end);arg[i]=ring[at];at=(at+1)&8191;}
        if(op==0x46 && count==1) {assert(events<2 && arg[0]==0x18+events);events++;}
        else if(op==0x3f) {assert(count==3 && events==2 && !arg[1]);execute_ib(arg[0],arg[2]);ibs++;}
        else if(op==0x26) {assert(!count && ibs && !idle++);}
        else {assert(op==0x46 && count==4 && arg[0]==4 && arg[1]==0x1010040 && !arg[2] && events==2 && idle==1 && ibs);
            if(fault!=6)((uint32_t *)(pool_dma+65536))[16]=arg[3];
            if(one_fence) {gpu[0x806]=at;pending=at!=end;return;}
            events=ibs=idle=0;
        }
    }
    gpu[0x806]=end;pending=0;
}
void *lmi_frame_gpu_lock=(void *)1;
void IOLockLock(void *p) {assert(p==(void *)1 && !locked);locked=1;}
void IOLockUnlock(void *p) {assert(p==(void *)1 && locked);locked=0;}
struct lmi_v66_desk *lmi_frame_backend(void) {assert(locked);return (void *)&backend;}
int lmi_frame_done(uint32_t fence) {assert(locked);return lmi_desktop_done(fence);}
int drain_all(struct lmi_v66_desk *d) {assert(locked && d==(void *)&backend);return drain(&backend);}
void lmi_frame_pause(uint32_t n,uint32_t unit) {assert(!locked);delay(n,unit);}
_Noreturn void lmi_frame_hold(struct lmi_v66_desk *d) {assert(d==(void *)&backend);hold(&backend);abort();}
uint64_t lmi_frame_ticks(void) {return ++clock_ticks;}
uint64_t lmi_frame_physical(uintptr_t p)
{assert(locked);unsigned i=region(p,4096);return fault==2 && map_calls==5?0:memory[i].pa+p-memory[i].cpu;}
void lmi_frame_retain(const void *p) {assert(locked && p);refs++;}
void lmi_frame_release(const void *p) {assert(locked && p && refs>unrefs);unrefs++;}
uint64_t redwood_gpu_address(uint64_t bytes)
{assert(locked && bytes);if(fault==1)return 0;uint64_t at=next_va;next_va+=(bytes+65535)&~65535ull;assert(next_va<0xf0000000);return at;}
void redwood_gpu_address_free(uint64_t addr,uint64_t bytes)
{assert(locked && addr>=0x20000000 && bytes);for(uint64_t i=0;i<bytes;i+=4096)assert(!page[(addr+i)>>12]);}
int legacy_space_map(struct desktop_space *d,u64 addr,u64 pa,u64 attr)
{
    assert(locked && d==&desktop_space && addr>=0x20000000 && addr<0x100000000ull && !(addr&4095));
    if(pa) {assert(attr==0xe40 || attr==0xec0);map_calls++;if((fault==3 && map_calls==6) ||
        (fault==10 && map_calls==LMI_DMA_BUFFER_BYTES/4096+22))return 0;assert(!page[addr>>12]);}
    else {assert(!attr);unmaps++;}
    page[addr>>12]=pa;rights[addr>>12]=!!(attr&128);return 1;
}
int cache_sync(u64 p,u32 n,int publish)
{
    if(p>=(u64)pool && p+n<=(u64)pool+sizeof(pool)) {
        size_t at=p-(u64)pool;if(publish)memcpy(pool_dma+at,pool+at,n);else memcpy(pool+at,pool_dma+at,n);return 1;
    }
    unsigned i=region((uintptr_t)p,n);size_t at=p-memory[i].cpu;
    struct lmi_gpu_frame_stats *owned=(void *)lmi_fast_state;
    for(unsigned target=0;target<2;target++)if(p==owned->target[target].pixels && n>=LMI_DMA_BUFFER_BYTES && (owned->gpu_owned_mask&(1u<<target))) {
        assert(!publish);if(fault==13)return 0;
    }
    if(fault==4 && publish && n<65536)return 0;
    if(fault==7 && !publish && bells)return 0;
    if(fault==12 && !publish && bells && n==4096)memory[i].dma[at+256]^=1;
    if(publish)memcpy(memory[i].dma+at,(void *)(uintptr_t)p,n);else memcpy((void *)(uintptr_t)p,memory[i].dma+at,n);
    memcpy(memory[i].clean+at,(void *)(uintptr_t)p,n);
    return 1;
}
u32 rsc_read(volatile u32 *p)
{if(pending && p==gpu+0x806 && ++execute_reads>=(fault==8?32u:3u))execute_ring();return *p;}
void rsc_write(volatile u32 *p,u32 v)
{
    if(p==gpu+0x807) {*p=v;bells++;if(fault==5)gpu[0x821]=1;else if(fault!=9) {if(!pending)execute_reads=0;pending=1;}}
    else {*p=v;assert((p==smmu+0x9610/4 && v==2) || (p==smmu+0x97f0/4 && !v));}
}
void delay(u32 n,u32 unit)
{assert(unit==1000);clock_ticks+=n*20;if(backend.failed)longjmp(escape,1);}
u64 lmi_gpu_counter(void) {return clock_ticks+=192;}
u64 lmi_gpu_counter_frequency(void) {return 19200000;}
void lmi_gpu_publish_barrier(void) {assert(locked);}
void log_line(const char *p) {(void)p;}
void log_hex(u64 n) {(void)n;}
u64 pa_of(u64 p) {return lmi_frame_physical(p);}
u64 io_map(u64 p,u64 n) {(void)p;(void)n;return 0;}
u64 absolute_time(void) {return clock_ticks;}
void *alloc_data(u64 n) {(void)n;return 0;}
int boot_arg(const char *p,void *o,int n) {(void)p;(void)o;(void)n;return 0;}
int lmi_gpu_cp_complete(volatile u32 *a,volatile u32 *b,volatile u32 *c,u32 n) {(void)a;(void)b;(void)c;(void)n;return 0;}
int lmi_gpu_tile(u64 p,u32 n,volatile u32 *g) {(void)p;(void)n;(void)g;return 0;}
void desktop_service_start(void) {assert(0);}
void lmi_display_smp_prepare(void) {}
uint64_t lmi_preclean_ticks(void) {return ++clock_ticks;}
int lmi_preclean_original_clean(void *opaque,const struct lmi_frame_buffer *b)
{(void)opaque;assert(!((struct lmi_gpu_frame_stats *)lmi_fast_state)->pending.fence);clean_calls++;return cache_sync(b->pixels,(u32)b->bytes,1);}
void lmi_preclean_emit(const char *tag,const uint64_t *p,unsigned n)
{assert(current->stop && !strcmp(tag,"LMI_DPU_PRECLEAN") && n==6 && p);}
void lmi_frame_emit(const char *tag,const uint64_t *p,unsigned n)
{assert(current->stop && !locked && p);
 const char *tags[]={"LMI_GPU_BLIT","LMI_GPU_BLIT_LIFETIME","LMI_GPU_TARGET_CACHE","LMI_GPU_COPY_OVERLAP","LMI_GPU_COPY_PENDING","LMI_GPU_CPU_TRANSFER","LMI_GPU_CPU_OWNED"};
 const unsigned counts[]={7,7,5,6,1,4,1};assert(frame_emit_count<7 && n==counts[frame_emit_count]);
 assert(!strcmp(tag,tags[frame_emit_count++]));}
static struct lmi_gpu_frame_stats *stats(void) {return (void *)lmi_fast_state;}
void *lmi_test_memcpy(void *dst,const void *src,size_t bytes)
{
    struct lmi_gpu_frame_stats *s=stats();
    for(unsigned n=0;n<2;n++)if(s->target[n].address) {
        uintptr_t start=s->target[n].pixels,end=start+LMI_DMA_BUFFER_BYTES;
        uintptr_t from=(uintptr_t)src,to=(uintptr_t)dst;
        if((from<end && start<from+bytes) || (to<end && start<to+bytes))assert(!(s->gpu_owned_mask&(1u<<n)));
    }
    return memcpy(dst,src,bytes);
}
/* Called only by test's allocator wrapper for the one command allocation. */
static void allocated(void *p,size_t n) {if(n==8192)register_memory(p,n);}
static struct lmi_display_dma device;
static struct fixture *make_gpu(unsigned pitch)
{
    memset(&backend,0,sizeof(backend));memset(&desktop_space,0,sizeof(desktop_space));memset(page,0,sizeof(page));
    memset(gpu,0,sizeof(gpu));memset(smmu,0,sizeof(smmu));memset(gmu,0,sizeof(gmu));
    memset(pool,0,sizeof(pool));memset(pool_dma,0,sizeof(pool_dma));memset(&device,0,sizeof(device));
    memory_count=locked=map_calls=unmaps=refs=unrefs=clean_calls=bells=fault=pending=execute_reads=decodes=frame_emit_count=0;
    one_fence=inject_tail=tail_calls=0;log_count=0;next_va=0x20000000;clock_ticks=0;
    backend.pool=(u64)pool;backend.gpu=gpu;backend.s=smmu;backend.g=gmu;
    backend.ready=1;backend.at=90;backend.done=backend.fence=1;
    gpu[0x806]=gpu[0x807]=90;gpu[0x210]=1;smmu[0x9058/4]=0x400;
    ((u32 *)(pool_dma+65536))[16]=1;
    desktop_slot[0]=(u64)&backend;desktop_slot[1]=0x4c4d494445534b31ull;desktop_slot[2]=~(u64)&backend;
    struct fixture *f=make();if(pitch!=4544)source(f,pitch,0);
    register_memory(f->allocation,(pitch*2436u+4095u)&~4095u);
    /* GPU has rendered different bytes; CPU source deliberately remains stale. */
    unsigned i=region((uintptr_t)f->source,1);
    for(unsigned y=0;y<2436;y++)for(unsigned x=0;x<pitch/4;x++)((uint32_t *)memory[i].dma)[y*(pitch/4)+x]^=0x13572468;
    memcpy(memory[i].expected,memory[i].dma,memory[i].size);
    sw(f->surface,LMI_SURF_drawn,1);
    free(lmi_fast_state);lmi_fast_state=lmi_gpu_frame_allocate(sizeof(struct lmi_fast_stats),16);assert(lmi_fast_state);
    device.prepared=1;
    for(unsigned n=0;n<2;n++) {
        free((void *)f->p.buffer[n].pixels);void *p=IOMallocAligned(LMI_DMA_BUFFER_BYTES+4096,4096);
        memset(p,0x31,LMI_DMA_BUFFER_BYTES+4096);memset((char *)p+BYTES,0xa5,GUARD);
        f->p.buffer[n].pixels=(uintptr_t)p;f->p.buffer[n].bytes=LMI_DMA_BUFFER_BYTES;
        device.buffer[n]=f->p.buffer[n];register_memory(p,LMI_DMA_BUFFER_BYTES+4096);
    }
    memset(other_command,0,sizeof(other_command));*(uint32_t *)other_command=0x70268000;
    register_memory(other_command,sizeof(other_command));
    page[0xf8000000u>>12]=memory[memory_count-1].pa;rights[0xf8000000u>>12]=1;
    f->p.context=&device;f->p.ops.clean=lmi_preclean_original_clean;return f;
}
static void native_tail(void)
{
    struct lmi_gpu_frame_stats *s=stats();
    if(!s->pending.fence)return;
    assert(!locked && !s->written && !s->credit && s->queued==s->finished+1);
    assert(backend.done<s->pending.fence); /* draw returned before GPU completion */
    tail_calls++;
    if(inject_tail) {
        /* A third-party queue writer takes the actual service lock while the
         * copy is pending. It must not need the presenter to release it. */
        u64 addr=0xf8000000u;uint32_t words=1;
        IOLockLock(lmi_frame_gpu_lock);assert(lmi_desktop_submit(&addr,&words,1)>s->pending.fence);
        IOLockUnlock(lmi_frame_gpu_lock);inject_tail=0;
    }
}
static int gpu_frame(struct fixture *f,void *surface,unsigned *n,uint64_t *ticket)
{void *surfaces[4]={surface,0,0,0};int result=lmi_gpu_frame_frame(&f->c,&f->p,f->swap,surfaces,n,ticket);assert(!stats()->pending.fence);return result;}
static void compare_gpu(struct fixture *f,unsigned n)
{
    unsigned si=region((uintptr_t)f->source,1),ti=region(f->p.buffer[n].pixels,1);
    assert(!memcmp(memory[si].dma,memory[si].expected,memory[si].size));
    for(unsigned y=0;y<2436;y++) {
        assert(!memcmp(memory[ti].dma+y*4544,memory[si].expected+y*f->source_pitch,4544));
    }
    assert(!memcmp((void *)(f->p.buffer[n].pixels+BYTES),memory[ti].dma+BYTES,LMI_DMA_BUFFER_BYTES+4096-BYTES));
}
static void finish(struct fixture *f,unsigned n,uint64_t ticket)
{assert(lmi_pipeline_submit(&f->p,n,ticket,0)==1);f->p.state[n]=LMI_FREE;f->p.scanning=-1;}
static void destroy_gpu(struct fixture *f)
{
    void *command=(void *)stats()->commands.pixels;
    for(unsigned i=0;i<memory_count;i++){free(memory[i].dma);free(memory[i].expected);free(memory[i].clean);}
    free(command);destroy(f);locked=0;
}
int main(void)
{
    unsigned n,m;uint64_t ticket;
    for(unsigned pitch=4544;pitch<=4608;pitch+=64) {
        struct fixture *f=make_gpu(pitch);
        assert(gpu_frame(f,f->surface,&n,&ticket)==1);compare_gpu(f,n);
        assert(stats()->frames==1 && stats()->draws==1 && !stats()->pre.original.copies && !clean_calls && stats()->skipped_clean==1);
        assert(stats()->bytes==BYTES && stats()->map_new==4 && refs==1 && !unrefs && !backend.mapping);
        finish(f,n,ticket);
        uint64_t pages=backend.map_pages;assert(gpu_frame(f,f->surface,&m,&ticket)==1);compare_gpu(f,m);finish(f,m,ticket);
        /* First free slot is reused: no mapping, allocation or retain per frame. */
        assert(backend.map_pages==pages && stats()->map_hits==1 && refs==1);
        for(unsigned i=0;i<10;i++){assert(gpu_frame(f,f->surface,&m,&ticket)==1);compare_gpu(f,m);finish(f,m,ticket);}
        assert(stats()->frames==12 && stats()->pre.original.frames==12 && !stats()->pre.original.copies);
        /* Real partial path reads the GPU-produced prior composition. */
        sw(f->swap,0x64,3);sw(f->swap,0x68,4);sw(f->swap,0x6c,2);sw(f->swap,0x70,2);
        uint32_t expected=((uint32_t *)memory[region(f->p.buffer[n].pixels,1)].dma)[2];f->source[2]=0xffbadbad;
        assert(gpu_frame(f,f->surface,&m,&ticket)==1 && f->draws==1 && clean_calls==1);
        assert(((uint32_t *)f->p.buffer[m].pixels)[2]==expected);
        finish(f,m,ticket);lmi_gpu_frame_cleanup();assert(frame_emit_count==7 && refs==1 && !unrefs);
        destroy_gpu(f);scenarios++;
    }
    /* GPU copies into B while A is still scanning; original pipeline refuses
     * to start B until the proven completion of A. A's pixels stay intact. */
    struct fixture *both=make_gpu(4608);
    assert(gpu_frame(both,both->surface,&n,&ticket)==1 && lmi_pipeline_submit(&both->p,n,ticket,0)==1);
    unsigned char *saved=malloc(BYTES);assert(saved);memcpy(saved,memory[region(both->p.buffer[n].pixels,1)].dma,BYTES);
    assert(gpu_frame(both,both->surface,&m,&ticket)==1 && n!=m && stats()->target[0].address && stats()->target[1].address);
    compare_gpu(both,m);assert(!memcmp(saved,memory[region(both->p.buffer[n].pixels,1)].dma,BYTES));free(saved);
    assert(lmi_pipeline_submit(&both->p,m,ticket,0)==0 && stats()->pre.pending==1);
    both->p.state[n]=LMI_FREE;both->p.scanning=-1;finish(both,m,ticket);destroy_gpu(both);scenarios++;
    /* GPU-clean credit is single use and cannot bypass the frozen descriptor,
     * ticket or lifetime checks, even when explicitly presented twice. */
    for(unsigned mode=0;mode<5;mode++) {
        struct fixture *q=make_gpu(4544);assert(gpu_frame(q,q->surface,&n,&ticket)==1);
        stats()->credit=1;
        if(mode==1)stats()->pre.ticket++;
        if(mode==2)q->p.buffer[n].width++;
        if(mode==3)device.restoring=1;
        if(mode==4)stats()->completed_target++;
        unsigned before=clean_calls;
        assert(lmi_gpu_frame_clean(&device,&stats()->pre.buffer)==1);
        assert(!stats()->credit && clean_calls==before+(mode?1:0));
        assert(lmi_gpu_frame_clean(&device,&stats()->pre.buffer)==1 && clean_calls==before+(mode?2:1));
        q->p.buffer[n]=device.buffer[n];destroy_gpu(q);scenarios++;
    }
    /* Failures before submission preserve the CPU fallback and mapping rollback. */
    for(unsigned mode=0;mode<6;mode++) {
        struct fixture *f=make_gpu(4608);
        if(mode<4)fault=mode+1;
        if(mode==4)sw(f->surface,LMI_SURF_drawn,0);
        if(mode==5)sw(f->surface,LMI_SURF_info+0x1c,4608*2436); /* no full final owned page */
        assert(gpu_frame(f,f->surface,&n,&ticket)==1 && !stats()->frames && stats()->pre.original.copies==1 && !bells);
        assert(!backend.mapping && refs-unrefs==(mode==3?1u:0u));finish(f,n,ticket);destroy_gpu(f);scenarios++;
    }
    struct fixture *rollback=make_gpu(4608);fault=10;
    assert(gpu_frame(rollback,rollback->surface,&n,&ticket)==1 && !bells && refs==1 && unrefs==1 && !backend.mapping && unmaps);
    finish(rollback,n,ticket);destroy_gpu(rollback);scenarios++;
    /* A queued GPU fault, missing fence, post-invalidate failure or timeout
     * never returns to CPU copying, DPU start, release or caller unmapping. */
    for(unsigned mode=5;mode<=12;mode++) {
        struct fixture *f=make_gpu(4608);fault=mode==10?7:mode;
        if(mode==8) {assert(gpu_frame(f,f->surface,&n,&ticket)==1);compare_gpu(f,n);finish(f,n,ticket);}
        else {
            if(!setjmp(escape)) {gpu_frame(f,f->surface,&n,&ticket);assert(!"uncertain copy returned");}
            assert(stats()->held==1 && !stats()->pre.original.copies && !stats()->frames && !unrefs && refs==1 && !stats()->credit);
            /* RAM return is simulated only after asserting dependencies held. */
            lmi_fast_state->active=0;sp(f->fb,LMI_FB_fBase,(uintptr_t)f->gop);
            sp(f->fb,LMI_FB_fColumn,0x1234);sp(f->fb,LMI_FB_fColumnWeight,0x5678);locked=0;
        }
        destroy_gpu(f);scenarios++;
    }
    /* Source retention/eviction uses 10 different actual surface identities. */
    struct fixture *f=make_gpu(4544);void *allocations[10]={f->allocation};unsigned char *surfaces[10]={f->surface};
    for(unsigned i=0;i<10;i++) {
        if(i) {
            f->allocation=0;source(f,4544,0);allocations[i]=f->allocation;register_memory(f->allocation,(4544*2436u+4095)&~4095u);
            surfaces[i]=malloc(728);assert(surfaces[i]);memcpy(surfaces[i],f->surface,728);
        }
        sp(surfaces[i],LMI_SURF_kpixels,(uintptr_t)f->source);sw(surfaces[i],LMI_SURF_drawn,1);
        assert(gpu_frame(f,surfaces[i],&n,&ticket)==1);compare_gpu(f,n);finish(f,n,ticket);
    }
    assert(stats()->retained==10 && stats()->released==2 && stats()->evicted==2 && refs-unrefs==8);
    assert(unmaps>=2*((4544*2436u+4095)/4096));
    for(unsigned i=0;i<9;i++)free(allocations[i]);for(unsigned i=1;i<10;i++)free(surfaces[i]);destroy_gpu(f);scenarios++;
    /* Repeated reuse must remove two actual full-target cache traversals,
     * while leaving continuous GPU targets owned by DMA and CPU views stale. */
    struct fixture *cache=make_gpu(4544);
    for(unsigned i=0;i<8;i++) {
        assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    }
    assert(stats()->target_prepared==1 && stats()->target_reused==7 && stats()->clean_mask==1);
    assert(stats()->post_deferred==8 && !stats()->cpu_sync_targets && stats()->gpu_owned_mask==1);
    assert(memcmp((void *)cache->p.buffer[n].pixels,memory[region(cache->p.buffer[n].pixels,1)].dma,BYTES));
    assert(stats()->target_bytes_saved==14ull*LMI_DMA_BUFFER_BYTES && stats()->target_prepare_ticks>0);
    /* An aborted no-draw bottom-layer clear leaves dirty CPU lines. The next
     * GPU full frame must publish/invalidate them before its new writer. */
    cache->bad_join=1;
    assert(gpu_frame(cache,0,&n,&ticket)==-1 && !stats()->clean_mask);
    assert(lmi_pipeline_cancel_frame(&cache->p,n,ticket)==1);
    cache->bad_join=0;sw(cache->fb,LMI_FB_fHelpersBusy,0);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    assert(stats()->target_prepared==2 && stats()->dirty_resets==1);destroy_gpu(cache);scenarios++;
    /* Both buffers retain separate clean state; using B cannot grant A credit. */
    cache=make_gpu(4608);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1 && lmi_pipeline_submit(&cache->p,n,ticket,0)==1);
    assert(gpu_frame(cache,cache->surface,&m,&ticket)==1 && m!=n && stats()->target_prepared==2 && stats()->clean_mask==3);
    cache->p.state[n]=LMI_FREE;cache->p.scanning=-1;finish(cache,m,ticket);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    assert(stats()->target_prepared==2 && stats()->target_reused==1);destroy_gpu(cache);scenarios++;
    /* CPU partial fallback revokes ownership BEFORE the native row writer,
     * including failure before READY/preclean. Real cacheline eviction above
     * detects stale CPU writes overwriting the following GPU full frame. */
    cache=make_gpu(4544);assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);finish(cache,n,ticket);
    sw(cache->swap,0x64,3);sw(cache->swap,0x68,4);sw(cache->swap,0x6c,2);sw(cache->swap,0x70,2);
    cache->bad_join=1;assert(gpu_frame(cache,cache->surface,&n,&ticket)==-1 && !stats()->clean_mask);
    assert(lmi_pipeline_cancel_frame(&cache->p,n,ticket)==1);
    cache->bad_join=0;sw(cache->fb,LMI_FB_fHelpersBusy,0);
    sw(cache->swap,0x64,0);sw(cache->swap,0x68,0);sw(cache->swap,0x6c,0);sw(cache->swap,0x70,0);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    assert(stats()->target_prepared==2);destroy_gpu(cache);scenarios++;
    /* A failed frame after a completed GPU draw grants neither a cache epoch
     * nor display-clean credit to its successor. */
    cache=make_gpu(4544);cache->bad_join=1;
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==-1 && !stats()->clean_mask && !stats()->credit && !stats()->gpu_owned_mask);
    assert(lmi_pipeline_cancel_frame(&cache->p,n,ticket)==1);
    cache->bad_join=0;sw(cache->fb,LMI_FB_fHelpersBusy,0);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);finish(cache,n,ticket);
    assert(stats()->target_prepared==2 && !stats()->target_reused);destroy_gpu(cache);scenarios++;
    /* Keep an earlier producer job and a later producer job around our
     * copy. Only the copy's fence is joined: the later job is STILL busy when
     * the frame is READY/clean and the DPU may consume its private target. */
    cache=make_gpu(4608);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);finish(cache,n,ticket);
    assert(tail_calls==1 && stats()->queued==stats()->finished && !stats()->pending.fence);
    uint32_t before=backend.done;u64 address=0xf8000000u;uint32_t words=1;
    one_fence=1;IOLockLock(lmi_frame_gpu_lock);assert(lmi_desktop_submit(&address,&words,1)==before+1);IOLockUnlock(lmi_frame_gpu_lock);
    inject_tail=1;
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);compare_gpu(cache,n);
    assert(tail_calls==2 && stats()->queued==2 && stats()->finished==2 && stats()->later_queued==1);
    assert(stats()->wait_polls>=stats()->finished && stats()->busy_polls && stats()->unlocked_ticks);
    assert(backend.done==before+2 && backend.fence==before+3 && pending && !stats()->pending.fence && !locked);
    finish(cache,n,ticket);
    IOLockLock(lmi_frame_gpu_lock);assert(drain(&backend));IOLockUnlock(lmi_frame_gpu_lock);
    destroy_gpu(cache);scenarios++;
    /* A full-frame admission can still fall back after source-fence/map
     * refusal. Ownership must transfer BEFORE the CPU draw writes. */
    cache=make_gpu(4544);assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);finish(cache,n,ticket);
    sw(cache->surface,LMI_SURF_drawn,0);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1 && stats()->pre.original.copies==1);
    assert(stats()->cpu_sync_targets==1 && !stats()->gpu_owned_mask);finish(cache,n,ticket);destroy_gpu(cache);scenarios++;
    /* A partial frame needs both the newest prior GPU composition AND the
     * old target's CPU view before original compositor preservation begins. */
    cache=make_gpu(4608);assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);
    assert(lmi_pipeline_submit(&cache->p,n,ticket,0)==1);
    assert(gpu_frame(cache,cache->surface,&m,&ticket)==1 && n!=m && stats()->gpu_owned_mask==3);
    cache->p.state[n]=LMI_FREE;cache->p.scanning=-1;finish(cache,m,ticket);
    sw(cache->swap,0x64,3);sw(cache->swap,0x68,4);sw(cache->swap,0x6c,2);sw(cache->swap,0x70,2);
    assert(gpu_frame(cache,cache->surface,&n,&ticket)==1 && stats()->cpu_sync_targets==2 && !stats()->gpu_owned_mask);
    finish(cache,n,ticket);destroy_gpu(cache);scenarios++;
    /* Refuse failed CPU ownership transfer; no stale CPU fallback or DPU. */
    cache=make_gpu(4544);assert(gpu_frame(cache,cache->surface,&n,&ticket)==1);finish(cache,n,ticket);
    sw(cache->swap,0x64,3);sw(cache->swap,0x68,4);sw(cache->swap,0x6c,2);sw(cache->swap,0x70,2);fault=13;
    if(!setjmp(escape)) {gpu_frame(cache,cache->surface,&n,&ticket);assert(!"CPU ownership failure returned");}
    assert(stats()->held==1 && stats()->gpu_owned_mask && !stats()->pre.original.copies);
    lmi_fast_state->active=0;sp(cache->fb,LMI_FB_fBase,(uintptr_t)cache->gop);
    sp(cache->fb,LMI_FB_fColumn,0x1234);sp(cache->fb,LMI_FB_fColumnWeight,0x5678);locked=0;
    destroy_gpu(cache);scenarios++;
    printf("PASS: %u integrated GPU-2D-frame scenarios, full/strided pixels, persistent mappings, CPU partial fallback, retained/evicted sources, held DMA faults\n",scenarios);
}
