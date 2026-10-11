#pragma once
#include <cstdint>
namespace ares::Nintendo64::Stage0 {
void start(const char* directory);
void stop();
void window(const char* label, unsigned fields);
void snapshot(const char* label);
void saveState(const char* path);
void loadState(const char* path);
void loadFlash(const char* path);
void execute(std::uint32_t address);
void audio(std::uint32_t address, unsigned length);
void rdpWrite(std::uint32_t address, unsigned length);
void cpuRead(std::uint32_t address, unsigned length, std::uint64_t value);
void field();
void task();
void dp();
void dma(bool toRam, std::uint32_t cart, std::uint32_t ram, unsigned length);
void flash(std::uint32_t command);
void joybus(unsigned command, unsigned address);
void bus(std::uint32_t address, unsigned length, unsigned device, bool write);
void cpuAccess(std::uint32_t address, unsigned length, bool write);
}
