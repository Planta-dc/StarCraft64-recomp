// Research instrumentation for the pinned ares-64 tree. No game-derived code.
#include <n64/n64.hpp>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>
#include <cstdio>
#include <cinttypes>
#include <atomic>
#include <mutex>

namespace ares::Nintendo64::Stage0 {
namespace {
std::FILE* events = nullptr;
std::string directory;
std::uint64_t fields = 0, tasks = 0;
unsigned remaining = 0, dumpedGraphics = 0, dumpedAudio = 0;
bool wasJit = true, wasRspJit = true;
std::string label;
std::set<std::string> blobs;
std::set<unsigned> executedPages;
std::atomic<bool> recordRdp = false;
std::mutex rdpMutex;
struct Access {
  std::uint64_t count = 0, bytes = 0;
  std::uint32_t min = UINT32_MAX, max = 0;
};
std::map<unsigned, Access> rdpWrites;
std::vector<std::uint8_t> lastRdpWriter(0x800000);
std::map<std::uint64_t, Access> rdpReads;
// Separate logical CPU requests from cache-line bus traffic; neither is DP writes.
std::map<std::uint64_t, Access> cpuAccesses;
std::map<unsigned, std::pair<std::uint64_t, std::uint64_t>> busAccesses;
void fail(const char* reason) { throw std::runtime_error(reason); }
void safeLabel(const char* value) {
  if(!value || !*value) fail("empty capture label");
  for(auto p = value; *p; ++p)
    if(!std::isalnum(static_cast<unsigned char>(*p)) && *p != '-' && *p != '_')
      fail("capture labels accept only letters, digits, hyphen and underscore");
}
std::uint8_t ramByte(std::uint32_t a) {
  return static_cast<Memory::Writable&>(rdram.ram).read<Byte>(a);
}
void writeRam(const std::string& path, unsigned address, unsigned length) {
  if(address > rdram.ram.size || length > rdram.ram.size - address)
    fail("capture outside RDRAM");
  std::ofstream out(path, std::ios::binary);
  if(!out) fail("cannot open RAM capture");
  std::vector<std::uint8_t> data(length);
  for(unsigned i = 0; i < length; ++i) data[i] = ramByte(address + i);
  out.write(reinterpret_cast<const char*>(data.data()), data.size());
  if(!out) fail("RAM capture write failed");
}
std::string blob(unsigned address, unsigned length) {
  address &= 0x1fffffff;
  if(address > rdram.ram.size || length > rdram.ram.size - address) return "invalid";
  // FNV is a file deduplication key only. Python reports SHA-1/SHA-256 separately.
  std::uint64_t hash = 14695981039346656037ULL;
  for(unsigned i = 0; i < length; ++i) hash = (hash ^ ramByte(address + i)) * 1099511628211ULL;
  char name[64]; std::snprintf(name, sizeof(name), "blob-%016" PRIx64 "-%u.bin", hash, length);
  if(blobs.insert(name).second) writeRam(directory + "/" + name, address, length);
  return name;
}
void accesses() {
  std::lock_guard<std::mutex> lock(rdpMutex);
  for(auto [page, a] : rdpWrites)
    std::fprintf(events, "{\"event\":\"rdp_write\",\"field\":%" PRIu64 ",\"page\":%u,\"count\":%" PRIu64 ",\"bytes\":%" PRIu64 ",\"min\":%u,\"max\":%u}\n", fields, page, a.count, a.bytes, a.min, a.max);
  rdpWrites.clear();
  for(auto [key, a] : rdpReads)
    std::fprintf(events, "{\"event\":\"cpu_rdp_read\",\"field\":%" PRIu64 ",\"pc\":%u,\"page\":%u,\"physical_equal\":%s,\"count\":%" PRIu64 ",\"bytes\":%" PRIu64 ",\"min\":%u,\"max\":%u}\n", fields, unsigned(key >> 32), unsigned(key & 0xfffff000), key & 1 ? "true" : "false", a.count, a.bytes, a.min, a.max);
  rdpReads.clear();
  for(auto [key, a] : cpuAccesses) {
    auto pc = static_cast<unsigned>(key >> 32);
    auto page = static_cast<unsigned>(key & 0xfffff000);
    bool write = key & 1;
    std::fprintf(events, "{\"event\":\"cpu_access\",\"field\":%" PRIu64 ",\"pc\":%u,\"page\":%u,\"write\":%s,\"count\":%" PRIu64 ",\"bytes\":%" PRIu64 ",\"min\":%u,\"max\":%u}\n", fields, pc, page, write ? "true" : "false", a.count, a.bytes, a.min, a.max);
  }
  for(auto [key, a] : busAccesses)
    std::fprintf(events, "{\"event\":\"bus_access\",\"field\":%" PRIu64 ",\"device\":%u,\"write\":%s,\"bytes\":%" PRIu64 "}\n", fields, key >> 1, (key & 1) ? "true" : "false", a.first);
  cpuAccesses.clear(); busAccesses.clear();
}
}
void start(const char* path) {
  stop(); directory = path;
  std::filesystem::create_directories(directory);
  auto eventPath = directory + "/events.jsonl";
  if(std::filesystem::exists(eventPath)) fail("capture directory already contains events");
  events = std::fopen(eventPath.c_str(), "wb");
  if(!events) fail("cannot open events file");
  fields = tasks = 0; blobs.clear(); executedPages.clear();
  std::fprintf(events, "{\"event\":\"session\",\"schema\":1,\"homebrew\":%s,\"ram_bytes\":%u}\n", system.homebrewMode ? "true" : "false", static_cast<unsigned>(rdram.ram.size));
}
void stop() {
  if(!events) return;
  recordRdp = false;
  accesses(); std::fclose(events); events = nullptr;
  if(remaining) { cpu.recompiler.enabled = wasJit; rsp.recompiler.enabled = wasRspJit; }
  remaining = 0;
}
void window(const char* name, unsigned count) {
  if(!events) fail("capture is not started");
  if(remaining || !count) fail("capture window overlaps or is empty");
  safeLabel(name); label = name; remaining = count;
  dumpedGraphics = dumpedAudio = 0;
  wasJit = cpu.recompiler.enabled; wasRspJit = rsp.recompiler.enabled;
  recordRdp = true;
  std::fill(lastRdpWriter.begin(), lastRdpWriter.end(), 0);
  cpu.recompiler.enabled = false; rsp.recompiler.enabled = false;
  std::fprintf(events, "{\"event\":\"window\",\"label\":\"%s\",\"field\":%" PRIu64 ",\"fields\":%u,\"cpu\":\"interpreter\"}\n", name, fields, count);
}
void snapshot(const char* name) {
  if(!events) fail("capture is not started");
  safeLabel(name);
  writeRam(directory + "/" + name + ".rdram.bin", 0, rdram.ram.size);
  std::vector<std::uint8_t> visible(rdram.ram.size);
  for(unsigned a = 0; a < visible.size(); ++a) visible[a] = ramByte(a);
  unsigned cachedLines = 0;
  for(auto& line : cpu.dcache.lines) {
    if(!line.valid()) continue;
    unsigned address = (line.tagKey & ~0xfffU) | line.index;
    if(address + 16 > visible.size()) continue;
    ++cachedLines;
    for(unsigned i = 0; i < 16; ++i) visible[address + i] = line.read<Byte>(address + i);
  }
  std::ofstream cpuOut(directory + "/" + name + ".cpu-visible.bin", std::ios::binary);
  cpuOut.write(reinterpret_cast<const char*>(visible.data()), visible.size());
  if(!cpuOut) fail("CPU cache overlay write failed");
  if(cartridge.flash) {
    std::ofstream out(directory + "/" + name + ".flash.bin", std::ios::binary);
    for(unsigned i = 0; i < cartridge.flash.size; ++i) {
      char b = static_cast<Memory::Writable&>(cartridge.flash).read<Byte>(i);
      out.write(&b, 1);
    }
    if(!out) fail("FlashRAM snapshot write failed");
  }
  std::fprintf(events, "{\"event\":\"snapshot\",\"label\":\"%s\",\"field\":%" PRIu64 "}\n", name, fields);
  std::fprintf(events, "{\"event\":\"core_state\",\"field\":%" PRIu64 ",\"cpu_pc\":%u,\"cp0_status_ie\":%u,\"cp0_status_exl\":%u,\"cp0_cause_pending\":%u,\"mi_irq_masked\":%u,\"rsp_pc\":%u,\"rsp_halted\":%u,\"rsp_broken\":%u,\"rsp_irq_break\":%u,\"dp_current\":%u,\"dp_end\":%u}\n", fields, unsigned(cpu.ipu.pc), unsigned(cpu.scc.status.interruptEnable), unsigned(cpu.scc.status.exceptionLevel), unsigned(cpu.scc.cause.interruptPending), unsigned(mi.activeIRQs()), unsigned(rsp.ipu.pc), unsigned(rsp.status.halted), unsigned(rsp.status.broken), unsigned(rsp.status.interruptOnBreak), unsigned(rdp.command.current), unsigned(rdp.command.end));
  std::fflush(events);
}
void saveState(const char* path) {
  auto state = system.serialize(false);
  std::ofstream out(path, std::ios::binary);
  out.write(reinterpret_cast<const char*>(state.data()), state.size());
  if(!out) fail("state write failed");
}
void loadState(const char* path) {
  std::ifstream in(path, std::ios::binary);
  if(!in) fail("cannot read state");
  std::vector<std::uint8_t> data(std::istreambuf_iterator<char>(in), {});
  if(data.empty() || data.size() > 128 * 1024 * 1024) fail("invalid state size");
  serializer state(data.data(), data.size());
  if(!system.unserialize(state)) fail("state rejected by core");
  vi.replayRegisters();
}
void loadFlash(const char* path) {
  if(!cartridge.flash) fail("cartridge has no FlashRAM");
  std::ifstream in(path, std::ios::binary);
  if(!in) fail("cannot read FlashRAM image");
  std::vector<std::uint8_t> data(std::istreambuf_iterator<char>(in), {});
  if(data.size() != cartridge.flash.size) fail("wrong FlashRAM image length");
  for(unsigned i = 0; i < data.size(); ++i)
    static_cast<Memory::Writable&>(cartridge.flash).write<Byte>(i, data[i]);
}
void execute(std::uint32_t address) {
  if(!events || address >= rdram.ram.size) return;
  unsigned page = address & ~0xfffU;
  if(!executedPages.insert(page).second) return;
  auto data = blob(page, 4096);
  std::fprintf(events, "{\"event\":\"execute_page\",\"field\":%" PRIu64 ",\"pc\":%u,\"page\":%u,\"data\":\"%s\"}\n", fields, unsigned(cpu.ipu.pc), page, data.c_str());
}
void audio(std::uint32_t address, unsigned length) {
  if(!events) return;
  std::fprintf(events, "{\"event\":\"ai_dma\",\"field\":%" PRIu64 ",\"pc\":%u,\"address\":%u,\"length\":%u,\"dac_rate\":%u", fields, unsigned(cpu.ipu.pc), address, length, unsigned(ai.io.dacRate));
  if(remaining && length && length <= 1024 * 1024) {
    auto data = blob(address, length);
    std::fprintf(events, ",\"data\":\"%s\"", data.c_str());
  }
  std::fprintf(events, "}\n");
}
void field() {
  if(!events) return;
  accesses();
  auto& v = vi.io;
  unsigned registers[14] = {
    unsigned(v.colorDepth) | unsigned(v.gammaDither) << 2 | unsigned(v.gamma) << 3 |
      unsigned(v.divot) << 4 | unsigned(v.reserved.bit(5)) << 5 |
      unsigned(v.serrate) << 6 | unsigned(v.reserved.bit(7)) << 7 |
      unsigned(v.antialias) << 8 | (unsigned(v.reserved) & 0xfc00),
    unsigned(v.dramAddress), unsigned(v.width), unsigned(v.coincidence),
    unsigned(v.vcounter) << 1 | unsigned(v.field),
    unsigned(v.hsyncWidth) | unsigned(v.colorBurstWidth) << 8 |
      unsigned(v.vsyncWidth) << 16 | unsigned(v.colorBurstHsync) << 20,
    unsigned(v.halfLinesPerField),
    unsigned(v.quarterLineDuration) | unsigned(v.leapPattern) << 16,
    unsigned(v.hsyncLeap[0]) | unsigned(v.hsyncLeap[1]) << 16,
    unsigned(v.hend) | unsigned(v.hstart) << 16,
    unsigned(v.vend) | unsigned(v.vstart) << 16,
    unsigned(v.colorBurstEnd) | unsigned(v.colorBurstStart) << 16,
    unsigned(v.xscale) | unsigned(v.xsubpixel) << 16,
    unsigned(v.yscale) | unsigned(v.ysubpixel) << 16,
  };
  std::fprintf(events, "{\"event\":\"vi_registers\",\"field\":%" PRIu64 ",\"registers\":[", fields);
  for(unsigned i = 0; i < 14; ++i) std::fprintf(events, "%s%u", i ? "," : "", registers[i]);
  std::fprintf(events, "]}\n");
  std::fprintf(events, "{\"event\":\"vi\",\"field\":%" PRIu64 ",\"clock\":%" PRIi64 ",\"origin\":%u,\"depth\":%u,\"width\":%u,\"serrate\":%u,\"hstart\":%u,\"hend\":%u,\"vstart\":%u,\"vend\":%u,\"xscale\":%u,\"yscale\":%u,\"v_sync\":%u,\"h_sync\":%u}\n", fields, static_cast<std::int64_t>(cpu.profile.cpuCycles), unsigned(v.dramAddress), unsigned(v.colorDepth), unsigned(v.width), unsigned(v.serrate), unsigned(v.hstart), unsigned(v.hend), unsigned(v.vstart), unsigned(v.vend), unsigned(v.xscale), unsigned(v.yscale), unsigned(v.halfLinesPerField), unsigned(v.quarterLineDuration));
  ++fields;
  if(remaining && !--remaining) {
    recordRdp = false;
    cpu.recompiler.enabled = wasJit; rsp.recompiler.enabled = wasRspJit;
    std::fprintf(events, "{\"event\":\"window_end\",\"label\":\"%s\",\"field\":%" PRIu64 "}\n", label.c_str(), fields);
    std::fflush(events);
  }
}
void task() {
  if(!events) return;
  unsigned w[16];
  for(unsigned i = 0; i < 16; ++i) w[i] = rsp.dmem.read<Word>(0xfc0 + i * 4);
  ++tasks;
  std::fprintf(events, "{\"event\":\"sp_start\",\"field\":%" PRIu64 ",\"task\":%" PRIu64 ",\"pc\":%u,\"words\":[", fields, tasks, static_cast<unsigned>(cpu.ipu.pc));
  for(unsigned i = 0; i < 16; ++i) std::fprintf(events, "%s%u", i ? "," : "", w[i]);
  if((w[0] == 1 || w[0] == 2) && w[5] && w[5] <= 4096 && w[7] <= 8192) {
    auto code = blob(w[4], w[5]); auto data = blob(w[6], w[7]);
    std::fprintf(events, "],\"ucode\":\"%s\",\"ucode_data\":\"%s\"", code.c_str(), data.c_str());
    bool full = remaining && ((w[0] == 1 && dumpedGraphics < 4) || (w[0] == 2 && !dumpedAudio));
    if(full) {
      char name[128]; std::snprintf(name, sizeof(name), "%s-task-%" PRIu64 ".rdram.bin", label.c_str(), tasks);
      writeRam(directory + "/" + name, 0, rdram.ram.size);
      std::ofstream dmem(directory + "/" + name + ".dmem.bin", std::ios::binary);
      for(unsigned i = 0; i < 4096; ++i) {
        char b = rsp.dmem.read<Byte>(i); dmem.write(&b, 1);
      }
      if(!dmem) fail("DMEM capture write failed");
      std::fprintf(events, ",\"rdram\":\"%s\"", name);
      if(w[0] == 1) ++dumpedGraphics; else ++dumpedAudio;
    }
  } else std::fprintf(events, "]");
  std::fprintf(events, "}\n");
}
void dp() {
  if(!events) return;
  std::fprintf(events, "{\"event\":\"dp\",\"field\":%" PRIu64 ",\"source\":%u,\"start\":%u,\"end\":%u,\"words\":[", fields, unsigned(rdp.command.source), unsigned(rdp.command.current), unsigned(rdp.command.end));
  bool first = true;
  for(unsigned a = rdp.command.current; a + 8 <= rdp.command.end; a += 8) {
    auto w = static_cast<std::uint64_t>(rdp.command.source ? rsp.dmem.readUnaligned<Dual>(a) : static_cast<Memory::Writable&>(rdram.ram).readUnaligned<Dual>(a));
    std::fprintf(events, "%s\"%016" PRIx64 "\"", first ? "" : ",", w); first = false;
  }
  std::fprintf(events, "]}\n");
}
void dma(bool toRam, std::uint32_t cart, std::uint32_t ram, unsigned length) {
  if(events) std::fprintf(events, "{\"event\":\"pi_dma\",\"field\":%" PRIu64 ",\"pc\":%u,\"to_ram\":%s,\"cart\":%u,\"ram\":%u,\"length\":%u}\n", fields, unsigned(cpu.ipu.pc), toRam ? "true" : "false", cart, ram, length);
}
void flash(std::uint32_t command) {
  if(events) std::fprintf(events, "{\"event\":\"flash\",\"field\":%" PRIu64 ",\"pc\":%u,\"command\":%u}\n", fields, unsigned(cpu.ipu.pc), command);
}
void joybus(unsigned command, unsigned address) {
  if(events && command != 1) std::fprintf(events, "{\"event\":\"joybus\",\"field\":%" PRIu64 ",\"pc\":%u,\"command\":%u,\"address\":%u}\n", fields, unsigned(cpu.ipu.pc), command, address);
}
void bus(std::uint32_t address, unsigned length, unsigned device, bool write) {
  if(!events || !remaining || address >= 0x800000) return;
  busAccesses[(device << 1) | write].first += length;
}
void cpuAccess(std::uint32_t address, unsigned length, bool write) {
  if(!events || !remaining || address >= 0x800000) return;
  if(write && length <= lastRdpWriter.size() - address)
    std::fill_n(lastRdpWriter.begin() + address, length, 0);
  auto key = (std::uint64_t(unsigned(cpu.ipu.pc)) << 32) | (address & ~0xfffU) | write;
  auto& a = cpuAccesses[key]; ++a.count; a.bytes += length;
  a.min = std::min(a.min, address); a.max = std::max(a.max, address + length - 1);
}
void rdpWrite(std::uint32_t address, unsigned length) {
  if(!recordRdp.load(std::memory_order_relaxed) || address >= 0x800000) return;
  std::lock_guard<std::mutex> lock(rdpMutex);
  auto& a = rdpWrites[address & ~0xfffU];
  ++a.count; a.bytes += length;
  a.min = std::min(a.min, address); a.max = std::max(a.max, address + length - 1);
  if(length <= lastRdpWriter.size() - address)
    std::fill_n(lastRdpWriter.begin() + address, length, 1);
}
void cpuRead(std::uint32_t address, unsigned length, std::uint64_t value) {
  if(!events || !remaining || address >= lastRdpWriter.size()
     || length > lastRdpWriter.size() - address) return;
  // Count only reads for which every byte was last written by RDP in this
  // interpreter window, then compare the returned CPU value with physical RAM.
  for(unsigned i = 0; i < length; ++i) if(!lastRdpWriter[address + i]) return;
  std::uint64_t physical = 0;
  for(unsigned i = 0; i < length; ++i) physical = physical << 8 | ramByte(address + i);
  bool equal = length == 8 ? value == physical : (value & ((1ULL << (length * 8)) - 1)) == physical;
  auto key = (std::uint64_t(unsigned(cpu.ipu.pc)) << 32) | (address & ~0xfffU) | equal;
  auto& a = rdpReads[key]; ++a.count; a.bytes += length;
  a.min = std::min(a.min, address); a.max = std::max(a.max, address + length - 1);
}
}
extern "C" void sc64_research_rdp_write(std::uint32_t address, unsigned length) {
  ares::Nintendo64::Stage0::rdpWrite(address, length);
}
