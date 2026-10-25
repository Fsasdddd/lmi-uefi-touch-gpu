/* FT3518 GPIO edges need a minimum 5us delay without scheduling the thread.
 * lmi's architectural virtual counter is fixed at the verified 19.2MHz rate;
 * long power/reset/poll waits continue to use XNU's yielding delay API. */
#ifdef LMI_TOUCH_TIMING_HOST
extern unsigned long long lmi_touch_counter(void);
extern unsigned long long lmi_touch_counter_frequency(void);
#else
static unsigned long long lmi_touch_counter(void) {
    unsigned long long value;
    __asm__ volatile("isb\n\tmrs %0, cntvct_el0":"=r"(value)::"memory");
    return value;
}
static unsigned long long lmi_touch_counter_frequency(void) {
    unsigned long long value;
    __asm__ volatile("mrs %0, cntfrq_el0":"=r"(value));
    return value;
}
#endif
static int lmi_touch_timing_ready(void) {
    return lmi_touch_counter_frequency()==19200000;
}
static void lmi_touch_edge_delay(void) {
    unsigned long long start=lmi_touch_counter();
    while(lmi_touch_counter()-start<96) {}
}
