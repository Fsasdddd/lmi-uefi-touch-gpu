SECTIONS {
.slot2 0xfffffff0074d8860 : { KEEP(*(.text.lmi_wait_delay)) KEEP(*(.text.lmi_wait_allocate)) KEEP(*(.text.lmi_wait_cleanup)) }
.slot6 0xfffffff0074d9c68 : { KEEP(*(.rodata.str1.1)) }
 /DISCARD/ : { *(.comment .note* .llvm_addrsig) }
}
