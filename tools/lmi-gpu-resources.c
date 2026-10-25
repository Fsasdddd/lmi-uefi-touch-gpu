/* Read-only command DB ARC inventory. Never issues an RPMh request.
 * Layout: vendor cmd-db.c; AUX semantics: rpmh-regulator.c1263+. */
#include "lmi-gpu-resources.h"
typedef unsigned long long arc_u64;
extern arc_u64 io_map_memory(arc_u64,arc_u64);
extern void log_line(const char *);
extern void log_hex(arc_u64);
static arc_u32 le16(const unsigned char *p) {return p[0]|((arc_u32)p[1]<<8);}
static arc_u32 le32(const unsigned char *p) {return le16(p)|(le16(p+2)<<16);}
static int span(arc_u32 at,arc_u32 count,arc_u32 bytes) {return at<=bytes && count<=bytes-at;}
int lmi_gpu_arc_parse(const void *memory,arc_u32 bytes,const char *id,struct lmi_arc_resource *out) {
    const unsigned char *db=memory;
    if(!db || !out || !id || bytes<144 || bytes>0x20000 || le32(db+4)!=0x0c0330db)return 0;
    struct lmi_arc_resource r={0};arc_u32 found=0;
    for(arc_u32 s=0;s<8;s++) {
        const unsigned char *h=db+8+16*s;
        if(le16(h)!=3)continue;
        arc_u32 at=144+le16(h+2),count=le16(h+6),data=144+le16(h+4);
        if(count>512 || !span(at,count*24,bytes))return 0;
        for(arc_u32 j=0;j<count;j++) {
            const unsigned char *e=db+at+24*j;
            arc_u32 equal=1;
            for(arc_u32 k=0;k<8;k++)equal&=e[k]==(unsigned char)id[k];
            if(!equal)continue;
            if(found++)return 0;
            arc_u32 len=le16(e+20),aux=data+le16(e+22);
            r.address=le32(e+16);
            if(!r.address || (r.address&3) || ((r.address>>16)&7)!=3 ||
               !len || len>32 || (len&1) || !span(aux,len,bytes))return 0;
            arc_u32 padding=0;
            for(arc_u32 n=0;n<len/2;n++) {
                arc_u32 level=le16(db+aux+2*n);
                if(!n && level)return 0;
                if(n && !level)padding=1;
                if(padding) {if(level)return 0;continue;}
                if(n && level<=r.levels[n-1])return 0;
                r.levels[n]=(arc_u16)level;r.count++;
                if(level>=48 && !r.min_svs_index)r.min_svs_index=n;
            }
            if(r.count<2 || !r.min_svs_index)return 0;
        }
    }
    if(found!=1)return 0;
    *out=r;return 1;
}
static void field(const char *s,arc_u64 v) {log_line(s);log_hex(v);}
int lmi_gpu_arc_inventory(void) {
    const unsigned char *db=(const void *)io_map_memory(0x80860000,0x20000);
    struct lmi_arc_resource resources[2];
    if(!lmi_gpu_arc_parse(db,0x20000,"cx.lvl\0",&resources[0]) ||
       !lmi_gpu_arc_parse(db,0x20000,"mx.lvl\0",&resources[1]) ||
       resources[0].address==resources[1].address) {
        log_line("LMI_GPU_ARC_REFUSED\n");return 0;
    }
    field("LMI_GPU_ARC_DB_VERSION\n",le32(db));
    for(arc_u32 n=0;n<2;n++) {
        const struct lmi_arc_resource *r=&resources[n];
        field("LMI_GPU_ARC_RESOURCE\n",n);
        field("LMI_GPU_ARC_ADDRESS\n",r->address);
        field("LMI_GPU_ARC_MIN_SVS_SELECTOR\n",r->min_svs_index);
        for(arc_u32 k=0;k<r->count;k++) {
            field("LMI_GPU_ARC_SELECTOR\n",k);
            field("LMI_GPU_ARC_LEVEL\n",r->levels[k]);
        }
    }
    log_line("LMI_GPU_ARC_INVENTORY_OK\n");return 1;
}
#ifdef LMI_GPU_RPMH_PROBE
extern int lmi_gpu_rscc_min_votes(volatile arc_u32 *,const struct lmi_arc_resource *,const struct lmi_arc_resource *);
int lmi_gpu_arc_min_votes(volatile arc_u32 *rscc) {
    const void *db=(const void *)io_map_memory(0x80860000,0x20000);
    struct lmi_arc_resource cx,mx;
    if(!lmi_gpu_arc_parse(db,0x20000,"cx.lvl\0",&cx) ||
       !lmi_gpu_arc_parse(db,0x20000,"mx.lvl\0",&mx))return 0;
    return lmi_gpu_rscc_min_votes(rscc,&cx,&mx);
}
#endif
