// Headless adapter compatibility. These extra APIs belong to the ares fork,
// not upstream Angrylion. GUI metrics/viewers are deliberately unavailable.
void n64video_flush(void) { if (config.parallel) cmd_flush(); }
void n64video_hidden_rdram_get(const uint8_t **buf, uint32_t *entries) {
    *buf = rdram_hidden;
    *entries = config.gfx.rdram_size / 2;
}
void n64video_metrics_get(struct n64video_metrics *out) { memset(out, 0, sizeof(*out)); }
void n64video_metrics_reset(void) {}
void n64video_fb_heatmap_get(struct n64video_fb_heatmap *out) { memset(out, 0, sizeof(*out)); }
void n64video_fb_heatmap_clear(void) {}
void n64video_tmem_snapshot(struct n64video_tmem_snapshot *out) { memset(out, 0, sizeof(*out)); }
void n64video_decode_tile_region(uint32_t tile, uint32_t *dst, uint32_t x,
                               uint32_t y, uint32_t w, uint32_t h) {
    msg_error("Research runner has no fork GUI texture viewer");
}
