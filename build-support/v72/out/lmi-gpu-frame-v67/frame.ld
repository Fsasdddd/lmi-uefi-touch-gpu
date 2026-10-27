SECTIONS {
.slot0 0xfffffff0074d7878 : { KEEP(*(.text.eligible)) KEEP(*(.text.OUTLINED_FUNCTION_0)) }
.slot1 0xfffffff0074d79dc : { KEEP(*(.text.source_mapping)) KEEP(*(.rodata.str1.1)) }
.slot6 0xfffffff0074d8a94 : { KEEP(*(.text.lmi_gpu_frame_clean)) KEEP(*(.text.lmi_gpu_frame_allocate)) }
.slot7 0xfffffff0074d8b98 : { KEEP(*(.text.commands)) KEEP(*(.text.command_mapping)) KEEP(*(.text.lmi_gpu_frame_frame)) KEEP(*(.text.lmi_gpu_frame_cleanup)) }
.slot8 0xfffffff0074d8d88 : { KEEP(*(.text.lmi_gpu_frame_draw)) }
.slot11 0xfffffff0074d94fc : { KEEP(*(.text.mapping)) KEEP(*(.text.uncertain)) }
.slot14 0xfffffff0074db054 : { KEEP(*(.text.copy)) }
 /DISCARD/ : { *(.comment .note* .llvm_addrsig) }
}
