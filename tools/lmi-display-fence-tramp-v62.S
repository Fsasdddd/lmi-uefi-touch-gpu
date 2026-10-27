.section .text.lmi_fence_original_method,"ax",@progbits
.p2align 2
.global lmi_fence_original_method
lmi_fence_original_method:
    sub sp, sp, #0xd0
    b lmi_fence_method_tail
.section .text.lmi_fence_original_close,"ax",@progbits
.p2align 2
.global lmi_fence_original_close
lmi_fence_original_close:
    stp x20, x19, [sp, #-0x20]!
    b lmi_fence_close_tail
.section .text.lmi_fence_finish_tramp,"ax",@progbits
.p2align 2
.global lmi_fence_finish_tramp
lmi_fence_finish_tramp:
    mov x0, x19
    b lmi_fence_finish
