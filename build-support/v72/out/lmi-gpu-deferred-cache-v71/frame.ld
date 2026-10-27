SECTIONS {
.slot0 0xfffffff0074d7878 : { KEEP(*(.text.full_frame)) KEEP(*(.text.OUTLINED_FUNCTION_1)) }
.slot1 0xfffffff0074d79dc : { KEEP(*(.text.eligible)) KEEP(*(.text.uncertain)) }
.slot2 0xfffffff0074d7b54 : { KEEP(*(.text.lmi_blit_commands)) KEEP(*(.text.OUTLINED_FUNCTION_3)) }
.slot4 0xfffffff0074d83dc : { KEEP(*(.text.finish)) KEEP(*(.text.save_restore)) }
.slot6 0xfffffff0074d8a94 : { KEEP(*(.text.mapping)) }
.slot7 0xfffffff0074d8b98 : { KEEP(*(.text.lmi_gpu_frame_frame)) KEEP(*(.text.command_mapping)) }
.slot8 0xfffffff0074d8d88 : { KEEP(*(.text.cpu_access)) KEEP(*(.text.OUTLINED_FUNCTION_2)) KEEP(*(.text.OUTLINED_FUNCTION_5)) }
.slot9 0xfffffff0074d8e88 : { KEEP(*(.text.source_mapping)) KEEP(*(.text.lmi_gpu_frame_draw)) }
.slot11 0xfffffff0074d94fc : { KEEP(*(.text.lmi_gpu_frame_cleanup)) KEEP(*(.text.lmi_gpu_frame_allocate)) KEEP(*(.text.OUTLINED_FUNCTION_4)) }
.slot12 0xfffffff0074d962c : { KEEP(*(.text.lmi_gpu_frame_clean)) KEEP(*(.rodata.str1.1)) KEEP(*(.text.lmi_blit_completed)) KEEP(*(.text.p7)) KEEP(*(.rodata.ranges)) KEEP(*(.text.event)) }
.slot14 0xfffffff0074db054 : { KEEP(*(.text.copy)) KEEP(*(.text.OUTLINED_FUNCTION_0)) }
 /DISCARD/ : { *(.comment .note* .llvm_addrsig) }
}
