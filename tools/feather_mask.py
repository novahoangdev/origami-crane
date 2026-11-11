"""Feather the near edge of the sun patch in the lattice mask (vertical blur blended in below y0, no seam).
Reads a raw 1600x2080 gray8 frame on stdin (the horizontally blurred mask), writes raw gray8 to stdout. See README_masks.txt."""
import sys
import numpy as np

W, H = 1600, 2080
m = np.frombuffer(sys.stdin.buffer.read(), np.uint8).reshape(H, W).astype(np.float64)
sig = 16.0
k = np.exp(-0.5 * (np.arange(-48, 49) / sig) ** 2)
k /= k.sum()
pad = np.pad(m, ((48, 48), (0, 0)), mode="edge")
vb = np.zeros_like(m)
for i, w in enumerate(k):
    vb += w * pad[i : i + H]
y = np.arange(H)[:, None]
t = np.clip((y - 1180.0) / 140.0, 0, 1)
a = t * t * (3 - 2 * t)
out = m * (1 - a) + vb * a
sys.stdout.buffer.write(np.clip(out + 0.5, 0, 255).astype(np.uint8).tobytes())
