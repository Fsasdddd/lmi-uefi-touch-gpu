SECTIONS {
.slot2 0xfffffff0074d8860 : { KEEP(*(.text.lmi_render_delay)) KEEP(*(.text.lmi_render_cleanup)) KEEP(*(.text.lmi_render_allocate)) }
.slot4 0xfffffff0074d90a4 : { KEEP(*(.rodata.str1.1)) }
 /DISCARD/ : { *(.comment .note* .llvm_addrsig) }
}
