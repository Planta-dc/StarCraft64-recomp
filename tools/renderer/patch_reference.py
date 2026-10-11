#!/usr/bin/env python3
"""Add opt-in post-FULLSYNC snapshots to the exact accepted local ares harness."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PINS = {'ares/n64/sc64-research.cpp': '89fc4b0f68c5c7da37e775a520859c20f75e5067262c9d58c2151aed1369eabf',
        'ares/n64/angrylion/angrylion.cpp': '5b9e273dd80c84aae5ae58af46f320086fe258ae7464c872fcf87ed5225b3ec7'}


def patch(root: Path):
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != '6b65e1beacf8b2af66aaee72541ab154382b7e6a':
        raise ValueError('Unexpected ares revision')
    marker = root / 'sc64-reference-patch.json'
    if marker.exists():
        for path, key in json.loads(marker.read_text())['outputs'].items():
            if hashlib.sha256((root/path).read_bytes()).hexdigest() != key:
                raise ValueError('Changed Stage2 patched source')
        return
    texts = {}
    for path, expected in PINS.items():
        data = (root/path).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'{path}: Stage0 source digest differs')
        texts[path] = data.decode()
    capture = texts['ares/n64/sc64-research.cpp']
    capture = capture.replace('std::string label;', 'std::string label;\nstd::string stage2Pending;')
    capture = capture.replace('void task() {\n', 'void task() {\n  stage2Pending.clear();\n', 1)
    capture = capture.replace('      writeRam(directory + "/" + name, 0, rdram.ram.size);',
                              '      writeRam(directory + "/" + name, 0, rdram.ram.size);\n'
                              '      if(std::getenv("SC64_STAGE2_POST_TASK")) stage2Pending = name;', 1)
    anchor = 'void dp() {'
    if capture.count(anchor) != 1:
        raise ValueError('DP source anchor differs')
    capture = capture.replace(anchor, '''// Called by Angrylion's SyncFull interrupt after cmd_flush has joined workers.
void stage2Finished(const std::uint8_t* hidden, unsigned entries) {
  if(!events || stage2Pending.empty()) return;
  auto path = stage2Pending + ".post.bin";
  writeRam(directory + "/" + path, 0, rdram.ram.size);
  std::ofstream out(directory + "/" + stage2Pending + ".hidden-post.bin", std::ios::binary);
  out.write(reinterpret_cast<const char*>(hidden), entries);
  if(!out) fail("post-task hidden coverage capture failed");
  std::fprintf(events, "{\\"event\\":\\"stage2_post_task\\",\\"task\\":%" PRIu64 ",\\"field\\":%" PRIu64 ",\\"rdram\\":\\"%s\\",\\"fence\\":\\"Angrylion SyncFull after worker join\\"}\\n", tasks, fields, path.c_str());
  std::fflush(events);stage2Pending.clear();
}
void dp() {''', 1)
    adapter = texts['ares/n64/angrylion/angrylion.cpp']
    anchor = '  rdp.syncFull();'
    if adapter.count(anchor) != 1:
        raise ValueError('Interrupt anchor differs')
    adapter = adapter.replace(anchor, '''  const std::uint8_t* hidden = nullptr; std::uint32_t entries = 0;
  n64video_hidden_rdram_get(&hidden, &entries);
  Stage0::stage2Finished(hidden, entries);
  rdp.syncFull();''')
    adapter = adapter.replace('Angrylion angrylion;',
                              'namespace Stage0 { void stage2Finished(const std::uint8_t*, unsigned); }\nAngrylion angrylion;')
    outputs = {'ares/n64/sc64-research.cpp': capture, 'ares/n64/angrylion/angrylion.cpp': adapter}
    for path, text in outputs.items():
        (root/path).write_text(text)
    marker.write_text(json.dumps(dict(schema=1, input_hashes=PINS,
                      outputs={p: hashlib.sha256(t.encode()).hexdigest() for p, t in outputs.items()}), indent=2)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('checkout', type=Path)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    checkout = args.checkout.resolve()
    if not checkout.is_relative_to(root/'local'):
        p.error('Use the ignored local/ research checkout')
    patch(checkout)
    print('Post-task capture is opt-in via SC64_STAGE2_POST_TASK=1')


if __name__ == '__main__':
    main()
