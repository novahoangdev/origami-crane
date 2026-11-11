"""Placeholder fold model in the crane.json/crane.bin format (used until blender/scripts/fold_crane.py delivers).
A 2x2 sheet, grid split along the u=v diagonal, one diagonal valley fold (hinge 180 deg, axis lifted by one layer)."""
import json, math, struct, sys
N = 10
T = 0.004
verts, uv = [], []
for j in range(N + 1):
    for i in range(N + 1):
        u, v = i / N, j / N
        uv += [u, v]
        verts.append((u * 2 - 1, v * 2 - 1, 0.0005))
tris = []
idx = lambda i, j: j * (N + 1) + i
for j in range(N):
    for i in range(N):
        a, b, c, d = idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)
        # cells split along their u=v diagonal (a-c); CCW seen from -z (front) = CW seen from +z
        tris += [a, c, b, a, d, c]
ease = lambda x: x * x * (3 - 2 * x)
K = 24
frames = []
ax = (1 / math.sqrt(2), 1 / math.sqrt(2), 0.0)
for k in range(K + 1):
    th = math.pi * ease(k / K)
    f = []
    for (x, y, z), (u, v) in zip(verts, zip(uv[0::2], uv[1::2])):
        if v > u + 1e-9:
            # rotate about the line through origin along ax, lifted to z = T/2
            d = (x * ax[1] - y * ax[0])  # signed distance from the line in the plane
            px, py = x - d * ax[1], y + d * ax[0]
            zz = z - T / 2
            nd = d * math.cos(th) + zz * math.sin(th)
            nz = -d * math.sin(th) + zz * math.cos(th)
            x2, y2 = px + nd * ax[1], py - nd * ax[0]
            f.append((x2, y2, nz + T / 2))
        else:
            f.append((x, y, z))
    frames.append(f)
out = sys.argv[1]
with open(out + ".bin", "wb") as fh:
    for f in frames:
        for p in f:
            fh.write(struct.pack("<3f", *p))
json.dump({"version": 0, "vertexCount": len(verts), "triCount": len(tris) // 3, "keyframes": K + 1, "layerThickness": T,
           "uv": uv, "tris": tris,
           "steps": [{"name": "Diagonal fold", "from": 0, "to": K, "hint": {"a": [-0.9, 0.9, 0], "b": [0.9, -0.9, 0]}}],
           "wings": None, "head": None, "tail": None}, open(out + ".json", "w"))
print("placeholder", len(verts), len(tris) // 3, K + 1)
