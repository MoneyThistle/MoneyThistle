"""Draw MoneyThistle's app icons (the teal dot on navy, as in the header) as PNG files
for phones' home screens. Standard library only. Run: python tools/make_icons.py"""

import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "moneyapp", "static")
NAVY, NAVY2 = (0x12, 0x32, 0x5F), (0x1C, 0x4B, 0x8A)
TEAL_LIGHT, TEAL, TEAL_DARK = (0x7F, 0xD6, 0xC2), (0x1F, 0x8A, 0x8A), (0x0F, 0x5B, 0x5B)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def pixel(x, y, n):
    u, v = (x + 0.5) / n, (y + 0.5) / n
    bg = mix(NAVY2, NAVY, v)                       # the header's gradient
    cx = cy = 0.5
    r = 0.30                                        # the dot (inside the maskable safe zone)
    d = math.hypot(u - cx, v - cy)
    if d > r + 1.5 / n:
        return bg
    # Radial shading from a highlight up and to the left, like the header mark.
    hd = math.hypot(u - (cx - 0.1), v - (cy - 0.1)) / (r * 1.6)
    col = mix(TEAL_LIGHT, TEAL, hd / 0.6) if hd < 0.6 else mix(TEAL, TEAL_DARK, (hd - 0.6) / 0.6)
    ring = r - 0.025
    if d > ring:                                    # soft light rim
        col = mix(col, (255, 255, 255), 0.35)
    edge = (r + 1.5 / n - d) / (3.0 / n)            # anti-aliased edge
    return mix(bg, col, edge) if edge < 1 else col


def png(n, path):
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y, n)) for x in range(n)) for y in range(n))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


if __name__ == "__main__":
    for size in (180, 192, 512):
        png(size, os.path.join(OUT, f"icon-{size}.png"))
        print("icon", size)
