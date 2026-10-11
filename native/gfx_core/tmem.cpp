#include "gfx.hpp"
#include <algorithm>
#include <stdexcept>

namespace sc64::gfx {
namespace {
std::uint8_t byte(std::span<const std::uint8_t> ram, std::uint64_t address) {
    if (address >= ram.size()) throw std::runtime_error("Texture read outside RDRAM");
    return ram[address];
}
std::uint16_t half(std::span<const std::uint8_t> ram, std::uint64_t address) {
    return (byte(ram,address)<<8)|byte(ram,address+1);
}
Color decode(unsigned format, unsigned size, unsigned value) {
    if (format == 0 && size == 2) return rgba16(value);
    if (format == 0 && size == 3) return {int(value>>24),int(value>>16&255),int(value>>8&255),int(value&255)};
    if (format == 3) {
        if (size == 0) { unsigned v=value&14;int i=(v<<4)|(v<<1)|(v>>2); return {i,i,i,int(value&1)*255}; }
        if (size == 1) { int i=(value>>4)*17; return {i,i,i,int(value&15)*17}; }
        if (size == 2) { int i=value>>8; return {i,i,i,int(value&255)}; }
    }
    if (format == 4 && size <= 1) {
        int i=size == 0 ? value*17 : value; return {i,i,i,i};
    }
    throw std::runtime_error("Unsupported texture format/size");
}
}
Color rgba16(std::uint16_t v) {
    auto expand=[](int c){return (c<<3)|(c>>2);};
    return {expand(v>>11),expand(v>>6&31),expand(v>>1&31),(v&1)*255};
}
std::uint16_t encode_rgba16(Color c) {
    return ((std::clamp(c.r,0,255)>>3)<<11)|((std::clamp(c.g,0,255)>>3)<<6)|
           ((std::clamp(c.b,0,255)>>3)<<1)|(c.a!=0);
}
std::uint16_t Tmem::palette(unsigned index) const {
    if(index>=256) throw std::runtime_error("TLUT index exceeds 256");
    unsigned a=2048+index*8; return (bytes[a]<<8)|bytes[a+1];
}
void Tmem::load_tlut(std::span<const std::uint8_t> ram,const Image& img,
                     unsigned head,unsigned count,int sl,int tl) {
    if (img.size!=2 || head<256 || head>511 || count>512-head || sl<0 || tl<0)
        throw std::runtime_error("Invalid TLUT load");
    std::uint64_t src=img.address+(std::uint64_t(tl/4)*img.width+sl/4)*2;
    for(unsigned i=0;i<count;++i) {
        auto v=half(ram,src+i*2);
        for(unsigned bank=0;bank<4;++bank) {
            unsigned a=(head+i)*8+bank*2; bytes[a]=v>>8;bytes[a+1]=v&255;
        }
    }
}
void Tmem::load_tile(std::span<const std::uint8_t> ram,const Image& img,
                    const Tile& tile,int sl,int tl,int sh,int th) {
    if(sh<sl || th<tl || img.width==0 || img.size>3 || sl<0 || tl<0)
        throw std::runtime_error("Invalid LOADTILE bounds");
    unsigned w=(sh>>2)-(sl>>2)+1,h=(th>>2)-(tl>>2)+1;
    if(w>1024 || h>1024 || std::uint64_t(w)*h>1048576) throw std::runtime_error("LOADTILE exceeds budget");
    for(unsigned y=0;y<h;++y) for(unsigned x=0;x<w;++x) {
        std::uint64_t texel=std::uint64_t((tl>>2)+y)*img.width+(sl>>2)+x;
        unsigned base=tile.tmem*8+y*tile.line*8;
        unsigned swap=(y&1)?4:0;
        if(img.size==3) {
            // RG halfwords in bank0, BA in bank1; each uses the 16-bit stride.
            unsigned a=((base+x*2)^swap)&2047;
            for(unsigned j=0;j<2;++j) {bytes[(a+j)&2047]=byte(ram,img.address+texel*4+j);
                bytes[2048+((a+j)&2047)]=byte(ram,img.address+texel*4+j+2);}
        } else if(img.size==0) {
            unsigned v=byte(ram,img.address+texel/2);v=(texel&1)?(v&15):(v>>4);
            unsigned a=((base+x/2)^swap)&4095;
            if(x&1) bytes[a]=(bytes[a]&240)|v;else bytes[a]=(bytes[a]&15)|(v<<4);
        } else {
            unsigned n=1u<<(img.size-1);
            for(unsigned j=0;j<n;++j) bytes[((base+x*n+j)^swap)&4095]=byte(ram,img.address+texel*n+j);
        }
    }
}
Color Tmem::fetch(const Tile& tile,int s,int t,unsigned mode) const {
    unsigned base=(tile.tmem+tile.line*(t&255))*8, swap=(t&1)?4:0,v=0;
    unsigned byte_mask=tile.format==2 && (mode==2 || mode==3)?2047:4095;
    if(tile.size==3) {
        unsigned a=((base+s*2)^swap)&2047;
        v=(unsigned(bytes[a])<<24)|(unsigned(bytes[(a+1)&2047])<<16)|
            (unsigned(bytes[2048+a])<<8)|bytes[2048+((a+1)&2047)];
    } else if(tile.size==0) {
        // Shift the wrapped unsigned texel address so negative odd S rounds
        // down, as in TMEM hardware, rather than truncating toward zero.
        unsigned offset=std::uint32_t(s)>>1;
        v=bytes[((base+offset)^swap)&byte_mask];v=(s&1)?(v&15):(v>>4);
    } else {
        unsigned n=1u<<(tile.size-1),a=((base+s*n)^swap)&byte_mask;
        v=bytes[a];if(n==2)v=(v<<8)|bytes[(a+1)&4095];
    }
    if(tile.format==2) {
        if(tile.size>1 || (mode!=2 && mode!=3)) throw std::runtime_error("CI texture needs RGBA16/IA16 TLUT");
        v=palette(tile.size==0?tile.palette*16+v:v);
        return mode==2?rgba16(v):decode(3,2,v);
    }
    return decode(tile.format,tile.size,v);
}
Color source_texel(std::span<const std::uint8_t> ram,const Image& img,
                   unsigned x,unsigned y,unsigned pal,const Tmem& tmem,unsigned mode) {
    if(img.width==0 || img.size>3)throw std::runtime_error("Invalid source image");
    std::uint64_t pos=std::uint64_t(y)*img.width+x;
    unsigned v;
    if(img.size==0) {v=byte(ram,img.address+pos/2);v=(pos&1)?v&15:v>>4;}
    else if(img.size==1) v=byte(ram,img.address+pos);
    else if(img.size==2) v=half(ram,img.address+pos*2);
    else v=(unsigned(half(ram,img.address+pos*4))<<16)|half(ram,img.address+pos*4+2);
    if(img.format==2) {
        if(img.size>1 || (mode!=2 && mode!=3))throw std::runtime_error("Invalid CI background TLUT");
        v=tmem.palette(img.size==0?pal*16+v:v);return mode==2?rgba16(v):decode(3,2,v);
    }
    return decode(img.format,img.size,v);
}
std::vector<std::uint8_t> target_rgba(std::span<const std::uint8_t> ram,Image img,unsigned h) {
    if(img.format!=0 || img.size!=2 || img.width>1024 || h>1024 || !img.width || !h)
        throw std::runtime_error("Only bounded RGBA16 target export is supported");
    std::vector<std::uint8_t> out;out.reserve(img.width*h*4);
    Tmem unused;
    for(unsigned y=0;y<h;++y) for(unsigned x=0;x<img.width;++x) {
        auto c=source_texel(ram,img,x,y,0,unused,0);
        out.insert(out.end(),{std::uint8_t(c.r),std::uint8_t(c.g),std::uint8_t(c.b),std::uint8_t(c.a)});
    }
    return out;
}
}
