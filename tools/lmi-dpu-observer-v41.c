/* lmi SM8250 DPU registers, read only. Caller supplies a mapped MDSS base.
 * Offsets are from MiCode lmi-q-oss 789514465a7cd3acbf70fa67f7e10fd8fde270bd.
 * In particular, INTF1_MUX chooses the pingpong block; PP0 is not assumed.
 * Keep code in a separate resident TEXT_EXEC section, with no data/strings
 * added to the old kernel sections. This is not a present/IRQ implementation.
 */
typedef unsigned int dpu_u32;
struct lmi_dpu_snapshot {
    dpu_u32 mux, sync, autorefresh, frame, transfer_line;
    dpu_u32 ctl_start, ctl_flush, source_address, source_stride;
};
#ifndef LMI_DPU_SNAPSHOT_HOST
#define DPU_CODE __attribute__((section("__TEXT_EXEC,__lmi_dpu"), noinline, used))
#define DPU_ALIGN __attribute__((aligned(16384)))
#else
#define DPU_CODE
#define DPU_ALIGN
#endif

DPU_CODE DPU_ALIGN int
lmi_dpu_read_snapshot(volatile const dpu_u32 *mdss, struct lmi_dpu_snapshot *out)
{
    if (!mdss || !out) return 0;
    out->mux = mdss[0x6ba5c / 4];
    out->sync = mdss[0x6ba88 / 4];
    out->autorefresh = mdss[0x6bab4 / 4];
    out->frame = mdss[0x6b8ac / 4];
    out->transfer_line = mdss[0x6bab0 / 4];
    out->ctl_start = mdss[0x201c / 4];
    out->ctl_flush = mdss[0x2018 / 4];
    out->source_address = mdss[0x5014 / 4];
    out->source_stride = mdss[0x5024 / 4];
    return 1;
}

#ifndef LMI_DPU_SNAPSHOT_HOST
extern unsigned long ml_io_map(unsigned long, unsigned long);
extern int snprintf(char *, unsigned long, const char *, ...);
extern void loader_log_line(const char *);
extern void lmi_dpu_original_show(void *, const unsigned char *, void **);
static volatile const dpu_u32 *display_map __attribute__((section("__DATA,__lmi_dpu")));
static unsigned long display_samples __attribute__((section("__DATA,__lmi_dpu")));
static const char display_format[] __attribute__((section("__TEXT_EXEC,__lmi_ro"))) =
    "LMI_DPU_PRESENT_READONLY n=%lu mux=%x sync=%x auto=%x frame=%u line=%u ctl_start=%x ctl_flush=%x source=%x stride=%x\n";

static const char display_entry[] __attribute__((section("__TEXT_EXEC,__lmi_ro"))) =
    "LMI_DPU_OBSERVER_ENTER\n";
static const char display_map_failure[] __attribute__((section("__TEXT_EXEC,__lmi_ro"))) =
    "LMI_DPU_OBSERVER_MAP_FAILED\n";

DPU_CODE void
lmi_dpu_observe_show(void *self, const unsigned char *swap, void **surfaces)
{
    /* show() runs on the single presenter. Observe without changing any DPU
     * register, surface lifetime, GPU wait, or submission decision. */
    if (!display_map) {
        loader_log_line(display_entry);
        display_map = (volatile const dpu_u32 *)ml_io_map(0x0ae00000UL, 0x84000UL);
    }
    unsigned long sample = ++display_samples;
    if (sample <= 4 || sample % 128 == 0) {
        struct lmi_dpu_snapshot snapshot;
        if (lmi_dpu_read_snapshot(display_map, &snapshot)) {
            char line[256];
            snprintf(line, sizeof(line), display_format, sample, snapshot.mux, snapshot.sync, snapshot.autorefresh,
                snapshot.frame, snapshot.transfer_line, snapshot.ctl_start, snapshot.ctl_flush,
                snapshot.source_address, snapshot.source_stride);
            loader_log_line(line);
        } else {
            loader_log_line(display_map_failure);
        }
    }
    lmi_dpu_original_show(self, swap, surfaces);
}
#endif
