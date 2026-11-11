"""Run with Blender's python: $(ls /Applications/Blender.app/Contents/Resources/*/python/bin/python3.13) tools/fx_atlas.py
Particle sprite atlas for the app (app/assets/fx/atlas.png): 8 cells of 128 px in one row.
0 sparkle (core + 4 rays)  1 soft dot  2 star glint (6 long rays)  3–6 cherry petal tumbling (4 squash frames)  7 flash."""
import math
import numpy as np
import subprocess

C = 128
N = 8
img = np.zeros((C, C * N, 4), np.float32)
yy, xx = np.mgrid[0:C, 0:C].astype(np.float32)
cx = cy = (C - 1) / 2
dx, dy = (xx - cx) / (C / 2), (yy - cy) / (C / 2)
r = np.hypot(dx, dy)
ang = np.arctan2(dy, dx)


def put(i, rgb, a):
    a = np.clip(a, 0, 1)
    for k in range(3):
        img[:, i * C:(i + 1) * C, k] = rgb[k]  # straight alpha (PNG); Skia premultiplies on decode
    img[:, i * C:(i + 1) * C, 3] = a


def rays(n, width, length, rot=0.0):
    out = np.zeros_like(r)
    for k in range(n):
        a = rot + k * math.pi * 2 / n
        along = dx * math.cos(a) + dy * math.sin(a)
        across = -dx * math.sin(a) + dy * math.cos(a)
        m = (along > 0) * np.exp(-(across / (width * (1 - np.clip(along / length, 0, 1)) + 1e-3)) ** 2) * np.clip(1 - along / length, 0, 1) ** 1.5
        out = np.maximum(out, m)
    return out


# 0 sparkle: hot core, soft halo, 4 thin rays
put(0, (1, 1, 1), np.exp(-(r / 0.10) ** 2) + 0.35 * np.exp(-(r / 0.35) ** 2) + 0.9 * rays(4, 0.05, 0.95, math.pi / 4))
# 1 soft dot (bokeh-ish disc with a faint brighter rim)
put(1, (1, 1, 1), np.clip(1 - (r / 0.9) ** 8, 0, 1) * (0.55 + 0.45 * np.clip((r - 0.6) / 0.3, 0, 1)) * 0.9 * np.clip((0.95 - r) / 0.08, 0, 1))
# 2 star glint: 6 long rays + core
put(2, (1, 1, 1), np.exp(-(r / 0.07) ** 2) + 0.25 * np.exp(-(r / 0.25) ** 2) + rays(6, 0.035, 1.0, 0.2))
# 3–6 petal frames: a cherry petal (teardrop with a notch) seen at different tilt angles
for f, sq in enumerate([1.0, 0.72, 0.42, 0.16]):
    px = dx / (0.62 * sq + 1e-3)
    py = dy / 0.9
    # teardrop: wider at the top (notched end), pointed at the bottom
    wdt = 0.72 + 0.3 * np.clip(-py, -1, 1)
    body = np.clip(1 - (px / np.maximum(wdt, 0.05)) ** 2 - py ** 2, 0, 1)
    notch = np.exp(-((px / 0.18) ** 2 + ((py + 0.95) / 0.22) ** 2))
    a = np.clip(body * 6, 0, 1) * (1 - notch)
    shade = 0.75 + 0.25 * (1 - np.clip(np.hypot(px, py + 0.2), 0, 1))
    base = np.stack([np.ones_like(r), 0.78 + 0.1 * (py + 1) / 2, 0.84 + 0.08 * (py + 1) / 2])  # pale pink, whiter toward the tip
    i = 3 + f
    for k in range(3):
        img[:, i * C:(i + 1) * C, k] = base[k] * shade
    img[:, i * C:(i + 1) * C, 3] = a
# 7 flash: big soft radial
put(7, (1, 1, 1), np.exp(-(r / 0.45) ** 2) * 0.9 + 0.25 * np.exp(-(r / 0.12) ** 2))

out = (np.clip(img, 0, 1) * 255).astype(np.uint8)
# numpy-only (runs with Blender's bundled python): raw RGBA → PNG through ffmpeg
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{C * N}x{C}", "-i", "-",
                "app/assets/fx/atlas.png"], input=out.tobytes(), check=True)
print("atlas", out.shape)
