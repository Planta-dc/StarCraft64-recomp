#!/usr/bin/env python3
"""Check original nearest presentation through the real SDL3 shell renderer."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]

def presented_rgb(bgra: bytes, metadata: dict) -> np.ndarray:
    w, h = metadata['window_width'], metadata['window_height']
    nw, nh = metadata['native_width'], metadata['native_height']
    if metadata.get('origin') != 'top-left':
        raise ValueError('Readback rows must be recorded top-down')
    if len(bgra) != w * h * 4:
        raise ValueError('Incomplete GPU readback')
    scale = min(w / nw, h / nh)
    dw, dh = int(nw * scale), int(nh * scale)
    if min(dw, dh) <= 0:
        raise ValueError('Invalid Fit viewport')
    x, bottom = (w - dw) // 2, (h - dh) // 2
    y = h - bottom - dh
    pixels = np.frombuffer(bgra, dtype=np.uint8).reshape(h, w, 4)
    # SDL readback is top-down BGRA. Check the complete Fit viewport;
    # fractional sizes must not be cropped to an integer magnification.
    outside = pixels[:, :, :3].copy()
    outside[y:y + dh, x:x + dw] = 0
    if np.any(outside):
        raise ValueError('Letterbox is not black')
    return pixels[y:y + dh, x:x + dw, :3][:, :, ::-1]

def nearest_fit(source: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    dh, dw = shape
    nh, nw = source.shape[:2]
    xs = np.minimum(((np.arange(dw) + .5) * nw / dw).astype(int), nw - 1)
    ys = np.minimum(((np.arange(dh) + .5) * nh / dh).astype(int), nh - 1)
    return source[ys[:, None], xs[None, :]]

def nearest_valid(source: np.ndarray, captured: np.ndarray) -> bool:
    dh, dw = captured.shape[:2]
    nh, nw = source.shape[:2]
    xn = (2 * np.arange(dw) + 1) * nw
    yn = (2 * np.arange(dh) + 1) * nh
    xs, ys = xn // (2 * dw), yn // (2 * dh)
    # At an exact texel boundary, interpolation precision may select either
    # adjacent texel. Only those boundaries permit an alternate source pixel;
    # a filtered blend or displacement anywhere else must still fail.
    left = np.maximum(xs - (xn % (2 * dw) == 0), 0)
    above = np.maximum(ys - (yn % (2 * dh) == 0), 0)
    valid = np.zeros((dh, dw), dtype=bool)
    for x in (xs, left):
        for y in (ys, above):
            valid |= np.all(captured == source[y[:, None], x[None, :]], axis=2)
    return bool(np.all(valid))

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'local/inputs/renderer/manifest.json')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'local/reports/renderer/fenced-review-fixed')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'local'):
        raise SystemExit('Private reports must remain below ignored local/')
    manifest = json.loads(args.manifest.read_text())
    run_path = output.parent / 'run.json'
    run = json.loads(run_path.read_text())
    if run.get('schema') != 3 or run['exit_code'] != 0 or not run['binary_unchanged'] \
            or not run.get('resources_unchanged', False):
        raise ValueError('GPU probe needs a completed run with unchanged binary and resources; legacy receipts must be rerun')
    manifest_hash = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    if run['inputs']['gpu_probe']['sha256'] != manifest_hash:
        raise ValueError('GPU probe manifest differs from the run receipt')
    results = []
    for index, item in enumerate(manifest['cases']):
        prefix = output / f'case-{index}'
        metadata = json.loads(prefix.with_suffix('.json').read_text())
        if metadata['case'] != item['id']:
            raise ValueError('Captured case identity mismatch')
        if metadata['sdl_version'] != run['build']['sdl3_version'] or metadata['source_ram_sha256'] != item['ram_sha256']:
            raise ValueError('Native capture provenance differs from the run/source receipt')
        ram = Path(item['source_ram']).read_bytes()
        if hashlib.sha256(ram).hexdigest() != item['ram_sha256']:
            raise ValueError('Source RAM freshness mismatch')
        w, h = metadata['native_width'], metadata['native_height']
        expected = np.frombuffer(prefix.with_suffix('.rgba').read_bytes(), dtype=np.uint8).reshape(h, w, 4)[:, :, :3]
        baseline = np.asarray(Image.open(args.baseline / item['id'] / 'actual.png').convert('RGB'))
        baseline_equal = bool(np.array_equal(expected, baseline))
        captured = presented_rgb(prefix.with_suffix('.bgra').read_bytes(), metadata)
        reference = nearest_fit(expected, captured.shape[:2])
        gpu_equal = bool(np.array_equal(captured, reference))
        gpu_nearest_valid = nearest_valid(expected, captured)
        errors = np.abs(captured.astype(np.int16) - reference.astype(np.int16))
        Image.fromarray(expected).save(prefix.with_suffix('.png'))
        results.append({'id': item['id'], 'native_width': w, 'native_height': h,
                        'baseline_rgb_exact': baseline_equal, 'gpu_rgb_exact': gpu_equal,
                        'gpu_nearest_valid': gpu_nearest_valid,
                        'max_channel_error': int(errors.max()),
                        'readback_sha256': hashlib.sha256(prefix.with_suffix('.bgra').read_bytes()).hexdigest(),
                        'software_rgba_sha256': hashlib.sha256(prefix.with_suffix('.rgba').read_bytes()).hexdigest(),
                        'baseline_png_sha256': hashlib.sha256((args.baseline / item['id'] / 'actual.png').read_bytes()).hexdigest()})
    renderers = sorted({json.loads((output / f'case-{i}.json').read_text())['renderer'] for i in range(len(results))})
    report = {'schema': 4, 'scope': f"SDL {run['build']['sdl3_version']} {run['build']['profile']} "
              f"{'/'.join(renderers)} nearest presentation", 'renderers': renderers,
              'boundary_rule': 'Either adjacent source texel only at an exact rational texel boundary',
              'resources_unchanged': run['resources_unchanged'],
              'presentation_accepted': len(results) == 20 and all(r['baseline_rgb_exact'] and r['gpu_nearest_valid'] for r in results),
              'cases': results, 'manifest_sha256': manifest_hash,
              'binary_sha256': run['build']['binary_sha256'], 'run_sha256': hashlib.sha256(run_path.read_bytes()).hexdigest()}
    (output / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not report['presentation_accepted']:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
