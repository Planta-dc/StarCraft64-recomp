#!/usr/bin/env python3
"""Reject private game output missing the observers required by pointer input."""
from __future__ import annotations
import argparse
from pathlib import Path


def validate_ui_hooks(generated: Path) -> None:
    files = sorted(generated.glob('funcs_*.c'))
    if not files:
        raise ValueError('Private game lacks funcs_*.c; generate the Stage 4 game first')
    source = '\n'.join(path.read_text() for path in files)
    required = {
        'sc64_ui_font(rdram, ctx,': 8,
        'sc64_ui_blit(rdram, ctx);': 1,
        'sc64_ui_briefing(rdram, ctx,': 2,
        **{f'sc64_ui_hud_{kind}(rdram, ctx);': 1 for kind in ('begin', 'end', 'present')},
        **{f'sc64_ui_hud_font(rdram, ctx, {kind});': 1 for kind in range(3)},
        **{f'sc64_ui_main(rdram, ctx, {kind});': 1 for kind in range(4)},
        '// 0x801296C8: nop': 1,
        **{f'sc64_ui_pick(rdram, ctx, {kind});': 1 for kind in range(2)},
    }
    for anchor, expected in required.items():
        actual = source.count(anchor)
        if actual != expected:
            raise ValueError(f'Private game observer/patch mismatch: {anchor!r}: '
                             f'expected {expected}, found {actual}. Regenerate with '
                             'tools/input/add_ui_hooks.py and tools/recompile/run_recompiler.py')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('generated', type=Path)
    args = parser.parse_args()
    try:
        validate_ui_hooks(args.generated)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
