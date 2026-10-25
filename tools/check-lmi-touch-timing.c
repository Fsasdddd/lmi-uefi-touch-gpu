#include <assert.h>
#include <stdio.h>
#define LMI_TOUCH_TIMING_HOST
#include "lmi-touch-timing.h"
static unsigned long long counter,step,frequency,reads;
unsigned long long lmi_touch_counter(void) {
    unsigned long long value=counter;
    counter+=step;reads++;
    return value;
}
unsigned long long lmi_touch_counter_frequency(void) {return frequency;}
int main(void) {
    frequency=19200000;assert(lmi_touch_timing_ready());
    for(unsigned n=0;n<4;n++) {
        counter=n==3?~0ull-20:1000;
        step=n==1?7:n==2?113:1;reads=0;
        unsigned long long start=counter;
        lmi_touch_edge_delay();
        unsigned long long elapsed=counter-step-start;
        assert(elapsed*1000000>=5*frequency);
        assert(elapsed<96+step && reads>=2 && reads<=97);
    }
    frequency=0;assert(!lmi_touch_timing_ready());
    frequency=24000000;assert(!lmi_touch_timing_ready());
    puts("PASS: 5us GPIO edge minimum, timer jumps/wrap, and wrong-frequency rejection");
}
