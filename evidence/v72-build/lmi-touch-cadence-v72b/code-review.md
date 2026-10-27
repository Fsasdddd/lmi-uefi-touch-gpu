# v72b offline review

Only three guarded ARM64 immediate words differ from reviewed v71: valid report
pause 20ms -> 1ms, idle/header-retry pause 50ms -> 2ms, and finite loop bound
4000 -> 409600. The larger limit prevents a faster loop expiring before the
180-second RAM run finishes; original error exits and timer remain effective.

All I2C edge/clock-stretch timing, power/reset/chip-ID gates, full-report reads,
decoder, last-up coordinates, HID initialization, GPU fence/cache ownership and
DPU completion bytes remain identical. This is a binary patch; editing only the
old C source would not modify the running kernel. A restoration of all three
words reproduces the complete v71 image byte for byte.

Independent Capstone decode plus Unicorn execution of the actual ARM64 loop
passed 15 cases: tap/swipe/final-up/missing-up/multitouch/duplicate/FF/64 failures,
transient/header retry/clamp/active cleanup, both limit boundaries and modeled
185-second idle lifetime. Only external I/O and yielding delays are stubbed;
this does not prove hardware timing, actual sample rate or touch-to-photon time.

Preserved failures: first v72 candidate had the wrong shifted CMP immediate and
was rejected before hardware. Emulator setup initially omitted the dominating
w23=1 gate state; an explicit expected swipe assertion caught that harness error.
The staging script initially referenced a missing renamed ancestry checker;
the failed directory is retained and corrected prepare-only uses reviewed-b.
No failed result is counted as passing and no old candidate/log is overwritten.

Tradeoff: faster GPIO I2C polling consumes more CPU, especially during movement.
Compare same-contact timestamp intervals, post-to-HID delivery and animation
behavior in one RAM-only test. A better sample rate alone is not proof of lower
physical end-to-end latency or higher animation FPS. Legacy GPU admission and
strict source/DPU rules are inherited unchanged; Wi-Fi is not integrated.
