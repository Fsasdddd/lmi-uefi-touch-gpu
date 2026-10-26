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
