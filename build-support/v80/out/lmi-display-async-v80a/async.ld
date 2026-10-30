SECTIONS { .async 0xfffffff0074d138c : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.comment .note* .llvm_addrsig) } }
