/* Place the alignment anchor before link-time optimized functions. */
.section __TEXT_EXEC,__lmi_dpu
.p2align 14
.globl _lmi_dpu_read_snapshot
_lmi_dpu_read_snapshot:
    mov w0, #0
    ret
/* Preserve the two frozen globals, then use only 24 bytes of their existing
 * 32-byte tail padding. Explicit order avoids compiler global reordering and
 * scalar replacement moving the old kernel's BSS or data symbols. */
.section __DATA,__lmi_dpu
.p2align 3
.globl _display_map, _display_samples, _state
_display_map:
    .quad 0
_display_samples:
    .quad 0
_state:
    .space 24
