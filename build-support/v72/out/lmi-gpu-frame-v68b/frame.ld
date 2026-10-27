SECTIONS {
.slot0 0xfffffff0074d7878 : { KEEP(*(.text.eligible)) KEEP(*(.text.OUTLINED_FUNCTION_1)) }
.slot1 0xfffffff0074d79dc : { KEEP(*(.text.source_mapping)) KEEP(*(.rodata.str1.1)) KEEP(*(.text.OUTLINED_FUNCTION_2)) }
.slot2 0xfffffff0074d7b54 : { KEEP(*(.text.lmi_blit_commands)) }
.slot4 0xfffffff0074d83dc : { KEEP(*(.text.copy)) }
.slot6 0xfffffff0074d8a94 : { KEEP(*(.text.mapping)) }
.slot7 0xfffffff0074d8b98 : { KEEP(*(.text.command_mapping)) KEEP(*(.text.save_restore)) KEEP(*(.text.lmi_gpu_frame_frame)) KEEP(*(.rodata.ranges)) KEEP(*(.text.OUTLINED_FUNCTION_0)) }
.slot8 0xfffffff0074d8d88 : { KEEP(*(.text.lmi_gpu_frame_draw)) KEEP(*(.text.p7)) }
.slot9 0xfffffff0074d8e88 : { KEEP(*(.text.lmi_gpu_frame_cleanup)) KEEP(*(.text.lmi_gpu_frame_allocate)) KEEP(*(.text.event)) KEEP(*(.text.uncertain)) }
.slot11 0xfffffff0074d94fc : { KEEP(*(.text.lmi_gpu_frame_clean)) KEEP(*(.text.lmi_blit_completed)) }
 /DISCARD/ : { *(.comment .note* .llvm_addrsig) }
}
