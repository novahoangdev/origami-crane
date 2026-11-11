# Anime-style multiplane background + table light passes (no Cycles: Codex paintings + numpy projection).
#
# Inputs (Codex paintings, blender/textures/anime_raw/*.png; cut-out layers were painted on flat #FF00FF):
#   sky, hills, garden, house, table, leaf, bird
# Outputs (app/assets/scene/):
#   anime/sky.jpg, anime/hills.png, anime/garden.png, anime/house.png   multiplane layers (vertical planes facing -y)
#   table_base.jpg   table without direct sun (cool lavender-teal ambient + warm bounce)            sRGB-encoded linear
#   table_sun.jpg    direct-sun contribution as if nothing occluded the sun (incl. a faint sheen)    sRGB-encoded linear
#   mask_lattice.jpg sun visibility through the house opening (pillars, lintel, side shoji, furin)  linear 0..1
#   mask_leaves.jpg  sun visibility from the garden foliage (hard-edged elongated dapples)          linear 0..1
#   table.jpg        = srgb( lin(table_base) + lin(table_sun) * mask_lattice * mask_leaves )
#   sunmask.jpg      = mask_lattice * mask_leaves
#   backdrop.jpg     front-ortho composite of the layers over x in [-9, 9], z in [-0.5, 13] (fallback)
#   bg.jpg           1320x2868 perspective composite from the app camera (reference)
#   layout.json      camera, sun, ambient, extents, "layers", "passes"
#   app/assets/fx/leaf.png, bird.png
# Preview: render/preview/anime.jpg (bg | tilted view | table | masks)
#
# Run: /Applications/Blender.app/Contents/Resources/<ver>/python/bin/python3.13 -I blender/scripts/anime_scene.py
import json, math, os
import numpy as np
import OpenImageIO as oiio

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RAW = os.path.join(ROOT, "blender", "textures", "anime_raw")
OUT = os.path.join(ROOT, "app", "assets", "scene")
LAY = os.path.join(OUT, "anime")
FX = os.path.join(ROOT, "app", "assets", "fx")
PREV = os.path.join(ROOT, "render", "preview")
for d in (OUT, LAY, FX, PREV):
    os.makedirs(d, exist_ok=True)
rng = np.random.default_rng(11)

# ── world ──
CAM_POS, CAM_TARGET, FOV_Y = np.array([0, -6.0, 2.9]), np.array([0, 0.3, 0.0]), 42.0
TABLE = {"x": [-5.0, 5.0], "y": [-6.0, 7.0]}
BACKDROP = {"y": 7.0, "x": [-9.0, 9.0], "z": [-0.5, 13.0]}
TW, TH = 1600, 2080
# sun: light travels toward -y, slightly +x, and down (elevation ~21.7 deg), entering through the house opening
SUN_TRAVEL = np.array([0.10, -1.0, -0.40])
SUN_DIR = -SUN_TRAVEL / np.linalg.norm(SUN_TRAVEL)
SUN_COLOR = np.array([1.0, 0.80, 0.53])          # normalised (max 1), linear
SUN_SCALE = 2.25                                   # white Lambertian facing the sun = SUN_COLOR * SUN_SCALE (linear)
AMBIENT = np.array([0.19, 0.22, 0.47])          # cool lavender-teal sky light, linear, same units as SUN_COLOR*SUN_SCALE
BOUNCE = np.array([0.30, 0.17, 0.07])              # warm bounce from the sunlit floor (peak, linear)

# house opening, measured from the painting (alpha hole bbox in px) and placed at x in [-2.8, 2.8], bottom z = 0.3
HOLE_PX = (561, 991, 675, 931)
HOLE_X, HOLE_Z0 = (-2.8, 2.8), 0.3


# ── io helpers ──
def load(name):
    b = oiio.ImageBuf(os.path.join(RAW, name))
    return np.asarray(b.get_pixels(oiio.FLOAT))[..., :3].copy()


def resize(a, w, h):
    c = a.shape[2]
    b = oiio.ImageBuf(oiio.ImageSpec(a.shape[1], a.shape[0], c, oiio.FLOAT))
    b.set_pixels(oiio.ROI(0, a.shape[1], 0, a.shape[0], 0, 1, 0, c), np.ascontiguousarray(a, np.float32))
    r = oiio.ImageBufAlgo.resize(b, roi=oiio.ROI(0, w, 0, h, 0, 1, 0, c))
    return np.asarray(r.get_pixels(oiio.FLOAT)).copy()


def save(a, path, q=88):
    a = np.atleast_3d(a)
    h, w, c = a.shape
    spec = oiio.ImageSpec(w, h, c, "uint8")
    if path.endswith(".jpg"):
        spec.attribute("Compression", f"jpeg:{q}")
    else:
        spec.attribute("png:compressionLevel", 9)
    o = oiio.ImageOutput.create(path)
    o.open(path, spec)
    o.write_image(np.ascontiguousarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)))
    o.close()
    print("SAVE", os.path.relpath(path, ROOT), w, h, f"{os.path.getsize(path) / 1024:.0f} KB")


def gblur(a, s):
    if s <= 0:
        return a
    r = max(1, int(s * 3))
    x = np.arange(-r, r + 1)
    k = np.exp(-x * x / (2 * s * s))
    k /= k.sum()
    for ax in (0, 1):
        pad = [(0, 0)] * a.ndim
        pad[ax] = (r, r)
        p = np.pad(a, pad, mode="edge")
        acc = np.zeros_like(a)
        for i, kv in enumerate(k):
            sl = [slice(None)] * a.ndim
            sl[ax] = slice(i, i + a.shape[ax])
            acc += kv * p[tuple(sl)]
        a = acc
    return a


lin = lambda a: np.where(a <= 0.04045, a / 12.92, ((np.clip(a, 0, None) + 0.055) / 1.055) ** 2.4)
enc = lambda a: np.where(a <= 0.0031308, a * 12.92, 1.055 * np.clip(a, 0, None) ** (1 / 2.4) - 0.055)
luma = lambda a: a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
smooth = lambda e0, e1, x: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0, 1))


def key_magenta(a, soft=(0.22, 0.55), erode=0.6):
    """Alpha from a flat #FF00FF background, with despill on the edge band. Returns RGBA (straight alpha)."""
    k = np.minimum(a[..., 0], a[..., 2]) - a[..., 1]
    al = 1 - smooth(soft[0], soft[1], k)
    al = np.clip((gblur(al, 0.8) - 0.5 * erode) / (1 - 0.5 * erode), 0, 1)     # shave the magenta fringe
    edge = (al < 0.999) | (gblur((al < 0.5).astype(np.float32), 2.0) > 0.01)
    rgb = a.copy()
    spill = np.clip(np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1], 0, None) * edge
    rgb[..., 0] -= spill * 0.9
    rgb[..., 2] -= spill * 0.9
    # bleed colour from the opaque core into the transparent area (clean bilinear filtering in the app)
    w = gblur(al[..., None] ** 2, 4.0)
    fill = gblur(rgb * al[..., None] ** 2, 4.0) / np.maximum(w, 1e-4)
    rgb = np.where(al[..., None] > 0.6, rgb, fill)
    return np.concatenate([np.clip(rgb, 0, 1), al[..., None]], 2)


def sample(img, u, v):
    """Bilinear sample img (h, w, c) at normalised u (left->right), v (top->bottom); clamp to edge."""
    h, w = img.shape[:2]
    x = np.clip(u * w - 0.5, 0, w - 1.001)
    y = np.clip(v * h - 0.5, 0, h - 1.001)
    x0, y0 = x.astype(np.int32), y.astype(np.int32)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


# ── 1. layers ──
layers = []


def add_layer(name, file, y, x, z, img, drift=0.0):
    layers.append({"name": name, "file": f"anime/{file}", "y": y, "x": [round(v, 3) for v in x],
                   "z": [round(v, 3) for v in z], "drift": drift, "img": img})


# sky: horizontally tileable (cross-fade the left band with the wrapped right edge, then drop it)
sky = load("sky.png")
B = 256
t = np.linspace(0, 1, B)[None, :, None]
sky = np.concatenate([sky[:, -B:] * (1 - t) + sky[:, :B] * t, sky[:, B:-B]], 1)   # width W - B, seamless
sky = resize(sky, 2048, int(round(2048 * sky.shape[0] / sky.shape[1])))
save(sky, os.path.join(LAY, "sky.jpg"), 88)
skyw = 60.0
skyh = skyw * sky.shape[0] / sky.shape[1]
z1 = 2.0 + 0.86 * skyh                            # the sun glow (86 % down the painting) sits just below the hill ridge
add_layer("sky", "sky.jpg", 60.0, (-skyw / 2, skyw / 2), (z1 - skyh, z1), np.concatenate([sky, np.ones_like(sky[..., :1])], 2), 3.0)

hills = key_magenta(load("hills.png"))
save(hills, os.path.join(LAY, "hills.png"))
add_layer("hills", "hills.png", 35.0, (-12.0, 12.0), (-3.9, 12.1), hills)

garden = key_magenta(load("garden.png"))
save(garden, os.path.join(LAY, "garden.png"))
add_layer("garden", "garden.png", 14.0, (-9.0, 9.0), (-5.0, 7.0), garden)

house = key_magenta(load("house.png"), soft=(0.3, 0.6), erode=0.3)
save(house, os.path.join(LAY, "house.png"))
hx0, hx1, hy0, hy1 = HOLE_PX
ppu = (hx1 - hx0 + 1) / (HOLE_X[1] - HOLE_X[0])   # px per world unit
H_W, H_H = house.shape[1], house.shape[0]
hxa = HOLE_X[0] - hx0 / ppu
hza = HOLE_Z0 - (H_H - 1 - hy1) / ppu
add_layer("house", "house.png", 7.0, (hxa, hxa + H_W / ppu), (hza, hza + H_H / ppu), house)
print("HOUSE extents", layers[-1]["x"], layers[-1]["z"], "opening top z", round(HOLE_Z0 + (hy1 - hy0 + 1) / ppu, 2))


def layer_rgba_at(L, x, z):
    u = (x - L["x"][0]) / (L["x"][1] - L["x"][0])
    v = (L["z"][1] - z) / (L["z"][1] - L["z"][0])
    out = sample(L["img"], u, v)
    if L["drift"] == 0:   # outside a non-tiling layer: transparent (sky tiles, it is never outside)
        inside = ((u >= 0) & (u <= 1) & (v >= 0) & (v <= 1))[..., None]
        out = out * inside
    return out


# ── 2. table passes ──
ii = (np.arange(TW) + 0.5) / TW
jj = (np.arange(TH) + 0.5) / TH
X = TABLE["x"][0] + ii[None, :] * 10.0 + 0 * jj[:, None]
Y = TABLE["y"][1] - jj[:, None] * 13.0 + 0 * ii[None, :]
ppu_t = TW / 10.0

# albedo: Codex wood, centre crop to the table aspect, a touch of extra grain contrast
if os.path.exists(os.path.join(RAW, "floor.png")):
    # painted engawa planks: cut between the outermost plank seams, tile 3x across (12 planks over 10 units),
    # stretch along y (the low camera foreshortens it back)
    wood = load("floor.png")
    colm = luma(wood).mean(0)
    w_ = wood.shape[1]
    sa = int(np.argmin(colm[int(w_ * 0.08):int(w_ * 0.3)])) + int(w_ * 0.08)
    sb = int(np.argmin(colm[int(w_ * 0.7):int(w_ * 0.92)])) + int(w_ * 0.7)
    wood = np.concatenate([wood[:, sa:sb]] * 3, 1)
    wood = resize(wood, TW, TH)
else:
    wood = load("table.png")
    ch = int(round(wood.shape[1] * TH / TW))
    o0 = (wood.shape[0] - ch) // 2
    wood = resize(wood[o0:o0 + ch], TW, TH)
wl = lin(wood)
grain = luma(wl)
wl = np.clip(wl * (1 + 0.3 * (grain - grain.mean())[..., None] / max(1e-3, grain.mean())), 0, 1)
# a bit less saturated / orange than the painting, so the cool ambient turns the shade lavender
A = (grain[..., None] * 0.22 + wl * 0.78) * np.array([1.0, 0.95, 0.9])
A = A * (0.50 / max(1e-3, float(luma(A).mean())))   # mean albedo ~0.5 linear

# lattice: shoot each table point toward the sun to the house plane, visibility = 1 - house alpha
hl = layers[[L["name"] for L in layers].index("house")]
d = 7.0 - Y
Xw = X + SUN_TRAVEL[0] / SUN_TRAVEL[1] * d        # x where the ray toward the sun crosses y = 7
Zw = SUN_TRAVEL[2] / SUN_TRAVEL[1] * d            # z there (table z = 0)
ha = layer_rgba_at(hl, Xw, Zw)[..., 3]
lat = 1 - ha
lat = np.where((Zw >= hl["z"][0]) & (Zw <= hl["z"][1]), lat, 0.0)
# below the opening's bottom edge (painted threshold / veranda) the light still passes: the floor reaches the sill
in_x = (Xw > HOLE_X[0] + 0.02) & (Xw < HOLE_X[1] - 0.02)
lat = np.where(in_x & (Zw < HOLE_Z0 + 0.06), 1.0, lat)
lat = gblur(lat.astype(np.float32), 2.2)          # crisp, a hint of penumbra

# leaves: hard-edged clumps of overlapping ellipses (elongated along y: low sun), a few light holes inside
def blobs(n_clumps, centres, spread, rmin, rmax, per):
    m = np.zeros((TH, TW), np.float32)
    for cx, cy in centres[:n_clumps]:
        for _ in range(per):
            ex, ey = cx + rng.normal(0, spread), cy + rng.normal(0, spread * 2.0)
            rx = rng.uniform(rmin, rmax) * (0.4 + 0.6 * smooth(-3.2, 0.5, cy))   # smaller toward the near edge
            ry = rx * rng.uniform(1.8, 2.6)
            th = rng.uniform(-0.35, 0.35)
            # bbox in px
            R = ry * 1.1
            i0, i1 = int((ex - R + 5) * ppu_t), int((ex + R + 5) * ppu_t) + 1
            j0, j1 = int((7 - ey - R) * ppu_t), int((7 - ey + R) * ppu_t) + 1
            i0, j0 = max(0, i0), max(0, j0)
            i1, j1 = min(TW, i1), min(TH, j1)
            if i0 >= i1 or j0 >= j1:
                continue
            dx, dy = X[j0:j1, i0:i1] - ex, Y[j0:j1, i0:i1] - ey
            u = (dx * math.cos(th) + dy * math.sin(th)) / rx
            v = (-dx * math.sin(th) + dy * math.cos(th)) / ry
            # leaf-ish lobes: a wobbly radius
            ang = np.arctan2(v, u)
            rr = 1 + 0.09 * np.sin(5 * ang + rng.uniform(0, 6.28)) + 0.05 * np.sin(3 * ang + rng.uniform(0, 6.28))
            m[j0:j1, i0:i1] = np.maximum(m[j0:j1, i0:i1], (u * u + v * v < rr * rr).astype(np.float32))
    return m


clumps = [(-3.4, 1.0), (-2.7, -1.6), (2.9, 2.6), (3.6, -0.6), (-2.2, 4.9), (1.9, 5.6), (0.6, -3.2), (-0.6, 6.4),
          (2.5, -2.6), (-3.6, 3.4)]
shadow = blobs(len(clumps), clumps, 0.45, 0.09, 0.26, 19)
# sparse single dapples drifting across the patch (keep the paper area x, y in [-1.2, 1.2] mostly clear)
singles = []
while len(singles) < 22:
    p = (rng.uniform(-3.0, 3.6), rng.uniform(-2.4, 6.4))
    if abs(p[0]) < 1.45 and abs(p[1]) < 1.45:
        continue
    singles.append(p)
shadow = np.maximum(shadow, blobs(len(singles), singles, 0.08, 0.06, 0.15, 3))
holes = blobs(len(clumps), clumps, 0.5, 0.03, 0.08, 14)
shadow = shadow * (1 - holes)
# softness grows with the distance to the foliage (near edge = farthest from the garden): crisp far, soft near
s_hard, s_soft = gblur(shadow, 2.6), gblur(shadow, 9.0)
wsoft = smooth(0.5, -3.5, Y)
leaves = 1 - (s_hard * (1 - wsoft) + s_soft * wsoft)

vis = lat * leaves
# sun pass: albedo * sun * cos, + a faint broad sheen around the point where the camera sees the sun's reflection
Lz = float(SUN_DIR[2])
hd = CAM_POS[2] / math.tan(math.asin(Lz))
hdir = -SUN_TRAVEL[:2] / np.linalg.norm(SUN_TRAVEL[:2])
rp = CAM_POS[:2] + hdir * hd
sheen = np.exp(-(((X - rp[0]) / 1.3) ** 2 + ((Y - rp[1]) / 2.6) ** 2))
sheen = sheen * (0.75 + 0.5 * np.clip(grain / grain.mean() - 0.5, 0, 1))
sun = A * (SUN_COLOR * SUN_SCALE * Lz) + (0.16 * sheen)[..., None] * SUN_COLOR
# base: cool ambient, slightly darker toward the edges and under the wall, + warm bounce around the lit patch
glow = gblur(vis[::4, ::4], 40.0)
glow = resize(glow[..., None], TW, TH)[..., 0]
glow = glow / max(1e-3, glow.max())
vign = 1 - 0.25 * smooth(2.0, 5.5, np.hypot(X * 0.9, (Y - 1.5) * 0.55))
amb = AMBIENT * (0.85 + 0.15 * smooth(-6, 2, Y))[..., None] * vign[..., None]
base = A * (amb + BOUNCE * glow[..., None] ** 1.5)
peak = float(np.percentile(base + sun * vis[..., None], 99.9))
print("TABLE peak linear", round(peak, 3), "sun max", round(float(sun.max()), 3))
sun = np.clip(sun, 0, 1)
base = np.clip(base, 0, 1)
tab = np.clip(base + sun * vis[..., None], 0, 1)

save(enc(base), os.path.join(OUT, "table_base.jpg"), 88)
save(enc(sun), os.path.join(OUT, "table_sun.jpg"), 88)
save(np.repeat(lat[..., None], 3, 2), os.path.join(OUT, "mask_lattice.jpg"), 90)
save(np.repeat(leaves[..., None], 3, 2), os.path.join(OUT, "mask_leaves.jpg"), 90)
save(np.repeat(vis[..., None], 3, 2), os.path.join(OUT, "sunmask.jpg"), 90)
tab_s = enc(tab)
save(tab_s, os.path.join(OUT, "table.jpg"), 90)
TAB_IMG = tab_s

# ── 3. composites: backdrop (front ortho) and bg (app camera) ──
def over(dst, src):
    a = src[..., 3:4]
    return dst * (1 - a) + src[..., :3] * a


BW, BH = 2048, 1536
bx = BACKDROP["x"][0] + (np.arange(BW) + 0.5) / BW * 18.0
bz = BACKDROP["z"][1] - (np.arange(BH) + 0.5) / BH * 13.5
BX, BZ = np.meshgrid(bx, bz)
bd = np.zeros((BH, BW, 3), np.float32)
for L in layers:                                    # back to front (sky first)
    bd = over(bd, layer_rgba_at(L, BX, BZ))
save(bd, os.path.join(OUT, "backdrop.jpg"), 88)


def camera_view(pos, target, w, h, fov=FOV_Y):
    fwd = target - pos
    fwd = fwd / np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    th = math.tan(math.radians(fov / 2))
    sx = ((np.arange(w) + 0.5) / w * 2 - 1) * th * w / h
    sy = (1 - (np.arange(h) + 0.5) / h * 2) * th
    SX, SY = np.meshgrid(sx, sy)
    D = fwd[None, None] + SX[..., None] * right[None, None] + SY[..., None] * up[None, None]
    img = np.zeros((h, w, 3), np.float32)
    for L in layers:
        t = (L["y"] - pos[1]) / np.where(np.abs(D[..., 1]) < 1e-6, 1e-6, D[..., 1])
        x, z = pos[0] + D[..., 0] * t, pos[2] + D[..., 2] * t
        img = over(img, layer_rgba_at(L, x, z) * (t > 0)[..., None])
    # the table (z = 0, in front of the house plane) on top
    t = -pos[2] / np.where(D[..., 2] < -1e-6, D[..., 2], -1e-6)
    x, y = pos[0] + D[..., 0] * t, pos[1] + D[..., 1] * t
    on = (D[..., 2] < 0) & (y < 7.0) & (x > -5) & (x < 5) & (y > -6)
    tv = sample(TAB_IMG, (x + 5) / 10, (7 - y) / 13)
    return np.where(on[..., None], tv, img)


bg = camera_view(CAM_POS, CAM_TARGET, 1320, 2868)
save(bg, os.path.join(OUT, "bg.jpg"), 88)
# tilted-up preview (camera follows the crane): dolly position, pitch up ~25 deg from the typical view
# flight views: camera risen to z 3.5, moved to y 2.5, looking through the opening; and a mid-flight tilt
p2 = np.array([0, 2.5, 3.5])
tilt = camera_view(p2, p2 + np.array([0, math.cos(math.radians(-8)), math.sin(math.radians(-8))]), 440, 956)
p3 = np.array([0, -2.0, 3.2])
tilt2 = camera_view(p3, p3 + np.array([0, math.cos(math.radians(-4)), math.sin(math.radians(-4))]), 440, 956)

# ── 4. fx ──
lf = key_magenta(load("leaf.png"))
ys, xs = np.nonzero(lf[..., 3] > 0.05)
c0, c1 = max(0, min(ys.min(), xs.min()) - 24), min(lf.shape[0], max(ys.max(), xs.max()) + 24)
lf = lf[c0:c1, c0:c1]
save(resize(lf, 256, 256), os.path.join(FX, "leaf.png"))
bd_ = key_magenta(load("bird.png"), soft=(0.25, 0.5), erode=0.2)
al = bd_[..., 3] > 0.1
cols = np.nonzero(al.any(0))[0]
# split into the three silhouettes at the widest gaps
gaps = np.nonzero(np.diff(cols) > 20)[0]
spans = np.split(cols, gaps + 1)
cells = []
for sp in spans[:3]:
    rows = np.nonzero(al[:, sp[0]:sp[-1] + 1].any(1))[0]
    cx, cy = (sp[0] + sp[-1]) // 2, (rows[0] + rows[-1]) // 2
    half = int(max(sp[-1] - sp[0], rows[-1] - rows[0]) * 0.62) + 4
    pad = np.pad(bd_, ((half, half), (half, half), (0, 0)))
    cells.append(resize(pad[cy:cy + 2 * half, cx:cx + 2 * half], 128, 128))
save(np.concatenate(cells, 1), os.path.join(FX, "bird.png"))
print("BIRD frames", len(cells))

# ── 5. layout.json ──
lp = os.path.join(OUT, "layout.json")
layout = json.load(open(lp)) if os.path.exists(lp) else {}
layout["camera"] = {"pos": CAM_POS.tolist(), "target": CAM_TARGET.tolist(), "fovY": FOV_Y, "up": [0, 0, 1]}
layout["sunDir"] = [round(float(c), 4) for c in SUN_DIR]
layout["sunColor"] = [round(float(c), 3) for c in SUN_COLOR]
layout["sunScale"] = SUN_SCALE
layout["ambient"] = [round(float(c / SUN_SCALE), 3) for c in AMBIENT]
layout["table"] = TABLE
layout["backdrop"] = BACKDROP
layout["image"] = {"bg": [1320, 2868], "table": [TW, TH], "sunmask": [TW, TH], "backdrop": [BW, BH],
                   "tableOrientation": "top = +y (wall side), left = -x", "backdropOrientation": "top = +z, left = -x"}
layout["passes"] = {
    "tableBase": "table_base.jpg", "tableSun": "table_sun.jpg", "maskLattice": "mask_lattice.jpg",
    "maskLeaves": "mask_leaves.jpg",
    "combine": "table = srgb(lin(table_base) + lin(table_sun) * mask_lattice * mask_leaves); masks are linear 0..1, "
               "sunmask.jpg = mask_lattice * mask_leaves",
}
layout["layers"] = [{k: v for k, v in L.items() if k != "img"} for L in layers]
layout["layersNote"] = ("vertical planes facing -y, back to front; image top = +z, left = -x; png = straight alpha; "
                        "drift in image px per second (sky tiles horizontally)")
layout["houseOpening"] = {"x": list(HOLE_X), "z": [HOLE_Z0, round(HOLE_Z0 + (hy1 - hy0 + 1) / ppu, 3)], "y": 7.0}
layout["color"] = ("sRGB; table_base/table_sun/table are sRGB-encoded linear light (decode, add, re-encode); "
                   "masks are linear 0..1; lighting model lit = albedo * (ambient + sunColor * max(n.L, 0)) * sunScale")
layout.pop("tableStats", None)
lt = lin(TAB_IMG)
layout["tableStats"] = {"sunMean": round(float(luma(lt)[vis > 0.9].mean()), 3),
                        "shadeMean": round(float(luma(lt)[vis < 0.05].mean()), 3)}
json.dump(layout, open(lp, "w"), indent=2)
print("LAYOUT", json.dumps({k: layout[k] for k in ("sunDir", "sunColor", "sunScale", "ambient")}))

# ── preview sheet ──
def tile(a, H=900):
    s = -(-a.shape[0] // H)
    return a[::s, ::s]


tiles = [tile(bg), tile(tilt2), tile(tilt), tile(TAB_IMG), tile(np.repeat(vis[..., None], 3, 2))]
hm = max(t.shape[0] for t in tiles)
tiles = [np.pad(t, ((0, hm - t.shape[0]), (0, 8), (0, 0))) for t in tiles]
save(np.concatenate(tiles, 1), os.path.join(PREV, "anime.jpg"), 85)
