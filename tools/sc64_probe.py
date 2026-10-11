#!/usr/bin/env python3
"""Probe StarCraft 64 BOLT-extracted assets: CHK maps, GRP candidates, images, palettes, audio.

Usage: python3 tools/sc64_probe.py [local/extracted/sc64-usa] [--png local/OUT_DIR]

Sample PNGs are game-derived, so --png must name a directory under local/.
"""
import argparse
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from private_paths import ROOT, PrivatePathError, require_local

DEFAULT_INPUT = ROOT / "local/extracted/sc64-usa"


def u16be(d, o):
    return struct.unpack_from(">H", d, o)[0]


def u16le(d, o):
    return struct.unpack_from("<H", d, o)[0]


def u32le(d, o):
    return struct.unpack_from("<I", d, o)[0]


def walk(root):
    for dirpath, _, files in os.walk(root):
        for f in files:
            yield os.path.join(dirpath, f)


# ---------- CHK ----------
def chk_sections(d):
    """SC64 campaign CHKs: every section is tag + u32 LE size + data (incl. TYPE/VER/IVE2/VCOD)."""
    secs = {}
    off = 0
    while off + 8 <= len(d):
        tag = d[off:off + 4]
        size = struct.unpack_from("<I", d, off + 4)[0]
        if off + 8 + size > len(d) + 16:  # implausible: stop
            break
        secs.setdefault(tag, (off, size))
        off += 8 + size
    return secs


def chk_info(d):
    secs = chk_sections(d)
    info = {"sections": [s.decode("ascii", "replace") for s in secs]}
    if b"DIM " in secs:
        o = secs[b"DIM "][0] + 8
        info["dims"] = (u16le(d, o), u16le(d, o + 2))
    if b"ERA " in secs:
        info["tileset"] = u16le(d, secs[b"ERA "][0] + 8)
    title = None
    if b"STR " in secs:
        so = secs[b"STR "][0] + 8
        n = u16le(d, so)
        s0 = u16le(d, so + 2)
        if 0 < n and s0 < len(d):
            e = d.find(b"\0", so + s0)
            title = d[so + s0:so + s0 + (e - so - s0)].decode("cp1252", "replace")
    info["title"] = title
    if b"UNIT" in secs:
        o, size = secs[b"UNIT"]
        info["units"] = size // 36
    return info


# ---------- GRP (relaxed) ----------
def grp_relaxed(d):
    """Return (frames, w, h) if the file plausibly is a PC GRP, else None."""
    if len(d) < 16:
        return None
    frames = u16le(d, 0)
    w, h = u16le(d, 2), u16le(d, 4)
    if not (0 < frames < 2000) or w == 0 or h == 0:
        return None
    if 6 + frames * 8 > len(d):
        return None
    # all frame boxes inside canvas, offsets monotonic-ish and in bounds
    last = 6 + frames * 8
    for i in range(frames):
        dx, dy, fw, fh = d[6 + i * 8:10 + i * 8]
        if fw == 0 or fh == 0 or dx + fw > w or dy + fh > h:
            return None
        off = u32le(d, 6 + i * 8 + 4)
        if off < last or off >= len(d):
            return None
    return frames, w, h


# ---------- PNG out ----------
def write_png(path, w, h, argb_rows):
    import zlib
    raw = b"".join(b"\x00" + bytes(r) for r in argb_rows)
    def chunk(t, data):
        c = struct.pack(">I", len(data)) + t + data
        return c + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def load_pal(d):
    # u16 unk(0), u16 low(0), u16 high(255), then 256 * u16 5551
    cols = []
    for i in range(256):
        v = u16be(d, 6 + i * 2)
        r5 = (v >> 11) & 0x1F
        g5 = (v >> 6) & 0x1F
        b5 = (v >> 1) & 0x1F
        a = (v & 1) * 255
        cols.append(((r5 << 3) | (r5 >> 2), (g5 << 3) | (g5 >> 2), (b5 << 3) | (b5 >> 2), a))
    return cols


def img_to_png(data, pal, out):
    w, h = u16be(data, 8), u16be(data, 10)
    rows = []
    o = 16
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = pal[data[o + y * w + x]]
            row += [r, g, b, a]
        rows.append(row)
    write_png(out, w, h, rows)


def grp_to_png(data, pal, out, frame=0):
    frames = u16le(data, 0)
    w, h = u16le(data, 2), u16le(data, 4)
    rows = [[(0, 0, 0, 0)] * w for _ in range(h)]
    dx, dy, fw, fh = data[6 + frame * 8:10 + frame * 8]
    off = u32le(data, 6 + frame * 8 + 4)
    for y in range(fh):
        x = 0
        while x < fw:
            ctrl = data[off]
            off += 1
            if ctrl & 0x80:
                x += ctrl & 0x7F
            elif ctrl:
                for _ in range(ctrl):
                    rows[dy + y][dx + x] = pal[data[off]]
                    off += 1
                    x += 1
            else:
                break
    rows2 = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = rows[y][x]
            row += [r, g, b, a]
        rows2.append(row)
    write_png(out, w, h, rows2)


def read(path):
    return Path(path).read_bytes()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path, nargs="?", default=DEFAULT_INPUT,
                        help="bolt_extract.py output (default: local/extracted/sc64-usa)")
    parser.add_argument("--png", type=Path, metavar="OUT_DIR",
                        help="write sample PNGs to this directory under local/")
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print("sc64_probe: extracted asset directory not found: %s" % args.root, file=sys.stderr)
        return 2
    root = str(args.root)
    png_out = None
    if args.png is not None:
        try:
            png_out = str(require_local(args.png, root=ROOT, what="PNG output"))
        except PrivatePathError as error:
            print("sc64_probe: %s" % error, file=sys.stderr)
            return 2
        os.makedirs(png_out, exist_ok=True)

    chks, grps, imgs, pals, pcms, other = [], [], [], [], [], []
    for p in walk(root):
        ext = p.rsplit(".", 1)[-1]
        d = read(p)
        rel = os.path.relpath(p, root)
        if ext == "chk":
            chks.append((rel, chk_info(d)))
        elif ext == "unk":
            g = grp_relaxed(d)
            if g:
                grps.append((rel, g))
            else:
                other.append((rel, len(d), d[:8].hex()))
        elif ext == "unkimg":
            imgs.append((rel, (u16be(d, 8), u16be(d, 10))))
        elif ext == "unkpal":
            pals.append(rel)
        elif ext == "unkpcm":
            pcms.append((rel, d[0], d[1], u16be(d, 2), len(d)))

    print("== CHK maps (%d) ==" % len(chks))
    for rel, info in chks:
        dims = info.get("dims", ("?", "?"))
        print("  %-28s %4sx%-4s tileset=%-2s units=%-4s  %s"
              % (rel.split("/")[-1], dims[0], dims[1], info.get("tileset"),
                 info.get("units"), (info.get("title") or "")[:48]))

    print("\n== GRP candidates among .unk (%d) ==" % len(grps))
    for rel, (frames, w, h) in grps[:20]:
        print("  %-28s frames=%-4d %dx%d" % (rel.split("/")[-1], frames, w, h))
    if len(grps) > 20:
        print("  ... and %d more" % (len(grps) - 20))

    print("\n== unkimg count: %d, unkpal count: %d ==" % (len(imgs), len(pals)))
    for rel, (w, h) in imgs[:10]:
        print("  %-28s %dx%d" % (rel.split("/")[-1], w, h))

    print("\n== unkpcm headers (first 8) ==")
    for rel, ch, bits, rate, size in pcms[:8]:
        print("  %-28s channels=%d bits=%d rate=%d bytes=%d" % (rel.split("/")[-1], ch, bits, rate, size))

    print("\n== unclassified .unk: %d (sample headers) ==" % len(other))
    for rel, size, hdr in other[:15]:
        print("  %-28s %7d  %s" % (rel.split("/")[-1], size, hdr))

    if png_out:
        # first image + first palette from same dir if possible
        if imgs and pals:
            img_dir = os.path.dirname(imgs[0][0])
            cand = [p for p in pals if os.path.dirname(p) == img_dir]
            pal_file = cand[0] if cand else pals[0]
            pal = load_pal(read(os.path.join(root, pal_file)))
            img_to_png(read(os.path.join(root, imgs[0][0])), pal,
                       os.path.join(png_out, "sample_image.png"))
            print("\nwrote %s/sample_image.png (img=%s pal=%s)" % (png_out, imgs[0][0], pal_file))
        if grps:
            g_dir = os.path.dirname(grps[0][0])
            cand = [p for p in pals if os.path.dirname(p) == g_dir]
            if cand:
                pal = load_pal(read(os.path.join(root, cand[0])))
                grp_to_png(read(os.path.join(root, grps[0][0])), pal,
                           os.path.join(png_out, "sample_grp.png"))
                print("wrote %s/sample_grp.png (grp=%s pal=%s)" % (png_out, grps[0][0], cand[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
