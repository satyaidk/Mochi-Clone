#!/usr/bin/env python3
"""
gif2mochi.py - convert a GIF into a Mochi Desk animation header.

This is the exact encoder used to produce the 18 headers in this sketch.
Output format: each 128x64 frame is packed to 1 bit per pixel (1024 bytes,
row-major, MSB first), XORed against the previous frame, then PackBits
compressed. The decoder in MochiDesk.ino reverses it.

Usage:
    python3 gif2mochi.py happy.gif happy Happy
    python3 gif2mochi.py sad.gif sad Sad --threshold 120 --no-autocrop

Then add to animations.h:
    #include "anim_sad.h"
    ... and one row in the ANIMS[] table:
    { "Sad        ", sad_data, sad_offsets, SAD_FRAMES },

Requires: pip install pillow
"""

import argparse
import os
import sys

try:
    from PIL import Image, ImageFilter
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

W, H = 128, 64
FRAME_BYTES = W * H // 8          # 1024


# ---------------------------------------------------------------- load frames
def load_frames(path):
    im = Image.open(path)
    out = []
    i = 0
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


# ---------------------------------------------------------------- auto crop
def content_box(frames, thr=150):
    """Union of the bright area across the animation, padded and forced to 2:1."""
    box = None
    for g in frames[::3]:
        b = g.filter(ImageFilter.MedianFilter(5)).point(
            lambda p: 255 if p > thr else 0).getbbox()
        if b is None:
            continue
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                     max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        box = (0, 0, frames[0].size[0], frames[0].size[1])

    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    w, h = (box[2] - box[0]) * 1.10, (box[3] - box[1]) * 1.18
    if w / h < 2.0:
        w = h * 2.0
    else:
        h = w / 2.0
    return (int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2))


# ---------------------------------------------------------------- 1bpp packing
def to_bits(gray, box, thr, denoise=True):
    if denoise:
        gray = gray.filter(ImageFilter.MedianFilter(3))
    im = gray.crop(box).resize((W, H), Image.LANCZOS)
    return im.point(lambda p: 255 if p > thr else 0).convert("1")


def pack(img):
    """Row-major, MSB first - the format Adafruit_GFX drawBitmap expects."""
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


# ---------------------------------------------------------------- PackBits
def packbits(data):
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        run = 1
        while i + run < n and data[i + run] == data[i] and run < 128:
            run += 1
        if run >= 2:                       # repeat run
            out.append(256 - (run - 1))    # 129..255  ->  int8 -1..-127
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
    """Reference decoder - mirrors decodeFrame() in the sketch."""
    out = bytearray()
    i = 0
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


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gif")
    ap.add_argument("symbol", help="C identifier, e.g. sad  (letters/digits only)")
    ap.add_argument("label", nargs="?", help="display name, e.g. Sad")
    ap.add_argument("--threshold", type=int, default=110,
                    help="black/white cutoff 0-255 (default 110)")
    ap.add_argument("--no-autocrop", action="store_true")
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--outdir", default=".")
    a = ap.parse_args()

    sym = a.symbol
    if not sym.isidentifier() or sym[0].isdigit():
        sys.exit("symbol must be a valid C identifier and must not start with a digit")
    label = (a.label or sym.capitalize())[:11]

    frames = load_frames(a.gif)
    box = ((0, 0) + frames[0].size) if a.no_autocrop else content_box(frames)
    print(f"{len(frames)} frames, source {frames[0].size[0]}x{frames[0].size[1]}, crop {box}")

    prev = bytes(FRAME_BYTES)
    blob = bytearray()
    offsets = []
    for g in frames:
        cur = pack(to_bits(g, box, a.threshold, not a.no_denoise))
        offsets.append(len(blob))
        blob += packbits(bytes(x ^ y for x, y in zip(cur, prev)))
        prev = cur
    offsets.append(len(blob))

    if len(blob) > 65535:
        sys.exit("compressed data exceeds 65535 bytes; the uint16 offset table "
                 "cannot address it. Use fewer frames or widen the offsets to uint32.")

    # round-trip check
    acc = bytearray(FRAME_BYTES)
    for i in range(len(frames)):
        d = unpackbits(bytes(blob[offsets[i]:offsets[i + 1]]), FRAME_BYTES)
        acc = bytearray(x ^ y for x, y in zip(acc, d))
    print("round-trip decode OK")

    def hexblob(data, per=16):
        return ",\n".join("  " + ", ".join(f"0x{b:02x}" for b in data[i:i + per])
                          for i in range(0, len(data), per))

    path = os.path.join(a.outdir, f"anim_{sym}.h")
    with open(path, "w") as fh:
        fh.write(f"// {label} - {len(frames)} frames, {W}x{H}, XOR-delta + PackBits\n")
        fh.write("#pragma once\n#include <Arduino.h>\n\n")
        fh.write(f"#define {sym.upper()}_FRAMES {len(frames)}\n\n")
        fh.write(f"const uint16_t {sym}_offsets[{len(offsets)}] PROGMEM = {{\n")
        fh.write(",\n".join("  " + ", ".join(str(o) for o in offsets[i:i + 16])
                            for i in range(0, len(offsets), 16)))
        fh.write("\n};\n\n")
        fh.write(f"const uint8_t {sym}_data[{len(blob)}] PROGMEM = {{\n{hexblob(blob)}\n}};\n")

    raw = len(frames) * FRAME_BYTES
    print(f"wrote {path}")
    print(f"raw {raw//1024} KB -> compressed {len(blob)//1024} KB  (x{raw/len(blob):.1f})")
    print(f'\nAdd to animations.h:\n  #include "anim_{sym}.h"')
    print(f'  {{ "{label:<11}", {sym}_data, {sym}_offsets, {sym.upper()}_FRAMES }},')


if __name__ == "__main__":
    main()
