SECTIONS {
.slot0 0xfffffff0074d0a7c : { KEEP(lmi-cpu-epss-native.o(.text.lmi_epss_native_init)) KEEP(lmi-cpu-epss.o(.text.lmi_epss_prepare)) KEEP(lmi-cpu-epss-native.o(.text.native_barrier)) }
.slot1 0xfffffff0074d0e00 : { KEEP(lmi-cpu-epss.o(.text.lmi_epss_apply)) KEEP(lmi-cpu-epss.o(.text.lmi_epss_restore)) KEEP(lmi-cpu-epss.o(.text.lmi_epss_select)) KEEP(lmi-cpu-epss-native.o(.text.lmi_epss_native_quiesce)) KEEP(lmi-cpu-epss-native.o(.rodata.str1.1)) KEEP(lmi-cpu-epss-native.o(.text.status)) KEEP(lmi-cpu-epss-native.o(.rodata..L__const.lmi_epss_native_init.io)) KEEP(lmi-cpu-epss.o(.text.OUTLINED_FUNCTION_1)) KEEP(lmi-cpu-epss-native.o(.text.lmi_epss_native_cleanup)) KEEP(lmi-cpu-epss.o(.text.OUTLINED_FUNCTION_0)) KEEP(lmi-cpu-epss-native.o(.text.native_read)) KEEP(lmi-cpu-epss.o(.rodata.lmi_epss_prepare.cap)) KEEP(lmi-cpu-epss-native.o(.text.native_map)) KEEP(lmi-cpu-epss-native.o(.text.native_write)) }
 /DISCARD/ : { *(.comment .note* .llvm_addrsig) }
}
