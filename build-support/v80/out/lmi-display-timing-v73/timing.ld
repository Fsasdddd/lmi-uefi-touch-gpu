SECTIONS {
.slot1 0xfffffff0074d7b44 : { KEEP(*(.text.OUTLINED_FUNCTION_0)) }
.slot5 0xfffffff0074d86e4 : { KEEP(*(.text.lmi_timing_cleanup)) KEEP(*(.text.lmi_timing_source)) KEEP(*(.text.lmi_timing_allocate)) }
.slot8 0xfffffff0074d8e78 : { KEEP(*(.text.OUTLINED_FUNCTION_1)) }
.slot12 0xfffffff0074d9890 : { KEEP(*(.rodata.str1.1)) }
.slot13 0xfffffff0074d9934 : { KEEP(*(.text.lmi_timing_submit)) KEEP(*(.text.lmi_timing_frame)) KEEP(*(.text.sample)) }
 /DISCARD/ : { *(.comment .note* .llvm_addrsig) }
}
