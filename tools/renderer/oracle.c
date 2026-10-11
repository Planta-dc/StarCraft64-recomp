// Offline test adapter for pinned Angrylion. It is never linked into gfx_core
// or the application shell. Source files retain their upstream license.
#include "n64video.h"
#include "parallel.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
void parallel_init(uint32_t n,bool busy) {(void)n;(void)busy;}
void parallel_run(void task(uint32_t)) {task(0);}
uint32_t parallel_num_workers(void) {return 1;}
void parallel_close(void) {}
void msg_error(const char* fmt,...) {va_list args;va_start(args,fmt);vfprintf(stderr,fmt,args);va_end(args);exit(2);}
void msg_warning(const char* fmt,...) {va_list args;va_start(args,fmt);vfprintf(stderr,fmt,args);va_end(args);}
void msg_debug(const char* fmt,...) {(void)fmt;}
static void interrupt(void) {}
int main(int argc,char**argv) {
    if(argc!=4){fprintf(stderr,"usage: sc64_rdp_oracle canonical.ram commands.rdp NEW-result.ram\n");return 2;}
    FILE* input=fopen(argv[1],"rb");if(!input)return 2;
    uint8_t* ram=calloc(RDRAM_MAX_SIZE,1);if(!ram)return 2;
    for(unsigned i=0;i<RDRAM_MAX_SIZE;++i){int c=fgetc(input);if(c==EOF)return 2;ram[i^3]=c;}
    if(fgetc(input)!=EOF)return 2;fclose(input);
    uint32_t vi[14]={0},dp[8]={0},mi=0,*vp[14],*dpointers[8];
    uint32_t dmem[1024]={0};
    for(unsigned i=0;i<14;++i)vp[i]=vi+i;
    for(unsigned i=0;i<8;++i)dpointers[i]=dp+i;
    struct n64video_config config;n64video_config_init(&config);
    config.gfx.rdram=ram;config.gfx.rdram_size=RDRAM_MAX_SIZE;config.gfx.dmem=(uint8_t*)dmem;
    config.gfx.vi_reg=vp;config.gfx.dp_reg=dpointers;config.gfx.mi_intr_reg=&mi;config.gfx.mi_intr_cb=interrupt;
    config.parallel=false;n64video_init(&config);
    input=fopen(argv[2],"rb");if(!input)return 2;
    // Submit complete commands. Splitting arbitrary XBUS words across calls
    // would also exercise the upstream partial-command loader's state machine,
    // obscuring whether a mismatch belongs to our renderer or this test adapter.
    static const unsigned tri_words[8]={8,12,24,28,24,28,40,44};
    for(;;) {
        int c=fgetc(input);if(c==EOF)break;
        unsigned op=c&63;
        unsigned n=op>=8 && op<16?tri_words[op-8]:(op==0x24 || op==0x25?4:2);
        for(unsigned i=0;i<n;++i) {
            uint32_t v=0;
            for(unsigned j=0;j<4;++j) {
                if(i || j)c=fgetc(input);
                if(c==EOF)return 2;v=(v<<8)|(unsigned)c;
            }
            dmem[i]=v;
        }
        dp[DP_START]=dp[DP_CURRENT]=0;dp[DP_END]=n*4;dp[DP_STATUS]=1;
        n64video_process_list();
    }
    fclose(input);n64video_close();
    FILE* output=fopen(argv[3],"wx");if(!output)return 2;
    for(unsigned i=0;i<RDRAM_MAX_SIZE;++i)if(fputc(ram[i^3],output)==EOF)return 2;
    if(fclose(output))return 2;free(ram);return 0;
}
