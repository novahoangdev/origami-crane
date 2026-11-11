# Renders the passes the app draws (Cycles) -> app/assets/scene/:
#   bg.jpg        1320x2868 from the app camera (reference look, no paper)
#   table.jpg     1600x2080 top-down ortho of the table top, x in [-5, 5], y in [-6, 7] (image top = +y), lighting baked
#                 (sun patch + lattice shadow + shade); the shoji is hidden from the camera but still shades / casts
#   sunmask.jpg   1600x2080 same region / orientation as table.jpg, grayscale direct-sun visibility (1 = sun, 0 = shadow)
#   backdrop.jpg  2048x1536 front ortho of the wall plane y = 7, x in [-9, 9], z in [-0.5, 13] (table hidden), slightly soft
#   layout.json   camera, sun direction / colour, ambient, table and backdrop extents, measured table brightness
# All images are display-referred sRGB (Khronos PBR Neutral view transform baked in), except sunmask.jpg (0..1 visibility).
# Quick look: render/preview/passes.jpg (bg | table | backdrop).
#
# Run: Blender -b blender/room.blend -P blender/scripts/render_passes.py -- [--pct 100] [--samples 128] [--only bg,table,sunmask,backdrop]
import bpy, json, os, sys, time
import numpy as np
import OpenImageIO as oiio

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "app", "assets", "scene")
TMP = os.path.join(ROOT, "render", "passes")
PREV = os.path.join(ROOT, "render", "preview")
PCT = int(arg("--pct", "100"))
SAMPLES = int(arg("--samples", "128"))
ONLY = set(arg("--only", "bg,table,sunmask,backdrop").split(","))
for d in (OUT, TMP, PREV):
    os.makedirs(d, exist_ok=True)

sc = bpy.context.scene
r = sc.render
OC = sc["oc"].to_dict()
LOG = {}
TABLE = {"x": [-5.0, 5.0], "y": [-6.0, 7.0]}
BACKDROP = {"y": 7.0, "x": [-9.0, 9.0], "z": [-0.5, 13.0]}

try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "METAL"
    sc.cycles.device = "GPU"
except Exception as e:  # noqa: BLE001
    print("GPU setup failed:", e)


def read(path):
    inp = oiio.ImageInput.open(path)
    px = np.asarray(inp.read_image(0, 0, 0, inp.spec().nchannels, "float"), np.float32)
    inp.close()
    return px[..., :3]


def write(arr, path, quality=90):
    h, w, c = arr.shape
    spec = oiio.ImageSpec(w, h, c, "uint8")
    spec.attribute("Compression", f"jpeg:{quality}")
    o = oiio.ImageOutput.create(path)
    o.open(path, spec)
    o.write_image(np.ascontiguousarray(np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8)))
    o.close()
    print("SAVE", os.path.relpath(path, ROOT), w, h, f"{os.path.getsize(path) / 1024:.0f} KB")


def gblur(a, sigma):
    """Separable gaussian blur (edge-clamped)."""
    rad_ = max(1, int(sigma * 3))
    x = np.arange(-rad_, rad_ + 1)
    k = np.exp(-x * x / (2 * sigma * sigma))
    k /= k.sum()
    for ax in (0, 1):
        pad = [(0, 0)] * a.ndim
        pad[ax] = (rad_, rad_)
        p = np.pad(a, pad, mode="edge")
        acc = np.zeros_like(a)
        for i, kv in enumerate(k):
            sl = [slice(None)] * a.ndim
            sl[ax] = slice(i, i + a.shape[ax])
            acc += kv * p[tuple(sl)]
        a = acc
    return a


def render(name, cam, w, h, samples, hide_cam=()):
    """Render through `cam` at w x h (scaled by --pct) to a temp PNG, return the float image (display-referred)."""
    sc.camera = bpy.data.objects[cam]
    r.resolution_x, r.resolution_y = w, h
    r.resolution_percentage = PCT
    s = r.image_settings
    s.file_format = "PNG"
    s.color_mode = "RGB"
    s.color_depth = "16"
    sc.cycles.samples = samples
    saved = [(o, o.visible_camera) for o in hide_cam]
    for o in hide_cam:
        o.visible_camera = False
    path = os.path.join(TMP, name + ".png")
    r.filepath = path
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    for o, v in saved:
        o.visible_camera = v
    dt = time.time() - t0
    print(f"── render {name} {w * PCT // 100}x{h * PCT // 100} {samples} spp {dt:.1f}s")
    LOG[name] = round(dt, 1)
    return read(path)


shoji = list(bpy.data.collections["shoji"].all_objects)
bamboo = list(bpy.data.collections["bamboo"].all_objects)
table = list(bpy.data.collections["table"].all_objects)
imgs = {}
stats = {}

if "bg" in ONLY:
    a = render("bg", "app_cam", 1320, 2868, SAMPLES, hide_cam=bamboo)
    write(a, os.path.join(OUT, "bg.jpg"), 88)
    imgs["bg"] = a

if "table" in ONLY:
    a = render("table", "table_cam", 1600, 2080, SAMPLES, hide_cam=shoji + bamboo)
    write(a, os.path.join(OUT, "table.jpg"), 90)
    imgs["table"] = a
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    # rough brightness stats: the region under the paper (x, y in [-1, 1]) and the darkest / brightest tenth
    h, w = lum.shape
    px = lambda x: int((x - TABLE["x"][0]) / 10 * w)
    py = lambda y: int((TABLE["y"][1] - y) / 13 * h)
    under = lum[py(1):py(-1), px(-1):px(1)]
    stats = {
        "lumaMin": round(float(np.percentile(lum, 1)), 3), "lumaMax": round(float(np.percentile(lum, 99)), 3),
        "shadeMean": round(float(lum[lum < np.percentile(lum, 40)].mean()), 3),
        "sunMean": round(float(lum[lum > np.percentile(lum, 85)].mean()), 3),
        "underPaperMean": round(float(under.mean()), 3),
    }
    print("TABLE", stats)

if "sunmask" in ONLY:
    # direct sun visibility on the table plane: white diffuse table, sun only (white, energy pi / cos so lit = 1.0),
    # no world, no fill, no bounces, Standard view -> 1 = full sun, 0 = lattice / leaf / paper shadow
    sunl = bpy.data.objects["sun"].data
    fillo = bpy.data.objects["room_fill"]
    vs = sc.view_settings
    keep = (sunl.color[:], sunl.energy, fillo.hide_render, sc.world, vs.view_transform, vs.look, vs.exposure,
            sc.cycles.max_bounces, sc.cycles.use_denoising, table[0].data.materials[0])
    white = bpy.data.materials.new("mask_white")
    white.use_nodes = True
    bs = next(n for n in white.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bs.inputs["Base Color"].default_value = (1, 1, 1, 1)
    bs.inputs["Roughness"].default_value = 1.0
    bs.inputs["Specular IOR Level"].default_value = 0.0
    table[0].data.materials[0] = white
    sunl.color = (1, 1, 1)
    sunl.energy = 3.14159265 / max(1e-3, OC["sun_dir"][2])
    fillo.hide_render = True
    sc.world = None
    vs.view_transform = "Standard"
    vs.look = "None"
    vs.exposure = 0.0
    sc.cycles.max_bounces = 0
    sc.cycles.use_denoising = False
    a = render("sunmask", "table_cam", 1600, 2080, max(16, SAMPLES // 2), hide_cam=shoji + bamboo)
    (sunl.color, sunl.energy, fillo.hide_render, sc.world, vs.view_transform, vs.look, vs.exposure,
     sc.cycles.max_bounces, sc.cycles.use_denoising, table[0].data.materials[0]) = keep
    g = a.mean(axis=2, keepdims=True)
    g = np.clip(g / max(1e-3, float(np.percentile(g, 99.5))), 0, 1)   # normalise (glass tint, sampling noise)
    g[: int(round((TABLE["y"][1] - 6.8) / 13 * g.shape[0])) + 1] = 0.0  # the strip under the wall base is never sunlit
    write(np.repeat(g, 3, 2), os.path.join(OUT, "sunmask.jpg"), 90)
    imgs["sunmask"] = np.repeat(g, 3, 2)
    stats_mask = {"litFraction": round(float((g > 0.5).mean()), 3)}
    print("SUNMASK", stats_mask)

if "backdrop" in ONLY:
    a = render("backdrop", "backdrop_cam", 2048, 1536, SAMPLES, hide_cam=table)
    a = gblur(a, 1.6 * PCT / 100)
    write(a, os.path.join(OUT, "backdrop.jpg"), 88)
    imgs["backdrop"] = a

# ── layout.json ──
# ambient calibrated from the renders, in the app's shading model lit = albedo * (ambient + sunColor * max(n.L, 0)):
# per channel, ambient = sunColor * L.z * shade / (sun - shade), linear values of table.jpg in the camera-visible area,
# split by sunmask (sun > 0.9, shade < 0.05)
sun_lin = [round(c, 3) for c in OC["sun_color"]]
amb = [0.2, 0.2, 0.22]
if "table" in imgs and "sunmask" in imgs:
    lin = lambda a: np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    t, m = lin(imgs["table"]), imgs["sunmask"][..., 0]
    h, w = m.shape
    ys = slice(int((TABLE["y"][1] - 5.5) / 13 * h), int((TABLE["y"][1] + 2.5) / 13 * h))
    xs = slice(int(3 / 10 * w), int(7 / 10 * w))
    tv, mv = t[ys, xs].reshape(-1, 3), m[ys, xs].reshape(-1)
    lp_, ls_ = tv[mv > 0.9].mean(0), tv[mv < 0.05].mean(0)
    amb = [round(float(OC["sun_color"][i] * OC["sun_dir"][2] * ls_[i] / max(1e-4, lp_[i] - ls_[i])), 3) for i in range(3)]
    print("AMBIENT", amb, "sun", lp_.round(3), "shade", ls_.round(3))
layout = {
    "camera": {k: ([round(c, 4) for c in v] if isinstance(v, list) else v) for k, v in OC["camera"].items()},
    "sunDir": OC["sun_dir"],
    "sunColor": sun_lin,
    "ambient": amb,
    "table": TABLE,
    "backdrop": BACKDROP,
    "image": {"bg": [1320, 2868], "table": [1600, 2080], "sunmask": [1600, 2080], "backdrop": [2048, 1536],
              "tableOrientation": "top = +y (wall side), left = -x", "backdropOrientation": "top = +z, left = -x"},
    "color": f"sRGB display-referred (Blender {sc.view_settings.view_transform} view transform baked in); sunmask.jpg is linear visibility",
}
lp = os.path.join(OUT, "layout.json")
if os.path.exists(lp) and not stats:
    try:
        layout["tableStats"] = json.load(open(lp)).get("tableStats", {})
    except Exception:  # noqa: BLE001
        pass
if stats:
    layout["tableStats"] = stats
json.dump(layout, open(lp, "w"), indent=2)
print("LAYOUT", json.dumps(layout))

# ── contact sheet ──
if imgs:
    H = 900
    tiles = []
    for k in ("bg", "table", "sunmask", "backdrop"):
        if k in imgs:
            a = imgs[k]
            step = -(-a.shape[0] // H)
            tiles.append(a[::step, ::step])
    hmax = max(t.shape[0] for t in tiles)
    tiles = [np.pad(t, ((0, hmax - t.shape[0]), (0, 8), (0, 0))) for t in tiles]
    write(np.concatenate(tiles, 1), os.path.join(PREV, "passes.jpg"), 85)
print("TIMES", LOG)
