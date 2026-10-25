#ifndef LMI_GPU_HFI_TRANSFER_H
#define LMI_GPU_HFI_TRANSFER_H
struct lmi_hfi_trace {const char *request,*reply,*verified;};
int lmi_gpu_hfi_exchange(unsigned long long,unsigned int,volatile unsigned int *,const unsigned int *,unsigned int,unsigned int,unsigned int,const struct lmi_hfi_trace *);
#endif
