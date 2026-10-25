#ifndef LMI_GPU_RESOURCES_H
#define LMI_GPU_RESOURCES_H
typedef unsigned int arc_u32;
typedef unsigned short arc_u16;
struct lmi_arc_resource {
    arc_u32 address,count,min_svs_index;
    arc_u16 levels[16];
};
int lmi_gpu_arc_parse(const void *,arc_u32,const char *,struct lmi_arc_resource *);
int lmi_gpu_arc_inventory(void);
#endif
