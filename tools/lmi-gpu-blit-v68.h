#ifndef LMI_GPU_BLIT_V68_H
#define LMI_GPU_BLIT_V68_H
#include <stdint.h>
#define LMI_BLIT_COMMAND_BYTES 4096u
#define LMI_BLIT_STATE_BYTES 4096u
#define LMI_BLIT_MARKER_OFFSET 128u
#define LMI_BLIT_MARKER_COUNT 4u
#define LMI_BLIT_READBACK_OFFSET 256u
#define LMI_BLIT_REGISTER_COUNT 21u
/* Fixed 1136x2436 raw RGBA8 copy includes the same eleven padding pixels as
 * the CPU path. The visible image remains 1125x2436. No format conversion. */
uint32_t lmi_blit_commands(uint32_t *,uint64_t,uint64_t,uint64_t,uint32_t);
int lmi_blit_completed(const volatile uint32_t *);
#endif
