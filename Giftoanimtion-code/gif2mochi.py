#!/usr/bin/env python3
"""
gif2mochi.py  (v2)  -  convert GIFs into Mochi Desk animation headers.

Put your .gif files next to this script and just run it. It finds them, asks
which to convert, encodes it, and registers it in animations.h for you.

    python3 gif2mochi.py                      interactive, pick from a menu
    python3 gif2mochi.py sad.gif              convert one file
    python3 gif2mochi.py sad.gif --preview    write a PNG first, do not encode
    python3 gif2mochi.py --all                convert every GIF in the folder
    python3 gif2mochi.py --list               show what is registered now
    python3 gif2mochi.py --remove sad         unregister and delete a header
    python3 gif2mochi.py --budget             flash usage of all animations

Tuning:
    --threshold 130      raise if the result is too white, lower if too dark
    --invert             for GIFs with a light background and a dark subject
    --max-frames 120     evenly subsample a long clip
    --no-autocrop        keep the original framing
    --no-denoise         skip the median filter (use on clean vector art)

Format: each 128x64 frame is packed 1 bit per pixel (1024 bytes, row-major,
MSB first), XORed against the previous frame, then PackBits compressed. That
is exactly what decodeFrame() in MochiDesk.ino reverses.

Requires: pip install pillow
"""

import argparse
import glob
import os
import re
import sys

try:
    from PIL import Image, ImageFilter, ImageDraw
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

W, H = 128, 64
FRAME_BYTES = W * H // 8          # 1024
MAX_BLOB = 65535                  # the uint16 offset table cannot address more
IMAGE_EXT = (".gif", ".png", ".webp", ".apng")


# =============================================================== frame loading
def load_frames(path):
    """Accepts an animated file, or a folder of numbered still images."""
    if os.path.isdir(path):
        files = sorted(f for f in glob.glob(os.path.join(path, "*"))
                       if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")))
        if not files:
            sys.exit(f"no images found in folder {path}")
        return [Image.open(f).convert("L") for f in files]

    im = Image.open(path)
    out, i = [], 0
    try:
        while True:
            im.seek(i)
            out.append(im.convert("L").copy())
            i += 1
    except EOFError:
        pass
    if not out:
        sys.exit(f"no frames found in {path}")
    return out


def subsample(frames, limit):
    if not limit or len(frames) <= limit:
        return frames
    step = len(frames) / limit
    return [frames[int(i * step)] for i in range(limit)]


# =============================================================== image pipeline
def content_box(frames, thr=150):
    """Union of the bright area across the clip, padded, forced to 2:1."""
    box = None
    for g in frames[::3]:
        b = g.filter(ImageFilter.MedianFilter(5)).point(
            lambda p: 255 if p > thr else 0).getbbox()
        if b is None:
            continue
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                     max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        box = (0, 0) + frames[0].size

    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    w, h = (box[2] - box[0]) * 1.10, (box[3] - box[1]) * 1.18
    if w / h < 2.0:
        w = h * 2.0
    else:
        h = w / 2.0
    return (int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2))


def to_bits(gray, box, thr, denoise=True, invert=False):
    if denoise:
        gray = gray.filter(ImageFilter.MedianFilter(3))
    im = gray.crop(box).resize((W, H), Image.LANCZOS)
    if invert:
        im = im.point(lambda p: 255 - p)
    return im.point(lambda p: 255 if p > thr else 0).convert("1")


def pack(img):
    """Row-major, MSB first - the layout Adafruit_GFX drawBitmap expects."""
    px = img.load()
    out = bytearray()
    for y in range(H):
        for xb in range(W // 8):
            b = 0
            for bit in range(8):
                if px[xb * 8 + bit, y]:
                    b |= (0x80 >> bit)
            out.append(b)
    return bytes(out)


# =============================================================== PackBits
def packbits(data):
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        run = 1
        while i + run < n and data[i + run] == data[i] and run < 128:
            run += 1
        if run >= 2:                       # repeat run
            out.append(256 - (run - 1))    # 129..255 reads as int8 -1..-127
            out.append(data[i])
            i += run
        else:                              # literal run
            j, lit = i + 1, 1
            while j < n and lit < 128:
                if j + 1 < n and data[j] == data[j + 1]:
                    break
                j += 1
                lit += 1
            out.append(lit - 1)            # 0..127
            out += data[i:i + lit]
            i = j
    return bytes(out)


def unpackbits(c, size):
    """Mirrors decodeFrame() in the sketch - used for the round-trip check."""
    out, i = bytearray(), 0
    while len(out) < size and i < len(c):
        t = c[i]
        i += 1
        if t < 128:
            out += c[i:i + t + 1]
            i += t + 1
        else:
            out += bytes([c[i]]) * (257 - t)
            i += 1
    return bytes(out)


# =============================================================== encoding
def encode(frames, box, thr, denoise, invert):
    prev = bytes(FRAME_BYTES)
    blob, offsets = bytearray(), []
    for g in frames:
        cur = pack(to_bits(g, box, thr, denoise, invert))
        offsets.append(len(blob))
        blob += packbits(bytes(x ^ y for x, y in zip(cur, prev)))
        prev = cur
    offsets.append(len(blob))
    return bytes(blob), offsets


def roundtrip_ok(blob, offsets, nframes):
    acc = bytearray(FRAME_BYTES)
    for i in range(nframes):
        d = unpackbits(blob[offsets[i]:offsets[i + 1]], FRAME_BYTES)
        if len(d) != FRAME_BYTES:
            return False
        acc = bytearray(x ^ y for x, y in zip(acc, d))
    return True


def write_header(outdir, sym, label, blob, offsets, nframes):
    def hexblob(data, per=16):
        return ",\n".join("  " + ", ".join(f"0x{b:02x}" for b in data[i:i + per])
                          for i in range(0, len(data), per))

    path = os.path.join(outdir, f"anim_{sym}.h")
    with open(path, "w") as fh:
        fh.write(f"// {label} - {nframes} frames, {W}x{H}, XOR-delta + PackBits\n")
        fh.write("#pragma once\n#include <Arduino.h>\n\n")
        fh.write(f"#define {sym.upper()}_FRAMES {nframes}\n\n")
        fh.write(f"const uint16_t {sym}_offsets[{len(offsets)}] PROGMEM = {{\n")
        fh.write(",\n".join("  " + ", ".join(str(o) for o in offsets[i:i + 16])
                            for i in range(0, len(offsets), 16)))
        fh.write("\n};\n\n")
        fh.write(f"const uint8_t {sym}_data[{len(blob)}] PROGMEM = {{\n{hexblob(blob)}\n}};\n")
    return path


# =============================================================== preview
def write_preview(frames, box, thr, denoise, invert, sym, outdir):
    idxs = [int(i * (len(frames) - 1) / 5) for i in range(6)]
    cw, ch = 260, 152
    sheet = Image.new("RGB", (cw * 3, ch * 2), (20, 22, 26))
    d = ImageDraw.Draw(sheet)
    for n, fi in enumerate(idxs):
        img = to_bits(frames[fi], box, thr, denoise, invert)
        img = img.convert("RGB").resize((cw - 16, ch - 34), Image.NEAREST)
        x, y = (n % 3) * cw, (n // 3) * ch
        sheet.paste(img, (x + 8, y + 8))
        d.text((x + 8, y + ch - 22), f"frame {fi}", fill=(255, 176, 0))
    path = os.path.join(outdir, f"preview_{sym}.png")
    sheet.save(path)
    return path


# =============================================================== animations.h
ROW_RE = re.compile(r'\{\s*"([^"]*)"\s*,\s*(\w+)_data\s*,\s*\2_offsets\s*,\s*\w+_FRAMES\s*\}')

HEADER_TOP = """// Auto-generated index of all Mochi animations.
// Each frame is XOR-delta encoded against the previous frame, then PackBits
// compressed. Maintained by tools/gif2mochi.py.
#pragma once
#include <Arduino.h>

"""


def read_registry(path):
    if not os.path.exists(path):
        return []
    txt = open(path).read()
    return [(m.group(2), m.group(1).strip()) for m in ROW_RE.finditer(txt)]


def write_registry(path, rows):
    out = [HEADER_TOP]
    for sym, _ in rows:
        out.append(f'#include "anim_{sym}.h"\n')
    out.append("""
struct Anim {
  const char*     name;
  const uint8_t*  data;
  const uint16_t* offsets;
  uint16_t        frames;
};

const Anim ANIMS[] = {
""")
    for sym, label in rows:
        out.append(f'  {{ "{label:<11}", {sym}_data, {sym}_offsets, {sym.upper()}_FRAMES }},\n')
    out.append("};\n\nconst uint8_t ANIM_COUNT = sizeof(ANIMS) / sizeof(ANIMS[0]);\n\n")
    out.append("// Index of each animation, in the order listed above\n")
    for i, (sym, _) in enumerate(rows):
        out.append(f'#define ANIM_{sym.upper():<12} {i}\n')
    open(path, "w").write("".join(out))


def register(path, sym, label):
    rows = read_registry(path)
    for i, (s, _) in enumerate(rows):
        if s == sym:
            rows[i] = (sym, label)
            write_registry(path, rows)
            return len(rows), "updated"
    rows.append((sym, label))
    write_registry(path, rows)
    return len(rows), "added"


# =============================================================== reporting
def budget(folder):
    tot, rows = 0, []
    for f in sorted(glob.glob(os.path.join(folder, "anim_*.h"))):
        txt = open(f).read()
        m = re.search(r"_data\[(\d+)\]", txt)
        n = re.search(r"_FRAMES (\d+)", txt)
        if not m:
            continue
        size = int(m.group(1))
        tot += size
        rows.append((os.path.basename(f), int(n.group(1)) if n else 0, size))

    print(f"{'file':<26}{'frames':>8}{'stored':>10}")
    for f, n, s in rows:
        print(f"{f:<26}{n:>8}{s/1024:>9.1f}K")
    print(f"{'TOTAL':<26}{sum(r[1] for r in rows):>8}{tot/1024:>9.1f}K")
    free = 1310 - tot / 1024 - 290
    print("\nThe default 4MB partition gives about 1310 KB for the whole program.")
    print(f"Frames use {tot/1024:.0f} KB and the sketch itself roughly 290 KB.")
    print(f"Approximately {free:.0f} KB free"
          + ("" if free > 100 else "   <-- tight, switch to the Huge APP partition"))


def slug(name):
    s = re.sub(r"[^0-9a-zA-Z]+", "", os.path.splitext(os.path.basename(name))[0].lower())
    if not s:
        s = "anim"
    if s[0].isdigit():
        s = "a" + s          # C identifiers cannot start with a digit
    return s


# =============================================================== convert
def convert(path, a, outdir, animh, sym=None, label=None):
    sym = sym or slug(path)
    label = (label or sym.capitalize())[:11]
    if not sym.isidentifier() or sym[0].isdigit():
        sys.exit(f"'{sym}' is not a usable C identifier")

    frames = load_frames(path)
    n_src = len(frames)
    frames = subsample(frames, a.max_frames)
    box = ((0, 0) + frames[0].size) if a.no_autocrop else content_box(frames)

    print(f"\n{os.path.basename(path)}")
    print(f"  {n_src} frames"
          + (f" -> {len(frames)} after subsampling" if len(frames) != n_src else "")
          + f", source {frames[0].size[0]}x{frames[0].size[1]}")
    print(f"  crop {box}, threshold {a.threshold}" + (", inverted" if a.invert else ""))

    if a.preview:
        p = write_preview(frames, box, a.threshold, not a.no_denoise, a.invert, sym, outdir)
        print(f"  preview written to {p}")
        print("  adjust --threshold, rerun, then drop --preview to encode")
        return None

    blob, offsets = encode(frames, box, a.threshold, not a.no_denoise, a.invert)

    if len(blob) > MAX_BLOB:
        print(f"  ERROR: {len(blob)} compressed bytes exceeds the {MAX_BLOB} byte limit")
        print(f"  of the uint16 offset table. Try  --max-frames "
              f"{int(len(frames) * MAX_BLOB / len(blob) * 0.9)}")
        return None

    if not roundtrip_ok(blob, offsets, len(frames)):
        print("  ERROR: round-trip decode failed, header not written")
        return None

    hp = write_header(outdir, sym, label, blob, offsets, len(frames))
    raw = len(frames) * FRAME_BYTES
    print("  round-trip OK")
    print(f"  {raw/1024:.0f} KB raw -> {len(blob)/1024:.1f} KB stored  ({raw/len(blob):.1f}x)")
    print(f"  wrote {hp}")

    if a.no_register:
        print(f'  add manually:  #include "anim_{sym}.h"')
        print(f'                 {{ "{label:<11}", {sym}_data, {sym}_offsets, '
              f'{sym.upper()}_FRAMES }},')
    else:
        count, what = register(animh, sym, label)
        print(f"  {what} in {os.path.basename(animh)}; {count} animations registered")
    return sym


def interactive(a, outdir, animh):
    cands = []
    for d in {os.path.abspath(a.folder or "."), outdir}:
        for e in IMAGE_EXT:
            cands += glob.glob(os.path.join(d, "*" + e))
    cands = sorted(set(c for c in cands if not os.path.basename(c).startswith("preview_")))
    if not cands:
        print("No GIFs found here. Put your .gif files next to this script, or pass a path:")
        print("    python3 gif2mochi.py path/to/clip.gif")
        return

    print("\nGIFs found:")
    for i, c in enumerate(cands):
        print(f"  {i:>2}  {os.path.basename(c)}")
    print("   a  convert all of them")
    choice = input("\nWhich one? (number, or 'a') ").strip().lower()

    if choice == "a":
        for c in cands:
            convert(c, a, outdir, animh)
        return
    if not choice.isdigit() or int(choice) >= len(cands):
        print("nothing selected")
        return

    path = cands[int(choice)]
    default_sym = slug(path)
    sym = input(f"C name [{default_sym}]: ").strip() or default_sym
    label = input(f"Display name [{sym.capitalize()}]: ").strip() or sym.capitalize()
    convert(path, a, outdir, animh, sym, label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gif", nargs="?", help="GIF file, or a folder of numbered stills")
    ap.add_argument("symbol", nargs="?", help="C identifier, e.g. sad")
    ap.add_argument("label", nargs="?", help="display name, e.g. Sad")
    ap.add_argument("--all", action="store_true", help="convert every GIF in the folder")
    ap.add_argument("--folder", help="where to look for GIFs (default: here)")
    ap.add_argument("--outdir", help="where to write headers (default: the sketch folder)")
    ap.add_argument("--threshold", type=int, default=110)
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--no-autocrop", action="store_true")
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--no-register", action="store_true", help="do not touch animations.h")
    ap.add_argument("--preview", action="store_true", help="write a PNG instead of encoding")
    ap.add_argument("--list", action="store_true", help="show registered animations")
    ap.add_argument("--remove", metavar="SYM", help="unregister and delete an animation")
    ap.add_argument("--budget", action="store_true", help="report flash usage")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    # if this script lives in tools/, the sketch folder is one level up
    outdir = a.outdir or (os.path.dirname(here) if os.path.basename(here) == "tools" else here)
    animh = os.path.join(outdir, "animations.h")

    if a.budget:
        return budget(outdir)

    if a.list:
        rows = read_registry(animh)
        if not rows:
            return print(f"nothing registered in {animh}")
        for i, (s, l) in enumerate(rows):
            print(f"  {i:>2}  {l:<12} anim_{s}.h")
        return

    if a.remove:
        rows = read_registry(animh)
        keep = [r for r in rows if r[0] != a.remove]
        if len(keep) == len(rows):
            return print(f"'{a.remove}' is not registered")
        write_registry(animh, keep)
        hp = os.path.join(outdir, f"anim_{a.remove}.h")
        if os.path.exists(hp):
            os.remove(hp)
            print(f"deleted {hp}")
        return print(f"removed '{a.remove}'; {len(keep)} animations remain")

    if a.all:
        folder = os.path.abspath(a.folder or ".")
        files = sorted(f for e in IMAGE_EXT for f in glob.glob(os.path.join(folder, "*" + e))
                       if not os.path.basename(f).startswith("preview_"))
        if not files:
            return print(f"no GIFs in {folder}")
        for f in files:
            convert(f, a, outdir, animh)
        return print(f"\nDone. {len(files)} files processed.")

    if not a.gif:
        return interactive(a, outdir, animh)

    convert(a.gif, a, outdir, animh, a.symbol, a.label)


if __name__ == "__main__":
    main()
