#!/usr/bin/env python3
"""Apply source-only research hooks to a pinned ares-64 checkout, fail on drift."""
import argparse
from pathlib import Path
import shutil
import subprocess
import re

PIN = '6b65e1beacf8b2af66aaee72541ab154382b7e6a'
RDP_PIN = '9c8b9ed3e7d7f00dff8bc872ccdd3fba1a3673fc'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--reference', type=Path, required=True,
                        help='Pinned ata4/angrylion-rdp-plus checkout')
    args = parser.parse_args()
    root = args.checkout.resolve()
    revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PIN:
        parser.error(f'expected ares-64 {PIN}, got {revision}')
    reference = args.reference.resolve()
    rdp_revision = subprocess.check_output(
        ['git', '-C', str(reference), 'rev-parse', 'HEAD'], text=True).strip()
    if rdp_revision != RDP_PIN:
        parser.error(f'expected Angrylion {RDP_PIN}, got {rdp_revision}')
    def edit(path, old, new, count=1):
        file = root / path
        text = file.read_text()
        if new in text:
            return
        if text.count(old) != count:
            raise RuntimeError(f'{path}: expected {count} matching source anchors')
        file.write_text(text.replace(old, new))
    source = Path(__file__).resolve().parent
    # Keep the fork's ABI header for adapter declarations, but use the upstream
    # rasterizer: the fork introduced an alignment check that rejects this game.
    for file in (reference / 'src/core').rglob('*'):
        if file.is_file() and file.name != 'n64video.h':
            target = root / 'thirdparty/angrylion-rdp-plus/src/core' / file.relative_to(reference / 'src/core')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
    core = root / 'thirdparty/angrylion-rdp-plus/src/core/n64video.c'
    core.write_text(core.read_text() + '\n' + (source / 'angrylion_bridge.inc').read_text())
    memory = core.parent / 'n64video/rdp/rdram.c'
    memory_text = memory.read_text()
    memory_text = 'extern void sc64_research_rdp_write(uint32_t, unsigned);\n' + memory_text
    for bits, scale in [(8, 1), (16, 2), (32, 4)]:
        pattern = rf'(rdram{bits}\[(?:in \^ (?:BYTE|WORD)_ADDR_XOR|in)\] = [^;]+;)'
        memory_text, count = re.subn(pattern,
            rf'sc64_research_rdp_write(in * {scale}, {scale}); \1', memory_text)
        if count == 0:
            raise RuntimeError(f'no upstream RDRAM {bits}-bit write sites')
    memory.write_text(memory_text)
    for name, target in [('ares_capture.hpp', 'ares/n64/sc64-research.hpp'),
                         ('ares_capture.cpp', 'ares/n64/sc64-research.cpp'),
                         ('ares_js.inc', 'test-runner/sc64-research-js.inc')]:
        shutil.copyfile(source / name, root / target)
    header = root / 'ares/n64/sc64-research.hpp'
    text = header.read_text().replace('void start(', 'inline bool expansion = true;\nvoid start(')
    header.write_text(text)
    edit('test-runner/CMakeLists.txt', 'OR OS_WINDOWS))', 'OR OS_WINDOWS OR OS_MACOS))')
    edit('ares/n64/n64.hpp', '#pragma once', '#pragma once\n#include <n64/sc64-research.hpp>')
    edit('ares/n64/n64.cpp', '#include <n64/aleck64/aleck64.cpp>',
         '#include <n64/aleck64/aleck64.cpp>\n#include <n64/sc64-research.cpp>')
    edit('ares/n64/rsp/io.cpp', '    //SP_STATUS\n    if(data.bit( 0)', '    //SP_STATUS\n    if(status.halted && data.bit(0) && !data.bit(1)) Stage0::task();\n    if(data.bit( 0)')
    edit('ares/n64/rdp/render.cpp', 'auto RDP::render() -> void {', 'auto RDP::render() -> void {\n  Stage0::dp();')
    edit('ares/n64/vi/vi.cpp', 'auto VI::refresh() -> void {', 'auto VI::refresh() -> void {\n  Stage0::field();')
    edit('ares/n64/pi/dma.cpp', 'auto PI::dmaWrite() -> void {',
         'auto PI::dmaWrite() -> void {\n  Stage0::dma(true, io.pbusAddress, io.dramAddress, io.writeLength + 1);')
    edit('ares/n64/pi/dma.cpp', 'auto PI::dmaRead() -> void {',
         'auto PI::dmaRead() -> void {\n  Stage0::dma(false, io.pbusAddress, io.dramAddress, (io.readLength | 1) + 1);')
    edit('ares/n64/cartridge/flash.cpp', 'auto Cartridge::Flash::command(u32 data) -> void {',
         'auto Cartridge::Flash::command(u32 data) -> void {\n  Stage0::flash(data);')
    edit('ares/n64/controller/gamepad/gamepad.cpp',
         'auto Gamepad::comm(n8 send, n8 recv, n8 input[], n8 output[]) -> n2 {',
         'auto Gamepad::comm(n8 send, n8 recv, n8 input[], n8 output[]) -> n2 {\n  Stage0::joybus(input[0], (unsigned(input[1]) << 8 | unsigned(input[2])) & ~31U);')
    for name, write in [('read', 'false'), ('write', 'true')]:
        old = f'auto CPU::{name}(PhysAccess access' + (') -> maybe<u64> {' if name == 'read' else ', u64 data) -> bool {')
        new = old + f'\n  if(access) Stage0::cpuAccess(access.paddr, Size, {write});'
        edit('ares/n64/cpu/memory.cpp', old, new)
    edit('ares/n64/cpu/memory.cpp',
         '  if(access.cache) return dcache.read<Size>(access.vaddr, paddr);\n  return busRead<Size>(paddr);',
         '  maybe<u64> value = access.cache ? maybe<u64>(dcache.read<Size>(access.vaddr, paddr)) : busRead<Size>(paddr);\n'
         '  if(value) Stage0::cpuRead(paddr, Size, *value);\n  return value;')
    for signature, body in [
        ('read(u32 address, RBusDevice device) -> u64', 'Stage0::bus(address, Size, unsigned(device), false);'),
        ('write(u32 address, u64 value, RBusDevice device) -> void', 'Stage0::bus(address, Size, unsigned(device), true);'),
        ('readBurst(u32 address, u32 *value, RBusDevice device) -> void', 'Stage0::bus(address, Size, unsigned(device), false);'),
        ('writeBurst(u32 address, u32 *value, RBusDevice device) -> void', 'Stage0::bus(address, Size, unsigned(device), true);'),
        ('ebusRead(u32 address) -> u64', 'Stage0::bus(address, Size, unsigned(RBusDevice::VR4300_UNCACHED), false);'),
        ('ebusWrite(u32 address, u64 value) -> void', 'Stage0::bus(address, Size, unsigned(RBusDevice::VR4300_UNCACHED), true);')]:
        old = 'auto ' + signature + ' {'
        edit('ares/n64/rdram/rdram.hpp', old, old + '\n      ' + body)
    edit('test-runner/runner.cpp', 'option("Expansion Pak", "true");',
         'option("Expansion Pak", ares::Nintendo64::Stage0::expansion ? "true" : "false");')
    edit('test-runner/runner.cpp',
         '  if(node->name() == "Nintendo 64 Cartridge" && gamePak) return gamePak->pak;',
         '  if(node->name() == "Nintendo 64 Cartridge" && gamePak) return gamePak->pak;\n'
         '  if(node->name() == "Gamepad") {\n'
         '    auto pak = std::make_shared<vfs::directory>();\n'
         '    pak->append("save.pak", 32768);\n'
         '    return pak; // isolated formatted Controller Pak, no disk persistence\n'
         '  }')
    edit('test-runner/js-host.cpp', '}  //namespace\n\nauto jsHostInit',
         '#include "sc64-research-js.inc"\n\n}  //namespace\n\nauto jsHostInit')
    names = ['Start', 'Stop', 'Window', 'Snapshot', 'SaveState', 'LoadState', 'Expansion', 'Pak', 'LoadFlash']
    anchor = '  setFn(g_ctx, ares, "loadRom", js_loadRom, 1);'
    registrations = [f'  setFn(g_ctx, ares, "research{name}", js_research{name}, 2);' for name in names]
    js_host = root / 'test-runner/js-host.cpp'
    js_text = '\n'.join(line for line in js_host.read_text().splitlines()
                        if line not in registrations) + '\n'
    if js_text.count(anchor) != 1:
        raise RuntimeError('js-host.cpp: expected one loadRom registration anchor')
    js_host.write_text(js_text.replace(anchor, anchor + '\n' + '\n'.join(registrations)))
    # This fork keeps RSP DMEM in byte order, unlike word-swapped RDRAM.
    # Angrylion expects native u32 words for its XBUS DMA input.
    edit('ares/n64/angrylion/angrylion.cpp', '  u32  miIntrReg = 0;',
         '  u32  dmemWords[1024] = {};\n  u32  miIntrReg = 0;')
    edit('ares/n64/angrylion/angrylion.cpp', '  config.gfx.dmem         = dmem;',
         '  config.gfx.dmem         = reinterpret_cast<u8*>(dmemWords);')
    edit('ares/n64/angrylion/angrylion.cpp', '  auto& command = rdp.command;',
         '  auto& command = rdp.command;\n'
         '  if(command.source) for(u32 i = 0; i < 1024; ++i)\n'
         '    implementation->dmemWords[i] = rsp.dmem.read<Word>(i * 4);')
    # Partial RDP commands must retain only the remaining u32 words, not len - 1.
    edit('thirdparty/angrylion-rdp-plus/src/core/n64video.c',
         'toload = MIN(dp_end_al - dp_current_al, rdp_cmd_len - 1);',
         'toload = MIN(dp_end_al - dp_current_al, rdp_cmd_len - rdp_cmd_pos);')
    edit('ares/n64/cpu/cpu.cpp', '  if(!access) return true;\n\n  if(Accuracy::CPU::Recompiler',
         '  if(!access) return true;\n  Stage0::execute(access.paddr);\n\n  if(Accuracy::CPU::Recompiler')
    edit('ares/n64/ai/io.cpp', '      io.dmaLength[io.dmaCount] = length;',
         '      Stage0::audio(io.dmaAddress[io.dmaCount], length);\n      io.dmaLength[io.dmaCount] = length;')
    edit('ares/n64/angrylion/msg.cpp',
         '  debug(unusual, "[angrylion] ", buffer);',
         '  std::fprintf(stderr, "[angrylion] %s\\n", buffer);', count=2)
    # nall Path::program() assumes an app bundle on macOS; this runner is a CLI.
    edit('mia/mia.cpp', '  // 1. The application directory',
         '  if(const char* base = std::getenv("SC64_RESEARCH_FIRMWARE")) {\n'
         '    string explicitPath = {base, "/", name};\n'
         '    if(inode::exists(explicitPath)) return explicitPath;\n'
         '  }\n\n  // 1. The application directory')
    print(f'Research hooks applied to {root} at {PIN}')

if __name__ == '__main__':
    main()
