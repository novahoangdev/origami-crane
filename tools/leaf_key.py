"""Key the Codex leaf/petal paintings (pure magenta background) to straight-alpha PNGs.
  $(ls /Applications/Blender.app/Contents/Resources/*/python/bin/python3.13) -I tools/leaf_key.py
blender/textures/leaves_raw/*.png (magenta) → blender/textures/leaves_raw/keyed/*.png (RGBA, straight alpha, despilled)."""
import os, subprocess, sys
import numpy as np

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender", "textures", "leaves_raw")
os.makedirs(os.path.join(D, "keyed"), exist_ok=True)
for name in ("leaf_maple_red", "leaf_maple_green", "petal_sakura"):
    src = os.path.join(D, name + ".png")
    w, h = map(int, subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", src],
                                   capture_output=True, text=True).stdout.strip().split(","))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    c = np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(np.float64) / 255
    m = np.minimum(c[..., 0], c[..., 2]) - c[..., 1]  # magenta-ness: 1 on the background, ~0 on leaves and petals
    a = 1 - np.clip((m - 0.25) / (0.75 - 0.25), 0, 1)
    a = a * a * (3 - 2 * a)
    mag = np.array([1.0, 0.0, 1.0])
    rgb = np.where(a[..., None] > 0.02, (c - (1 - a[..., None]) * mag) / np.maximum(a[..., None], 0.02), 0)
    out = np.dstack([np.clip(rgb, 0, 1), a])
    buf = (out * 255 + 0.5).astype(np.uint8).tobytes()
    dst = os.path.join(D, "keyed", name + ".png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-i", "-", dst], input=buf, check=True)
    print("KEYED", dst, f"coverage {a.mean():.2f}")
