// Synthetic source-level regression against the real reference RDP core.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
extern "C" {
#include "n64video.h"
void msg_error(const char*, ...) { std::abort(); }
void msg_warning(const char*, ...) {}
void msg_debug(const char*, ...) {}
void sc64_research_rdp_write(std::uint32_t, unsigned) {}
}
static unsigned interrupts = 0;
static void interrupt() { ++interrupts; }

int main(int argc, char** argv) {
    if(argc != 2) return 2;
    std::vector<std::uint8_t> ram(0x800000);
    std::uint32_t dmem[1024] = {}, dp[DP_NUM_REG] = {}, vi[VI_NUM_REG] = {}, mi = 0;
    std::uint32_t* dpPointers[DP_NUM_REG];
    std::uint32_t* viPointers[VI_NUM_REG];
    for(unsigned i = 0; i < DP_NUM_REG; ++i) dpPointers[i] = &dp[i];
    for(unsigned i = 0; i < VI_NUM_REG; ++i) viPointers[i] = &vi[i];
    n64video_config config;
    n64video_config_init(&config);
    config.gfx.rdram = ram.data();
    config.gfx.rdram_size = static_cast<std::uint32_t>(ram.size());
    config.gfx.dmem = reinterpret_cast<std::uint8_t*>(dmem);
    config.gfx.dp_reg = dpPointers;
    config.gfx.vi_reg = viPointers;
    config.gfx.mi_intr_reg = &mi;
    config.gfx.mi_intr_cb = interrupt;
    config.parallel = false;
    n64video_init(&config);
    dp[DP_STATUS] = 1;
    if(std::strcmp(argv[1], "fragment") == 0) {
        dmem[0] = 0x24000000;
        dp[DP_END] = 8;
        n64video_process_list();
        dmem[4] = 0x29000000;
        dp[DP_END] = 24;
        n64video_process_list();
    } else if(std::strcmp(argv[1], "native-word") == 0) {
        dmem[0] = 0x29000000;
        dp[DP_END] = 8;
        n64video_process_list();
    } else if(std::strcmp(argv[1], "byte-array") == 0) {
        // A big-endian byte array viewed as native u32 on a little-endian host.
        dmem[0] = 0x00000029;
        dp[DP_END] = 8;
        n64video_process_list();
    } else return 2;
    n64video_close();
    std::printf("%s sync_full_interrupts=%u\n", argv[1], interrupts);
    return 0;
}
