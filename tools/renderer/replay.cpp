#include "gfx.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <string>
namespace fs=std::filesystem;
std::vector<std::uint8_t> read(const fs::path& p) {
    std::ifstream f(p,std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("Cannot read "+p.string());
    auto n=f.tellg();if(n<0 || n>128*1024*1024)throw std::runtime_error("Input size exceeds budget");
    std::vector<std::uint8_t> v(n);f.seekg(0);f.read(reinterpret_cast<char*>(v.data()),v.size());
    if(!f)throw std::runtime_error("Input short read");return v;
}
int main(int argc,char** argv) {
    try {
        if(argc<5 || argc%2==0)throw std::runtime_error("usage: sc64_gfx_replay gbi|rdp canonical.ram root-or-rdp.bin NEW-output-directory [--repeat 1..100] [--workers 0..15]");
        unsigned repeat=1,helpers=0;bool timed=false;
        auto number=[](const std::string& text,unsigned low,unsigned high,const char* error) {
            if(text.empty() || text.size()>3 || text.find_first_not_of("0123456789")!=std::string::npos)
                throw std::runtime_error(error);
            auto value=std::stoul(text);if(value<low || value>high)throw std::runtime_error(error);
            return unsigned(value);
        };
        for(int i=5;i<argc;i+=2) {
            const std::string option=argv[i];
            if(option=="--repeat"){repeat=number(argv[i+1],1,100,"Expected --repeat 1..100");timed=true;}
            else if(option=="--workers")helpers=number(argv[i+1],0,15,"Expected --workers 0..15");
            else throw std::runtime_error("Unknown option "+option);
        }
        fs::path output=fs::weakly_canonical(fs::absolute(argv[4]));
        auto private_root=fs::weakly_canonical(fs::path(SC64_PRIVATE_ROOT));
        auto relative=output.lexically_relative(private_root);
        if(relative.empty() || relative.is_absolute() || *relative.begin()=="..")
            throw std::runtime_error("Game-derived output must stay under ignored local/");
        if(fs::exists(output))throw std::runtime_error("Output must be new");
        auto ram=read(argv[2]);sc64::gfx::DrawList list;
        const std::string mode=argv[1];unsigned root=0;
        std::vector<std::uint64_t> words;
        if(mode=="gbi")root=std::stoul(argv[3],nullptr,0);
        else if(mode=="rdp") {
            auto data=read(argv[3]);if(data.size()%8)throw std::runtime_error("Incomplete RDP word");
            for(unsigned i=0;i<data.size();i+=8){std::uint64_t v=0;for(unsigned j=0;j<8;++j)v=(v<<8)|data[i+j];words.push_back(v);}
        } else throw std::runtime_error("Unknown input mode");
        auto interpret=[&] {return mode=="gbi"?sc64::gfx::interpret_gbi(ram,root):sc64::gfx::interpret_rdp(ram,words);};
        // Benchmark mode warms once, then measures interpretation only. Reading
        // inputs, freeing the previous packet and rasterization are outside it.
        if(timed)list=interpret();
        std::vector<double> interpret_ms;
        for(unsigned i=0;i<repeat;++i) {
            list={};const auto start=std::chrono::steady_clock::now();
            list=interpret();
            interpret_ms.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
        }
        // Timed mode warms once, then measures rasterization of the owned packet.
        sc64::gfx::RasterPool pool(helpers);
        auto rendered=sc64::gfx::render_software(list,{},&pool);
        std::vector<double> software_ms;
        for(unsigned i=0;timed && i<repeat;++i) {
            const auto start=std::chrono::steady_clock::now();
            auto again=sc64::gfx::render_software(list,{},&pool);
            software_ms.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
            if(again.ram!=rendered.ram || again.written_pixels!=rendered.written_pixels)
                throw std::runtime_error("Repeated rasterization is not deterministic");
        }
        fs::create_directories(output);
        std::ofstream raw(output/"rendered.ram",std::ios::binary);
        raw.write(reinterpret_cast<const char*>(rendered.ram.data()),rendered.ram.size());
        if(!raw)throw std::runtime_error("Output write failed");
        std::ofstream report(output/"report.json");
        report<<"{\"schema\":1,\"rectangles\":"<<list.rectangles.size()<<",\"textures\":"<<list.textures.size()
              <<",\"written_pixels\":"<<rendered.written_pixels<<",\"opcodes\":{";
        bool first=true;for(unsigned i=0;i<256;++i)if(list.opcodes[i]) {
            if(!first)report<<',';first=false;report<<'"'<<i<<"\":"<<list.opcodes[i];
        }
        report<<"},\"batches\":"<<sc64::gfx::adjacent_batches(list).size()<<",\"targets\":[";
        std::vector<sc64::gfx::Image> targets;
        for(const auto& rect:list.rectangles) {
            bool seen=false;for(auto target:targets)if(target==rect.target)seen=true;
            if(!seen)targets.push_back(rect.target);
        }
        first=true;for(auto target:targets) {
            if(!first)report<<',';first=false;
            report<<"{\"address\":"<<target.address<<",\"width\":"<<target.width
                  <<",\"format\":"<<target.format<<",\"size\":"<<target.size<<'}';
        }
        report<<"],\"texture_keys\":[";
        first=true;for(const auto& texture:list.textures) {
            if(!first)report<<',';first=false;
            // Decimal strings keep all 64 bits in JSON consumers.
            report<<'"'<<texture.key<<'"';
        }
        report<<"],\"interpret_ms\":["<<std::setprecision(17);
        first=true;for(auto ms:interpret_ms) {if(!first)report<<',';first=false;report<<ms;}
        report<<"],\"software_ms\":[";
        first=true;for(auto ms:software_ms) {if(!first)report<<',';first=false;report<<ms;}
        report<<"],\"raster_helpers\":"<<helpers<<"}\n";
        if(!report)throw std::runtime_error("Report write failed");
        std::cout<<"rectangles="<<list.rectangles.size()<<" textures="<<list.textures.size()<<" pixels="<<rendered.written_pixels<<'\n';
    } catch(const std::exception& e) {std::cerr<<"Replay failed: "<<e.what()<<'\n';return 2;}
}
